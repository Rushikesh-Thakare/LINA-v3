"""
LINA v3 — Command Processor (Brain Orchestrator)

Receives text commands and orchestrates the full response pipeline:
  1. Greeting detection
  2. Min-length guard
  3. IntentRouter fast-path
  4. LLM (Groq / llama) with timeout + fallback
  5. ScriptValidator
  6. Sandbox execution (timeout 10 s)
  7. LLM output interpretation
  8. speak + display via callbacks
  9. HistoryManager log

This class is NOT a QThread — it is called from a _ProcessWorker QThread.
All callbacks must be connected with Qt.QueuedConnection in the caller.
Never crashes the app — all exceptions caught and degraded gracefully.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from typing import Callable, Optional

from lina.brain.intent_router import IntentRouter, IntentMatch
from lina.brain.validator import ScriptValidator, RiskLevel
from lina.system.executor import Executor
from lina.system.history import HistoryManager
from lina.system.distro import detect_distro

log = logging.getLogger(__name__)

# ── Greeting detection ────────────────────────────────────────────────────────
_GREETINGS = frozenset([
    "hello", "hi", "hey", "hey lina", "hello lina", "hi lina",
    "good morning", "good afternoon", "good evening", "howdy",
    "what's up", "sup", "greetings",
])

_GREETING_REPLIES = [
    "Hello! I'm LINA, your Linux voice assistant. How can I help you today?",
    "Hi there! Ready to help. Just say what you need.",
    "Hey! What can I do for you?",
    "Hello! Ask me anything — I can run commands, open apps, or look things up.",
]

_MIN_COMMAND_CHARS = 3
_LLM_TIMEOUT = 30      # seconds
_EXEC_TIMEOUT = 10     # seconds (per executor call)
_HISTORY_CONTEXT = 5   # commands to pass to LLM


class CommandProcessor:
    """
    Dependency-injected command orchestrator.

    Constructor arguments:
        llm             — LLMService (Groq / llama primary)
        intent_router   — IntentRouter
        validator       — ScriptValidator
        executor        — Executor
        history         — HistoryManager
        distro          — str (e.g. "Ubuntu 22.04")

    Callback arguments (wire these to Qt signals on the main thread side):
        on_output  — Callable[[str], None]  — text to display in terminal
        on_speak   — Callable[[str], None]  — text to speak via TTS
        on_status  — Callable[[str], None]  — status bar label
    """

    def __init__(
        self,
        llm=None,
        intent_router: Optional[IntentRouter] = None,
        validator: Optional[ScriptValidator] = None,
        executor: Optional[Executor] = None,
        history: Optional[HistoryManager] = None,
        distro: Optional[str] = None,
        on_output: Optional[Callable[[str], None]] = None,
        on_speak:  Optional[Callable[[str], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        # Lazy-init any omitted deps (backward-compatible)
        self._llm          = llm
        self.router        = intent_router or IntentRouter()
        self.validator     = validator or ScriptValidator()
        self.executor      = executor  or Executor()
        self.history       = history   or HistoryManager()
        self.distro        = distro    or detect_distro()

        # Callbacks — default to no-op if not provided
        self._on_output: Callable[[str], None] = on_output or (lambda _: None)
        self._on_speak:  Callable[[str], None] = on_speak  or (lambda _: None)
        self._on_status: Callable[[str], None] = on_status or (lambda _: None)

        # Context window: last N commands for LLM
        self._cmd_history: list[str] = []
        self._lock = threading.Lock()   # process() is called from a QThread

        # Greeting reply rotation
        self._greeting_idx = 0

        # Paranoid mode (read from config; can be toggled at runtime)
        try:
            from lina.config import PARANOID_MODE
            self.paranoid_mode: bool = PARANOID_MODE
        except ImportError:
            self.paranoid_mode = False

    # ── Lazy LLM loader ───────────────────────────────────────────────────────
    def _get_llm(self):
        if self._llm is None:
            from lina.brain.llm_claude import LLMService
            self._llm = LLMService()
            log.info("LLMService ready (Groq llama-3.1-8b-instant).")
        return self._llm

    # =========================================================================
    # Main entry point — called from a _ProcessWorker QThread
    # =========================================================================

    def process(self, command: str) -> dict:
        """
        Full 9-step processing pipeline.
        Returns a result dict so the caller can emit Qt signals.
        All callbacks are fired synchronously here (inside the QThread).
        """
        result = self._empty_result(command)

        try:
            self._on_status("Processing…")

            # ── Step 1: Greeting ──────────────────────────────────────────────
            if self._is_greeting(command):
                reply = self._greeting_reply()
                self._emit(result, explanation=reply)
                return result

            # ── Step 2: Min length ────────────────────────────────────────────
            if len(command.strip()) < _MIN_COMMAND_CHARS:
                self._emit(result, explanation="Sorry, I didn't catch that. Could you say that again?")
                return result

            # ── Step 3: Intent router fast-path ──────────────────────────────
            match = self.router.match(command)
            if match:
                log.info("Intent: %s → %s (%.2f)", match.intent_name, match.action, match.confidence)
                self._on_status(f"Running: {match.intent_name}…")
                return self._execute_intent(match, command, result)

            # ── Step 4: LLM ──────────────────────────────────────────────────
            log.info("Intent: llm → __LLM__")
            self._on_status("Thinking…")
            script, description = self._llm_generate(command)

            if not script:
                msg = "I couldn't generate a command for that. Please try a different request."
                self._emit(result, explanation=msg, status="error")
                return result

            result["script"] = script
            result["type"]   = "llm"

            # ── Step 5: Validate ──────────────────────────────────────────────
            vr = self.validator.validate(script)

            if not vr.is_safe:
                msg = f"I can't do that safely. {vr.blocked_reason}"
                self._output(f"⛔ Blocked: {vr.blocked_reason}")
                self._emit(result, explanation=msg, status="blocked")
                return result

            if vr.risk_level == RiskLevel.HIGH_RISK:
                warn = f"⚠ High-risk command: {vr.blocked_reason}"
                self._output(warn)
                if self.paranoid_mode:
                    # In paranoid mode, block and ask instead of running
                    msg = f"This command is high-risk: {vr.blocked_reason}. Paranoid mode is on, so I won't run it automatically."
                    self._emit(result, explanation=msg, status="blocked")
                    return result

            # ── Step 6: Execute ───────────────────────────────────────────────
            self._on_status("Running…")
            output = self._exec_with_timeout(script)
            result["output"] = output
            self._output(f"$ {script}\n{output}".strip())

            # ── Step 7: Interpret ─────────────────────────────────────────────
            self._on_status("Interpreting…")
            explanation = self._llm_interpret(command, output)

            # ── Step 8: Speak + display ───────────────────────────────────────
            self._emit(result, explanation=explanation)

            # ── Step 9: Log ───────────────────────────────────────────────────
            self._log_history(command)

        except Exception as exc:
            log.exception("CommandProcessor.process() unhandled error: %s", exc)
            msg = f"Something went wrong: {exc}"
            self._emit(result, explanation=msg, status="error")

        finally:
            self._on_status("Idle")

        return result

    # =========================================================================
    # Intent execution
    # =========================================================================

    def _execute_intent(self, match: IntentMatch, command: str, result: dict) -> dict:
        action = match.action
        params = match.params

        try:
            if action == "launch_app":
                self._do_launch_app(params["app"], result)

            elif action == "shell_command":
                self._do_shell_command(params["cmd"], command, result)

            elif action == "open_url":
                self._do_open_url(params["url"], result)

            elif action == "show_help":
                self._do_help(result)

            elif action == "show_history":
                self._do_history(result)

            elif action == "clear_terminal":
                result["type"] = "clear_terminal"
                result["explanation"] = "Terminal cleared."
                self._on_speak("Terminal cleared.")

            else:
                log.warning("Unknown intent action: %s — falling to LLM", action)
                return self.process(command)   # re-route to LLM

        except Exception as exc:
            log.exception("Intent execution error (%s): %s", action, exc)
            msg = f"Failed to {action.replace('_', ' ')}: {exc}"
            self._emit(result, explanation=msg, status="error")

        self._log_history(command)
        return result

    # ── Intent action handlers ────────────────────────────────────────────────

    def _do_launch_app(self, app: str, result: dict) -> None:
        if not shutil.which(app):
            msg = f"'{app}' is not installed on this system."
            self._emit(result, explanation=msg, status="error")
            return
        subprocess.Popen(
            [app],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        msg = f"Opening {app}."
        self._output(f"🚀 Launched: {app}")
        self._emit(result, explanation=msg)

    def _do_shell_command(self, cmd: str, orig_command: str, result: dict) -> None:
        # Intent commands are pre-vetted; use lightweight validation
        vr = self.validator.validate_intent_command(cmd)
        if not vr.is_safe:
            self._emit(result, explanation=vr.blocked_reason, status="blocked")
            return
        output = self._exec_with_timeout(cmd)
        result["script"] = cmd
        result["output"] = output
        self._output(f"$ {cmd}\n{output}".strip())
        # For intent shell commands, use condensed output as explanation (no LLM call)
        explanation = output.strip().replace("\n", ". ")[:280] or "Done."
        self._emit(result, explanation=explanation)

    def _do_open_url(self, url: str, result: dict) -> None:
        opener = shutil.which("xdg-open") or shutil.which("firefox") or shutil.which("chromium")
        if not opener:
            self._emit(result, explanation="No browser found on this system.", status="error")
            return
        subprocess.Popen(
            [opener, url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        msg = f"Opening {url}."
        self._output(f"🌐 {url}")
        self._emit(result, explanation=msg)

    def _do_help(self, result: dict) -> None:
        msg = (
            "I can open apps like terminal, browser, and calculator. "
            "Check system info: time, IP, battery, disk, and memory. "
            "Control media, open websites, and run any Linux command you describe. "
            f"Running on {self.distro}."
        )
        self._output("📋 " + msg)
        self._emit(result, explanation=msg)

    def _do_history(self, result: dict) -> None:
        entries = self.history.recent(20)
        text = "\n".join(entries) if entries else "No history yet."
        result["output"] = text
        self._output(text)
        msg = "Here are your recent commands."
        self._emit(result, explanation=msg)

    # =========================================================================
    # LLM helpers with timeout
    # =========================================================================

    def _llm_generate(self, command: str) -> tuple[str, str]:
        """Call LLM to generate bash script. Returns (script, description) or ("", "")."""
        with self._lock:
            self._cmd_history.append(command)
            self._cmd_history = self._cmd_history[-20:]
            context = self._cmd_history[-(_HISTORY_CONTEXT + 1):-1]

        result_holder: list = []
        error_holder:  list = []

        def _worker():
            try:
                llm = self._get_llm()
                script, desc = llm.generate_bash_script(command, self.distro, context)
                result_holder.append((script, desc))
            except Exception as exc:
                log.error("LLM generate error: %s", exc)
                error_holder.append(exc)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout=_LLM_TIMEOUT)

        if t.is_alive():
            log.error("LLM generate_bash_script timed out after %ds", _LLM_TIMEOUT)
            return "", ""

        if result_holder:
            return result_holder[0]
        return "", ""

    def _llm_interpret(self, command: str, output: str) -> str:
        """Call LLM to interpret output. Returns friendly explanation."""
        result_holder: list = []

        def _worker():
            try:
                llm = self._get_llm()
                explanation = llm.interpret_output(command, output)
                result_holder.append(explanation)
            except Exception as exc:
                log.warning("LLM interpret error: %s", exc)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout=_LLM_TIMEOUT)

        if result_holder:
            return result_holder[0]
        # Fallback: use raw output condensed
        return output.strip().replace("\n", ". ")[:200] or "Done."

    # =========================================================================
    # Executor with timeout
    # =========================================================================

    def _exec_with_timeout(self, script: str) -> str:
        """Run script via executor with a hard timeout. Returns stdout string."""
        result_holder: list = []

        def _worker():
            try:
                out = self.executor.run(script)
                result_holder.append(out)
            except Exception as exc:
                result_holder.append(f"[exec error] {exc}")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout=_EXEC_TIMEOUT)

        if t.is_alive():
            log.error("Script execution timed out after %ds: %s", _EXEC_TIMEOUT, script[:60])
            return f"[timeout] Command took more than {_EXEC_TIMEOUT}s."

        return result_holder[0] if result_holder else ""

    # =========================================================================
    # Callback helpers
    # =========================================================================

    def _output(self, text: str) -> None:
        """Display text in the terminal pane."""
        try:
            self._on_output(text)
        except Exception:
            pass

    def _emit(self, result: dict, *, explanation: str = "", status: str = "ok") -> None:
        """Set result fields and fire both on_output (display) and on_speak callbacks."""
        result["explanation"] = explanation
        result["status"]      = status
        if explanation:
            try:
                self._on_output(f"💬 LINA: {explanation}")
                self._on_speak(explanation)
            except Exception:
                pass

    def _log_history(self, command: str) -> None:
        try:
            from datetime import datetime, timezone
            self.history.log({"command": command, "ts": datetime.now(timezone.utc).isoformat()})
        except Exception:
            pass

    # =========================================================================
    # Greeting helpers
    # =========================================================================

    def _is_greeting(self, text: str) -> bool:
        return text.strip().lower() in _GREETINGS

    def _greeting_reply(self) -> str:
        reply = _GREETING_REPLIES[self._greeting_idx % len(_GREETING_REPLIES)]
        self._greeting_idx += 1
        return reply

    # =========================================================================
    # Utilities
    # =========================================================================

    @staticmethod
    def _empty_result(command: str) -> dict:
        return {
            "type":        "intent",
            "command":     command,
            "script":      None,
            "output":      "",
            "explanation": "",
            "status":      "ok",
        }

    def set_callbacks(
        self,
        on_output: Callable[[str], None],
        on_speak:  Callable[[str], None],
        on_status: Callable[[str], None],
    ) -> None:
        """Update callbacks after construction (useful for MainWindow wiring)."""
        self._on_output = on_output
        self._on_speak  = on_speak
        self._on_status = on_status
