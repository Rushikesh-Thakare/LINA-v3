"""
LINA v3 — Configuration
Loads all settings from ~/.local/share/lina/.env (or project-root .env).
Provides validate_config() and auto-creates required directories.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env ─────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)

def _env_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes")

def _env_float(key: str, default: float = 0.0) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default

def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default

# ── API Keys ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = _env("ANTHROPIC_API_KEY")
GROQ_API_KEY: str      = _env("GROQ_API_KEY")

# ── Whisper (STT) ─────────────────────────────────────────────────────────────
WHISPER_MODEL_SIZE: str = _env("WHISPER_MODEL", "small.en")

# ── XDG-compliant data directories ───────────────────────────────────────────
_XDG_DATA = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
_LINA_DIR = _XDG_DATA / "lina"

PIPER_MODEL_PATH: Path = Path(_env("PIPER_MODEL_PATH", str(_LINA_DIR / "models" / "piper")))
VOSK_FALLBACK_MODEL: Path = Path(_env("VOSK_FALLBACK_MODEL", str(_LINA_DIR / "models" / "vosk")))
HISTORY_DIR: Path = Path(_env("HISTORY_DIR", str(_LINA_DIR / "history")))
LOG_DIR: Path     = Path(_env("LOG_DIR",     str(_LINA_DIR / "logs")))
OWW_MODEL_DIR: Path = _LINA_DIR / "models" / "oww"

# Derived piper model file, resolved from the directory + voice name
PIPER_VOICE: str = _env("PIPER_VOICE", "en_US-amy-medium")
PIPER_ONNX_PATH: Path = PIPER_MODEL_PATH / f"{PIPER_VOICE}.onnx"
PIPER_JSON_PATH: Path = PIPER_MODEL_PATH / f"{PIPER_VOICE}.onnx.json"

# ── History ───────────────────────────────────────────────────────────────────
HISTORY_RETENTION_DAYS: int = _env_int("HISTORY_RETENTION_DAYS", 7)

# ── Wake word ─────────────────────────────────────────────────────────────────
# NOTE: openWakeWord only ships a set of pretrained model names.
# Set WAKE_WORD to one of the available built-in names:
#   "alexa", "hey_jarvis", "hey_mycroft", "ok_nabu", "hey_rhasspy"
# OR set it to an absolute path to a custom .onnx model file.
# DISPLAY_WAKE_PHRASE is shown in the UI and spoken by LINA.
ENABLE_WAKE_WORD: bool  = _env_bool("ENABLE_WAKE_WORD", True)
WAKE_WORD: str          = _env("WAKE_WORD", "hey_jarvis")        # must be a valid OWW model name
DISPLAY_WAKE_PHRASE: str = _env("DISPLAY_WAKE_PHRASE", "Hey LINA")  # what the user says / UI shows
OWW_THRESHOLD: float    = _env_float("OWW_THRESHOLD", 0.5)

# ── Security / behaviour ──────────────────────────────────────────────────────
PARANOID_MODE: bool = _env_bool("PARANOID_MODE", False)
AUDIT_MODE: bool    = _env_bool("AUDIT_MODE", True)
ENABLE_NETWORK_COMMANDS: bool = _env_bool("ENABLE_NETWORK_COMMANDS", True)
ENABLE_FILE_COMMANDS: bool    = _env_bool("ENABLE_FILE_COMMANDS", True)
ENABLE_SYSTEM_COMMANDS: bool  = _env_bool("ENABLE_SYSTEM_COMMANDS", True)

# ── Audio / recording ─────────────────────────────────────────────────────────
SAMPLE_RATE: int               = 16_000   # Hz — required by Whisper & webrtcvad
CHANNELS: int                  = 1
VAD_AGGRESSIVENESS: int        = _env_int("VAD_AGGRESSIVENESS", 2)   # 0–3
MAX_RECORDING_SECONDS: float   = _env_float("MAX_RECORDING_SECONDS", 10.0)
SILENCE_THRESHOLD_SECONDS: float = _env_float("SILENCE_THRESHOLD_SECONDS", 1.5)

# ── LLM models ────────────────────────────────────────────────────────────────
CLAUDE_MODEL: str = _env("CLAUDE_MODEL", "claude-haiku-4-5")
GROQ_MODEL: str   = _env("GROQ_MODEL",   "llama-3.1-8b-instant")

# ── App info ──────────────────────────────────────────────────────────────────
APP_NAME: str = "LINA"
VERSION: str  = "3.0.0"

# ── Auto-create required directories ─────────────────────────────────────────
def _makedirs() -> None:
    for d in (PIPER_MODEL_PATH, VOSK_FALLBACK_MODEL, HISTORY_DIR, LOG_DIR, OWW_MODEL_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


_makedirs()

# ── Validate config ───────────────────────────────────────────────────────────
def validate_config() -> tuple[bool, list[str]]:
    """
    Check that critical settings are present and coherent.
    Returns (is_valid: bool, errors: list[str]).
    An app can start with warnings, but errors are shown in the UI.
    """
    errors: list[str] = []

    if not ANTHROPIC_API_KEY and not GROQ_API_KEY:
        errors.append("No LLM API key set — add ANTHROPIC_API_KEY or GROQ_API_KEY to .env")

    if ANTHROPIC_API_KEY and not ANTHROPIC_API_KEY.startswith("sk-ant-"):
        errors.append("ANTHROPIC_API_KEY looks invalid (should start with 'sk-ant-')")

    if not PIPER_ONNX_PATH.exists():
        errors.append(
            f"Piper voice model not found: {PIPER_ONNX_PATH}\n"
            "  Run: bash install_models.sh"
        )

    if MAX_RECORDING_SECONDS < 1 or MAX_RECORDING_SECONDS > 60:
        errors.append(f"MAX_RECORDING_SECONDS={MAX_RECORDING_SECONDS} is out of range [1–60]")

    if VAD_AGGRESSIVENESS not in (0, 1, 2, 3):
        errors.append(f"VAD_AGGRESSIVENESS={VAD_AGGRESSIVENESS} must be 0, 1, 2, or 3")

    return (len(errors) == 0), errors


# ── LLM Prompt Templates ──────────────────────────────────────────────────────

BASH_GENERATION_PROMPT: str = """\
You are LINA, an intelligent AI assistant built into a Linux voice interface.
The user is running: {distro}

