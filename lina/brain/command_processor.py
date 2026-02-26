"""
LINA v3 — Command Processor (Brain Orchestrator)
Ties together IntentRouter, ScriptValidator, Executor, and LLMs.
Runs synchronously — MUST be called from a worker thread, not the Qt main thread.
"""

import logging
import os
from datetime import datetime

from lina.brain.intent_router import (
    IntentRouter, APP_FALLBACKS,
    INTENT_HELP, INTENT_HISTORY, INTENT_SSH_STATUS,
    INTENT_WEATHER, INTENT_TIMEZONE,
    INTENT_PKG_CHECK, INTENT_PKG_VERSION,
    INTENT_LLM_FALLBACK,
)
from lina.brain.validator import ScriptValidator
from lina.system.executor import Executor
from lina.system.history import HistoryManager
from lina.system.distro import detect_distro

log = logging.getLogger(__name__)


class CommandProcessor:
    """
    Processes a voice/text command end-to-end.

    Typical pipeline:
        1. IntentRouter → fast-path bash or sentinel or LLM fallback
        2. ScriptValidator → block dangerous scripts
        3. Executor → run in sandbox
        4. LLM.interpret_output → friendly explanation
        5. HistoryManager → log the event
    """

    def __init__(self):
        self.router    = IntentRouter()
        self.validator = ScriptValidator()
        self.executor  = Executor()
        self.history   = HistoryManager()
        self.distro    = detect_distro()
        self._llm      = None   # lazy-loaded on first LLM call
        self._llm_name = None

    # ── LLM: Groq primary (free), Claude optional fallback ────────────────────
    def _get_llm(self, *, reset: bool = False):
        """Return cached LLM. Groq (llama-3.1-8b-instant) is primary — free tier."""
        if self._llm is not None and not reset:
            return self._llm
        # Always try Groq first — it's free
        try:
            from lina.brain.llm_groq import GroqLLM
            self._llm = GroqLLM()
            self._llm_name = "groq"
            log.info("Using Groq (llama-3.1-8b-instant) as primary LLM.")
            return self._llm
        except Exception as exc:
            log.warning("Groq init failed (%s) — trying Claude.", exc)

        # Claude fallback (only if key is set)
        try:
            from lina.config import ANTHROPIC_API_KEY
            if not ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY not set")
            from lina.brain.llm_claude import ClaudeLLM
            self._llm = ClaudeLLM()
            self._llm_name = "claude"
            log.info("Using Claude as fallback LLM.")
        except Exception as exc:
            raise RuntimeError("No LLM available. Set GROQ_API_KEY in .env.") from exc
        return self._llm

    def _call_with_fallback(self, method: str, *args):
        """Call llm.<method>(*args). Raises if Groq fails (Claude removed — no credits)."""
        llm = self._get_llm()
        try:
            return getattr(llm, method)(*args)
        except Exception as exc:
            log.error("Groq LLM error: %s", exc)
            raise

    # ── Main public method ────────────────────────────────────────────────────
    def process(self, command: str) -> dict:
        """
        Process a command and return a result dict:
        {
            "type":        "intent" | "llm" | "error",
            "command":     str,
            "script":      str | None,
            "output":      str,
            "explanation": str,   # TTS-ready
            "status":      "ok" | "blocked" | "error",
        }
        """
        log.info("Processing: %s", command)
        result = {
            "type": "intent",
            "command": command,
            "script": None,
            "output": "",
            "explanation": "",
            "status": "ok",
        }

        try:
            intent_key, intent_value = self.router.route(command)
            log.info("Intent: %s → %s", intent_key, intent_value)

            # ── Sentinel handlers ─────────────────────────────────────────────
            if intent_value == INTENT_HELP:
                return self._handle_help(result)

            if intent_value == INTENT_HISTORY:
                return self._handle_history(result)

            if intent_value == INTENT_SSH_STATUS:
                intent_value = "systemctl is-active ssh 2>/dev/null || systemctl is-active sshd 2>/dev/null || echo 'ssh not installed'"

            if intent_value == INTENT_WEATHER:
                return self._handle_weather(result)

            if intent_value == INTENT_TIMEZONE:
                intent_value = "timedatectl | grep 'Time zone'"

            if intent_value == INTENT_PKG_CHECK:
                return self._handle_pkg_check(command, result)

            if intent_value == INTENT_PKG_VERSION:
                return self._handle_pkg_version(command, result)

            # ── LLM fallback ──────────────────────────────────────────────────
            if intent_value == INTENT_LLM_FALLBACK:
                return self._handle_llm(command, result)

            # ── GUI app launch intents ─────────────────────────────────────────
            if intent_value.endswith("&"):
                return self._handle_gui_launch(intent_key, intent_value, command, result)

            # ── Runnable bash command ─────────────────────────────────────────
            result["script"] = intent_value
            return self._run_script(intent_value, command, result)

        except Exception as exc:
            log.exception("CommandProcessor error: %s", exc)
            result.update({"type": "error", "status": "error", "explanation": f"Error: {exc}"})
            return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _run_script(self, script: str, command: str, result: dict) -> dict:
        safe, reason = self.validator.validate(script)
        if not safe:
            result.update({"status": "blocked", "explanation": reason})
            self.history.log({**result, "ts": _now()})
            return result

        output = self.executor.run(script)
        result["output"] = output
        result["explanation"] = output.strip().replace("\n", ", ")[:250] or "Done."
        self.history.log({**result, "ts": _now()})
        return result

    def _handle_llm(self, command: str, result: dict) -> dict:
        result["type"] = "llm"
        script, description = self._call_with_fallback("generate_bash_script", command, self.distro)
        result["script"] = script

        safe, reason = self.validator.validate(script)
        if not safe:
            result.update({"status": "blocked", "explanation": reason})
            self.history.log({**result, "ts": _now()})
            return result

        output = self.executor.run(script)
        explanation = self._call_with_fallback("interpret_output", command, output)
        result.update({"output": output, "explanation": explanation})
        self.history.log({**result, "ts": _now()})
        return result

    def _handle_gui_launch(self, intent_key: str, intent_value: str, command: str, result: dict) -> dict:
        # Determine fallback category
        cat = next((k for k in APP_FALLBACKS if k in intent_key), None)
        app = IntentRouter.which_first(APP_FALLBACKS[cat]) if cat else intent_value.replace(" &", "").strip()
        if not app:
            result.update({"status": "error", "explanation": "Application not found on this system."})
            return result
        ok, msg = IntentRouter.launch_gui(app)
        result["explanation"] = "Done." if ok else f"Failed to launch: {msg}"
        result["status"] = "ok" if ok else "error"
        self.history.log({**result, "ts": _now()})
        return result

    def _handle_help(self, result: dict) -> dict:
        lines = [
            "LINA can:",
            "  • Open apps: terminal, browser, files, calculator",
            "  • System info: IP, time, uptime, battery, CPU temp",
            "  • Files: list, view, search",
            "  • Media: play, pause, next, previous track",
            f"  • Distro detected: {self.distro}",
            "  • Generate and run shell commands via AI",
        ]
        result["explanation"] = " ".join(lines)
        return result

    def _handle_history(self, result: dict) -> dict:
        entries = self.history.recent(20)
        result["output"] = "\n".join(entries)
        result["explanation"] = "Here are your recent commands."
        return result

    def _handle_weather(self, result: dict) -> dict:
        script = "curl -s 'https://wttr.in?format=3'"
        return self._run_script(script, "weather", result)

    def _handle_pkg_check(self, command: str, result: dict) -> dict:
        import re
        m = re.search(r"package\s+([A-Za-z0-9+_.-]{1,64})", command.lower())
        if not m:
            result["explanation"] = "Please say: is package <name> installed"
            return result
        pkg = m.group(1)
        script = (
            f"(dpkg -s {pkg} 2>/dev/null | grep -q 'Status: install') "
            f"&& echo installed || (rpm -q {pkg} >/dev/null 2>&1 && echo installed || echo 'not installed')"
        )
        return self._run_script(script, command, result)

    def _handle_pkg_version(self, command: str, result: dict) -> dict:
        import re
        m = re.search(r"version\s+of\s+([A-Za-z0-9+_.-]{1,64})", command.lower())
        if not m:
            result["explanation"] = "Please say: version of <command>"
            return result
        name = m.group(1)
        script = f"command -v {name} >/dev/null 2>&1 && {name} --version || echo '{name} not found'"
        return self._run_script(script, command, result)


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"
