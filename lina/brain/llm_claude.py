"""
LINA v3 — Primary LLM Service (Groq / llama-3.1-8b-instant — free)

Provides LLMService with clean, typed error handling and history context.
Uses Groq's llama-3.1-8b-instant model as the primary backend (free tier,
14 400 requests/day). Swap out _call() for the Anthropic SDK if you ever
want to use Claude instead.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional

from lina.config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    BASH_GENERATION_PROMPT,
    OUTPUT_INTERPRETATION_PROMPT,
)

log = logging.getLogger(__name__)

# ── Custom exceptions ─────────────────────────────────────────────────────────

class LLMError(Exception):
    """Base class for all LLM errors."""

class LLMConnectionError(LLMError):
    """Network / connection failure talking to the LLM API."""

class LLMRateLimitError(LLMError):
    """API rate limit or quota exceeded."""

class LLMAuthError(LLMError):
    """Invalid or expired API key."""


# ── JSON extraction ────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) if present."""
    text = text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    return text.strip()


def _extract_json(text: str) -> Optional[dict]:
    """
    Robustly extract the first balanced JSON object from a string.
    Handles:
      - Bare JSON responses
      - Markdown-fenced responses
      - Responses with explanatory text before/after
      - Multi-line bash scripts with nested { }
    """
    # 1) Try whole string after fence-stripping
    try:
        return json.loads(_strip_fences(text))
    except json.JSONDecodeError:
        pass

    # 2) Balanced-brace depth scanner (handles nested braces in bash)
    for start in range(len(text)):
        if text[start] != "{":
            continue
        depth = 0
        for end in range(start, len(text)):
            if text[end] == "{":
                depth += 1
            elif text[end] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : end + 1])
                    except json.JSONDecodeError:
                        break
    return None


# ══════════════════════════════════════════════════════════════════════════════
# ClaudeService
# ══════════════════════════════════════════════════════════════════════════════

class LLMService:
    """
    Primary LLM service for LINA.
    Backend: Groq llama-3.1-8b-instant (free tier, 14 400 req/day).

    Usage:
        svc = LLMService()   # reads GROQ_API_KEY from config
        script, desc = svc.generate_bash_script(query, distro, history)
        explanation  = svc.interpret_output(command, output)
    """

    _MAX_RETRIES = 2
    _RETRY_DELAY = 1.0   # seconds between retries on connection errors

    def __init__(self, api_key: str = GROQ_API_KEY) -> None:
        if not api_key:
            raise LLMAuthError(
                "No API key provided. Set GROQ_API_KEY in your .env file. "
                "Get a free key at: https://console.groq.com"
            )
        try:
            from groq import Groq
            self._client = Groq(api_key=api_key)
            self._model = GROQ_MODEL
        except ImportError as exc:
            raise LLMError("groq package not installed. Run: pip install groq") from exc

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_bash_script(
        self,
        query: str,
        distro: str = "Linux",
        history_context: list[str] | None = None,
    ) -> tuple[str, str]:
        """
        Convert a natural language query to a safe bash script.

        Args:
            query:           The user's voice/text command.
            distro:          Detected Linux distro string (e.g. "Ubuntu 22.04").
            history_context: Last N command strings for context (up to 5 used).

        Returns:
            (bash_script, description) tuple.

        Raises:
            LLMConnectionError, LLMRateLimitError, LLMAuthError, LLMError
        """
        context_block = self._build_history_block(history_context)
        system_prompt = BASH_GENERATION_PROMPT.format(
            distro=distro,
            query=query,  # prompt template may include {query}
        )
        user_msg = f"{context_block}User command: {query}"

        raw = self._call(
            system=system_prompt,
            user=user_msg,
            max_tokens=500,
            temperature=0.1,
        )
        log.debug("generate_bash_script raw response:\n%s", raw)

        data = _extract_json(raw)
        if not data:
            raise LLMError(
                f"LLM returned non-JSON output. Got:\n{raw[:300]}"
            )

        bash_script = data.get("bash_script") or data.get("bash script", "").strip()
        description = data.get("description", "").strip()

        if not bash_script:
            raise LLMError("LLM JSON response missing required 'bash_script' key.")

        return bash_script, description

    def interpret_output(self, command: str, output: str) -> str:
        """
        Produce a friendly 1-2 sentence explanation of a command's output.

        Args:
            command: The original user command / query.
            output:  Raw stdout/stderr from the executed script (truncated).

        Returns:
            TTS-ready plain text explanation.
        """
        prompt = OUTPUT_INTERPRETATION_PROMPT.format(
            query=command,
            output=output[:2000],
        )
        explanation = self._call(
            system="You are LINA, a friendly Linux voice assistant. Speak in plain English.",
            user=prompt,
            max_tokens=150,
            temperature=0.3,
        )
        return explanation.strip()

    # ── Internal: API call with retry ─────────────────────────────────────────

    def _call(
        self,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """
        Call the LLM API with retry logic.
        Retries up to _MAX_RETRIES times on connection errors.
        Maps API exceptions to LINA's LLMError hierarchy.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(self._MAX_RETRIES + 1):
            try:
                completion = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return completion.choices[0].message.content or ""

            except Exception as exc:
                exc_type = type(exc).__name__
                exc_str  = str(exc).lower()

                # ── Map to typed LLM errors ───────────────────────────────────
                if "authenticationerror" in exc_type or "401" in exc_str or "invalid api key" in exc_str:
                    raise LLMAuthError(
                        "Invalid GROQ_API_KEY. Check your .env file or get a new key at "
                        "https://console.groq.com"
                    ) from exc

                if "ratelimiterror" in exc_type or "429" in exc_str or "rate limit" in exc_str:
                    raise LLMRateLimitError(
                        "Groq rate limit reached. Wait a moment and try again."
                    ) from exc

                if "connectionerror" in exc_type or "timeout" in exc_str or "connect" in exc_str:
                    last_exc = LLMConnectionError(
                        f"Could not reach Groq API (attempt {attempt + 1}): {exc}"
                    )
                    if attempt < self._MAX_RETRIES:
                        log.warning("LLM connection error — retrying in %.1fs…", self._RETRY_DELAY)
                        time.sleep(self._RETRY_DELAY)
                        continue
                    raise last_exc from exc

                # ── Unknown error ─────────────────────────────────────────────
                raise LLMError(f"LLM call failed: {exc}") from exc

        raise LLMConnectionError("LLM API unreachable after retries.") from last_exc

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_history_block(history: list[str] | None) -> str:
        """Format last 5 commands as a context block to prepend to the prompt."""
        if not history:
            return ""
        recent = history[-5:]
        lines  = "\n".join(f"  - {cmd}" for cmd in recent)
        return f"Recent commands for context:\n{lines}\n\n"
