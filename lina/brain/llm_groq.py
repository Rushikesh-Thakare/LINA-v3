"""
LINA v3 — LLM Client: Groq (Primary — free tier)
llama-3.1-8b-instant via Groq API.
"""

import json
import logging
import re
from typing import Optional

from groq import Groq

from lina.config import GROQ_API_KEY, GROQ_MODEL, BASH_GENERATION_PROMPT, OUTPUT_INTERPRETATION_PROMPT

log = logging.getLogger(__name__)


def _extract_json(text: str) -> Optional[dict]:
    """
    Extract the first balanced JSON object from a string.
    Uses a brace-depth scanner that correctly handles multi-line bash scripts
    containing curly braces (e.g. heredocs, awk, functions).
    Falls back to trying the whole string as JSON if scanning fails.
    """
    # Try the whole string first (cleanest case)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Scan for balanced { ... } blocks
    for start in range(len(text)):
        if text[start] != '{':
            continue
        depth = 0
        for end in range(start, len(text)):
            if text[end] == '{':
                depth += 1
            elif text[end] == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[start:end + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break  # try next starting position
    return None


class GroqLLM:
    """Primary LLM — Groq (llama-3.1-8b-instant), free tier."""

    def __init__(self):
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not set in .env")
        self._client = Groq(api_key=GROQ_API_KEY)

    # ── Bash script generation ────────────────────────────────────────────────
    def generate_bash_script(self, query: str, distro: str = "Linux") -> tuple[str, str]:
        """Returns (bash_script, description). Raises ValueError if unparseable."""
        prompt = BASH_GENERATION_PROMPT.format(query=query, distro=distro)
        log.debug("Groq prompt:\n%s", prompt)

        completion = self._client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are a Linux assistant. Respond ONLY with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1024,
            temperature=0.1,
        )
        raw = completion.choices[0].message.content
        log.debug("Groq raw response:\n%s", raw)

        data = _extract_json(raw)
        if not data:
            raise ValueError(f"Groq returned non-JSON response: {raw[:200]}")

        bash_script = data.get("bash_script") or data.get("bash script", "")
        description = data.get("description", "")

        if not bash_script:
            raise ValueError("Groq JSON missing 'bash_script' field.")

        return bash_script, description

    # ── Output interpretation ─────────────────────────────────────────────────
    def interpret_output(self, query: str, output: str) -> str:
        """Returns a friendly, TTS-ready explanation of the command's output."""
        prompt = OUTPUT_INTERPRETATION_PROMPT.format(query=query, output=output[:2000])
        completion = self._client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
        )
        return completion.choices[0].message.content.strip()
