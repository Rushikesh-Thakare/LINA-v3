"""
LINA v3 — LLM Client: Anthropic Claude (Primary)
Generates bash scripts and interprets command output via Claude Haiku.
"""

import json
import logging
import re
from typing import Optional

import anthropic

from lina.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, BASH_GENERATION_PROMPT, OUTPUT_INTERPRETATION_PROMPT

log = logging.getLogger(__name__)


def _extract_json(text: str) -> Optional[dict]:
    """Extract the first valid JSON object from an LLM response string."""
    blocks = re.findall(r"\{[\s\S]*?\}", text)
    for block in reversed(blocks):
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            continue
    return None


class ClaudeLLM:
    """Primary LLM — Anthropic Claude Haiku."""

    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set in .env")
        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # ── Bash script generation ────────────────────────────────────────────────
    def generate_bash_script(self, query: str, distro: str = "Linux") -> tuple[str, str]:
        """
        Returns (bash_script, description).
        Raises ValueError if the response cannot be parsed.
        """
        prompt = BASH_GENERATION_PROMPT.format(query=query, distro=distro)
        log.debug("Claude prompt:\n%s", prompt)

        message = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        log.debug("Claude raw response:\n%s", raw)

        data = _extract_json(raw)
        if not data:
            raise ValueError(f"Claude returned non-JSON response: {raw[:200]}")

        bash_script = data.get("bash_script") or data.get("bash script", "")
        description = data.get("description", "")

        if not bash_script:
            raise ValueError("Claude JSON missing 'bash_script' field.")

        return bash_script, description

    # ── Output interpretation ─────────────────────────────────────────────────
    def interpret_output(self, query: str, output: str) -> str:
        """Returns a friendly, TTS-ready explanation of the command's output."""
        prompt = OUTPUT_INTERPRETATION_PROMPT.format(query=query, output=output[:2000])
        message = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
