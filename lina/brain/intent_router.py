"""
LINA v3 — Intent Router
Fast-path intent matching that bypasses the LLM for common commands.
Uses exact match → fuzzy match (difflib) → falls through to LLM.
"""

import difflib
import logging
import re
import shutil
import subprocess

log = logging.getLogger(__name__)

# ── Special sentinel values ────────────────────────────────────────────────────
INTENT_HELP         = "__HELP__"
INTENT_HISTORY      = "__SHOW_HISTORY__"
INTENT_SSH_STATUS   = "__SSH_STATUS__"
INTENT_WEATHER      = "__WEATHER__"
INTENT_TIMEZONE     = "__TIMEZONE__"
INTENT_PKG_CHECK    = "__PKG_CHECK__"
INTENT_PKG_VERSION  = "__PKG_VERSION__"
INTENT_LLM_FALLBACK = "__LLM__"   # signal to CommandProcessor to call the LLM

# ── Intent map: phrase → bash command or sentinel ─────────────────────────────
INTENT_MAP: dict[str, str] = {
    # Apps
    "open terminal":       "gnome-terminal &",
    "launch terminal":     "gnome-terminal &",
    "start terminal":      "gnome-terminal &",
    "open browser":        "firefox &",
    "open firefox":        "firefox &",
    "open chrome":         "google-chrome &",
    "open files":          "nautilus &",
    "open file manager":   "nautilus &",
    "open calculator":     "gnome-calculator &",

    # Network
    "what is my ip":       "ip -4 addr show scope global | grep -oE '[0-9]+(\\.[0-9]+){3}' | head -n1",
    "show ip":             "ip -4 addr show scope global | grep -oE '[0-9]+(\\.[0-9]+){3}' | head -n1",
    "current ip":          "ip -4 addr show scope global | grep -oE '[0-9]+(\\.[0-9]+){3}' | head -n1",

    # Files
    "list files":          "ls",
    "show files":          "ls",
    "show current folder": "pwd",
    "where am i":          "pwd",

    # Time
    "current time":        "date",
    "time now":            "date",
    "what time is it":     "date",

    # System health
    "battery status":      "upower -i $(upower -e | grep BAT | head -n1)",
    "cpu temperature":     "sensors | grep -E 'temp'",
    "fan speed":           "sensors | grep -i fan",
    "network status":      "ip -br addr && ip route",
    "storage health":      "lsblk -o NAME,SIZE,TYPE,MOUNTPOINT",
    "disk usage":          "df -h",
    "memory usage":        "free -h",
    "top memory processes":"ps -eo pid,comm,%mem --sort=-%mem | head -n10",
    "top cpu processes":   "ps -eo pid,comm,%cpu --sort=-%cpu | head -n10",
    "find large files":    "du -ah . | sort -rh | head -n20",
    "uptime":              "uptime -p",

    # Media (MPRIS)
    "pause music":         "playerctl pause",
    "play music":          "playerctl play",
    "next track":          "playerctl next",
    "previous track":      "playerctl previous",

    # Sentinels
    "what can you do":     INTENT_HELP,
    "help":                INTENT_HELP,
    "show history":        INTENT_HISTORY,
    "command history":     INTENT_HISTORY,
    "history":             INTENT_HISTORY,
    "is ssh running":      INTENT_SSH_STATUS,
    "ssh status":          INTENT_SSH_STATUS,
    "check ssh":           INTENT_SSH_STATUS,
    "weather":             INTENT_WEATHER,
    "timezone":            INTENT_TIMEZONE,
    "is package installed":INTENT_PKG_CHECK,
    "package version":     INTENT_PKG_VERSION,
}

# ── ASR mishear / noisy-speech heuristics ─────────────────────────────────────
_HEURISTICS: dict[str, str] = {
    "least five":           "list files",
    "list five":            "list files",
    "what the current site":"current ip",
    "open browse":          "open browser",
    "open file":            "open files",
    "current time now":     "current time",
}

# ── App fallback table (for multi-DE support) ─────────────────────────────────
APP_FALLBACKS: dict[str, list[str]] = {
    "terminal":   ["gnome-terminal", "kgx", "x-terminal-emulator", "konsole",
                   "xfce4-terminal", "tilix", "mate-terminal"],
    "browser":    ["firefox", "google-chrome", "chromium"],
    "files":      ["nautilus", "nemo", "dolphin", "thunar"],
    "calculator": ["gnome-calculator", "kcalc", "galculator", "qalculate-gtk"],
}

# ── Slot-filling regex ────────────────────────────────────────────────────────
_RE_MKDIR = re.compile(r"^(make|create)\s+(directory|folder)\s+([A-Za-z0-9._-]{1,64})$")


class IntentRouter:
    """
    Routes a normalised text command to a bash snippet, sentinel, or INTENT_LLM_FALLBACK.

    Returns:
        (intent_key: str, value: str)
        where value is a bash command, sentinel constant, or INTENT_LLM_FALLBACK.
    """

    def route(self, raw_text: str) -> tuple[str, str]:
        normalized = " ".join(raw_text.lower().split())

        # 1 — Heuristics (known ASR mishears)
        if normalized in _HEURISTICS:
            normalized = _HEURISTICS[normalized]

        # 2 — Exact match
        if normalized in INTENT_MAP:
            return normalized, INTENT_MAP[normalized]

        # 3 — Fuzzy match (difflib cutoff 0.78)
        known = list(INTENT_MAP.keys())
        matches = difflib.get_close_matches(normalized, known, n=1, cutoff=0.78)
        if matches:
            key = matches[0]
            return key, INTENT_MAP[key]

        # 4 — Slot: mkdir / create folder
        m = _RE_MKDIR.match(normalized)
        if m:
            dirname = m.group(3)
            return "mkdir", f"mkdir '{dirname}'"

        # 5 — Search
        if normalized.startswith("search for "):
            query = normalized[11:].strip().replace(" ", "+")
            return "search", f"xdg-open 'https://www.google.com/search?q={query}'"

        # 6 — Falls through to LLM
        return "llm", INTENT_LLM_FALLBACK

    @staticmethod
    def which_first(candidates: list[str]) -> str | None:
        """Return the first candidate that exists on PATH."""
        for app in candidates:
            if shutil.which(app):
                return app
        return None

    @staticmethod
    def launch_gui(app: str) -> tuple[bool, str]:
        """Non-blocking GUI app launch."""
        try:
            subprocess.Popen([app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, f"Launched {app}"
        except Exception as exc:
            return False, str(exc)