Your task is to convert the user's natural language command into a safe, \
valid bash script that can be executed on their system.

Strict rules:
1. Respond ONLY with a valid JSON object — no markdown, no explanation, no code fences.
2. The JSON must have exactly these two keys:
   - "bash_script": a safe, single-line or multi-line bash snippet
   - "description": a short, friendly one-sentence explanation (max 15 words)
3. NEVER generate scripts containing: rm -rf /, mkfs, dd, sudo, shutdown, \
reboot, halt, passwd, useradd, userdel, iptables, or writes to /dev/sd*.
4. Prefer read-only commands where possible. Avoid destructive operations.
5. Use standard GNU/Linux tools (ls, grep, awk, sed, df, free, ip, etc.).
6. If the request is unclear or unsafe, set "bash_script" to "echo 'I cannot do that safely.'"

Example output (you must match this format exactly):
{{
  "bash_script": "df -h | grep -v tmpfs",
  "description": "Shows disk usage for all mounted drives."
}}

User command: {query}
"""

OUTPUT_INTERPRETATION_PROMPT: str = """\
You are LINA, a friendly and concise Linux voice assistant.

The user said: "{query}"
The command produced this output:
---
{output}
---

Explain what happened in 1–2 short, plain sentences as if speaking aloud — \
no markdown, no bullet points, no technical jargon. \
Start directly with the result (e.g. "Your disk is 45% full." or "Firefox is now open.").
If the output is empty or blank, say "The command ran successfully with no output."
"""
