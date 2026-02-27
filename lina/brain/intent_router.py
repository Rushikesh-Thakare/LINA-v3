"""
LINA v3 — Intent Router
Fast-path command matching that bypasses the LLM for well-known phrases.

Matching order (first match wins):
  1. EXACT_MATCH   — O(1) dict lookup, lowercased + stripped
  2. REGEX_MATCH   — parameterised patterns (mkdir, search, open URL…)
  3. FUZZY_MATCH   — difflib.get_close_matches with cutoff=0.78
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Any, Optional
from urllib.parse import quote_plus


# ── IntentMatch dataclass ─────────────────────────────────────────────────────

@dataclass
class IntentMatch:
    intent_name: str
    action: str                         # launch_app | shell_command | open_url | show_help | …
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0             # 1.0 = exact, 0.78–0.99 = fuzzy


# ── Helpers ───────────────────────────────────────────────────────────────────

def _which_first(*candidates: str) -> str:
    """Return the first app from candidates found in PATH, or the last as fallback."""
    for app in candidates:
        if shutil.which(app):
            return app
    return candidates[-1]


def _app(*candidates: str) -> dict:
    return {"app": _which_first(*candidates)}


def _cmd(command: str) -> dict:
    return {"cmd": command}


def _url(u: str) -> dict:
    return {"url": u}


# ── EXACT_MATCH table ─────────────────────────────────────────────────────────
# Keys: lowercase stripped phrases.
# Values: (action, params_dict)

_EXACT: dict[str, tuple[str, dict]] = {

    # ── App launching ──────────────────────────────────────────────────────────
    "open terminal":    ("launch_app", _app("gnome-terminal", "konsole", "xfce4-terminal", "tilix")),
    "open browser":     ("launch_app", _app("firefox", "google-chrome", "chromium")),
    "open files":       ("launch_app", _app("nautilus", "dolphin", "thunar", "nemo")),
    "open file manager":("launch_app", _app("nautilus", "dolphin", "thunar", "nemo")),
    "open calculator":  ("launch_app", _app("gnome-calculator", "kcalc", "galculator")),
    "open text editor": ("launch_app", _app("gedit", "kate", "mousepad", "xed", "nano")),
    "open settings":    ("launch_app", _app("gnome-control-center", "systemsettings", "xfce4-settings-manager")),

    # ── System info ────────────────────────────────────────────────────────────
    "what time is it":  ("shell_command", _cmd("date '+%H:%M, %A %d %B %Y'")),
    "current time":     ("shell_command", _cmd("date '+%H:%M, %A %d %B %Y'")),
    "what date is it":  ("shell_command", _cmd("date '+%A, %d %B %Y'")),
    "what is my ip":    ("shell_command", _cmd("ip -4 addr show scope global | grep -oE '[0-9]+(\\.[0-9]+){3}' | head -n1")),
    "my ip address":    ("shell_command", _cmd("ip -4 addr show scope global | grep -oE '[0-9]+(\\.[0-9]+){3}' | head -n1")),
    "list files":       ("shell_command", _cmd("ls -la")),
    "show files":       ("shell_command", _cmd("ls -la")),
    "show disk space":  ("shell_command", _cmd("df -h")),
    "disk usage":       ("shell_command", _cmd("df -h")),
    "show memory":      ("shell_command", _cmd("free -h")),
    "memory usage":     ("shell_command", _cmd("free -h")),
    "battery status":   ("shell_command", _cmd("upower -i $(upower -e | grep BAT | head -n1) 2>/dev/null || cat /sys/class/power_supply/BAT*/capacity 2>/dev/null | head -n1")),
    "cpu temperature":  ("shell_command", _cmd("sensors 2>/dev/null | grep -E 'temp|Core' || cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | awk '{print $1/1000 \"°C\"}'")),
    "who am i":         ("shell_command", _cmd("whoami")),
    "whoami":           ("shell_command", _cmd("whoami")),
    "network status":   ("shell_command", _cmd("ip -br addr")),
    "show processes":   ("shell_command", _cmd("ps aux --sort=-%cpu | head -15")),
    "top processes":    ("shell_command", _cmd("ps aux --sort=-%cpu | head -10")),
    "uptime":           ("shell_command", _cmd("uptime -p")),
    "system uptime":    ("shell_command", _cmd("uptime -p")),
    "hostname":         ("shell_command", _cmd("hostname")),
    "show hostname":    ("shell_command", _cmd("hostname")),
    "kernel version":   ("shell_command", _cmd("uname -r")),

    # ── Media ──────────────────────────────────────────────────────────────────
    "pause music":      ("shell_command", _cmd("playerctl pause 2>/dev/null || echo 'No media player found'")),
    "play music":       ("shell_command", _cmd("playerctl play 2>/dev/null || echo 'No media player found'")),
    "stop music":       ("shell_command", _cmd("playerctl stop 2>/dev/null || echo 'No media player found'")),
    "next track":       ("shell_command", _cmd("playerctl next 2>/dev/null || echo 'No media player found'")),
    "previous track":   ("shell_command", _cmd("playerctl previous 2>/dev/null || echo 'No media player found'")),
    "mute":             ("shell_command", _cmd("pactl set-sink-mute @DEFAULT_SINK@ toggle")),
    "volume up":        ("shell_command", _cmd("pactl set-sink-volume @DEFAULT_SINK@ +10%")),
    "volume down":      ("shell_command", _cmd("pactl set-sink-volume @DEFAULT_SINK@ -10%")),
    "increase volume":  ("shell_command", _cmd("pactl set-sink-volume @DEFAULT_SINK@ +10%")),
    "decrease volume":  ("shell_command", _cmd("pactl set-sink-volume @DEFAULT_SINK@ -10%")),

    # ── Screenshots ────────────────────────────────────────────────────────────
    "take screenshot":  ("shell_command", _cmd("scrot ~/Desktop/screenshot_$(date +%F_%T).png 2>/dev/null || gnome-screenshot 2>/dev/null")),

    # ── Web ────────────────────────────────────────────────────────────────────
    "open youtube":     ("open_url", _url("https://www.youtube.com")),
    "open google":      ("open_url", _url("https://www.google.com")),
    "open github":      ("open_url", _url("https://www.github.com")),
    "open gmail":       ("open_url", _url("https://mail.google.com")),
    "open maps":        ("open_url", _url("https://maps.google.com")),
    "open reddit":      ("open_url", _url("https://www.reddit.com")),
    "open wikipedia":   ("open_url", _url("https://www.wikipedia.org")),
    "open netflix":     ("open_url", _url("https://www.netflix.com")),
    "open spotify":     ("open_url", _url("https://open.spotify.com")),
    "open twitter":     ("open_url", _url("https://www.twitter.com")),
    "open linkedin":    ("open_url", _url("https://www.linkedin.com")),

    # ── LINA meta ──────────────────────────────────────────────────────────────
    "what can you do":  ("show_help",    {}),
    "help":             ("show_help",    {}),
    "lina help":        ("show_help",    {}),
    "show help":        ("show_help",    {}),
    "show history":     ("show_history", {}),
    "command history":  ("show_history", {}),
    "clear terminal":   ("clear_terminal", {}),
    "clear screen":     ("clear_terminal", {}),
}


# ── REGEX_MATCH table ─────────────────────────────────────────────────────────
# Each entry: (compiled pattern, intent_name, builder_fn(match) → params, confidence)

def _regex_params_mkdir(m: re.Match) -> dict:
    return {"cmd": f"mkdir -p ~/{m.group(3)}"}

def _regex_params_search(m: re.Match) -> dict:
    return {"url": f"https://www.google.com/search?q={quote_plus(m.group(1))}"}

def _regex_params_open_domain(m: re.Match) -> dict:
    domain = m.group(1)
    prefix = "" if domain.startswith(("http://", "https://")) else "https://"
    return {"url": f"{prefix}{domain}"}

def _regex_params_service_status(m: re.Match) -> dict:
    return {"cmd": f"systemctl is-active {m.group(1)}"}

def _regex_params_version(m: re.Match) -> dict:
    return {"cmd": f"{m.group(3)} --version 2>&1 | head -1"}

def _regex_params_youtube(m: re.Match) -> dict:
    return {"url": f"https://www.youtube.com/results?search_query={quote_plus(m.group(1))}"}


_REGEX: list[tuple[re.Pattern, str, str, Any]] = [
    # (pattern, intent_name, action, params_builder)
    (re.compile(r"^(make|create)\s+(directory|folder)\s+([A-Za-z0-9._-]{1,64})$", re.I),
     "make_directory", "shell_command", _regex_params_mkdir),

    (re.compile(r"^search\s+(?:for\s+)?(.+)$", re.I),
     "web_search", "open_url", _regex_params_search),

    (re.compile(r"^play\s+(.+)\s+on\s+youtube$", re.I),
     "youtube_search", "open_url", _regex_params_youtube),

    (re.compile(r"^open\s+([\w.-]+\.(?:com|org|net|io|dev|app|ai))(?:/\S*)?$", re.I),
     "open_website", "open_url", _regex_params_open_domain),

    (re.compile(r"^is\s+(.+?)\s+running$", re.I),
     "service_status", "shell_command", _regex_params_service_status),

    (re.compile(r"^(?:what\s+is|show)\s+(?:version\s+of|version)\s+(.+)$", re.I),
     "app_version", "shell_command", _regex_params_version),
]


# ══════════════════════════════════════════════════════════════════════════════
# IntentRouter
# ══════════════════════════════════════════════════════════════════════════════

class IntentRouter:
    """
    Three-strategy intent router.
    Call match(text) → IntentMatch or None.
    Returns None when no intent is confident enough → CommandProcessor falls
    through to the LLM.
    """

    FUZZY_CUTOFF = 0.78
    _exact_keys  = list(_EXACT.keys())

    def match(self, text: str) -> Optional[IntentMatch]:
        normalised = text.strip().lower()

        # 1) Exact match ───────────────────────────────────────────────────────
        if normalised in _EXACT:
            action, params = _EXACT[normalised]
            return IntentMatch(
                intent_name=normalised,
                action=action,
                params=dict(params),     # copy so callers can modify
                confidence=1.0,
            )

        # 2) Regex match ────────────────────────────────────────────────────────
        for pattern, intent_name, action, builder in _REGEX:
            m = pattern.match(normalised)
            if m:
                return IntentMatch(
                    intent_name=intent_name,
                    action=action,
                    params=builder(m),
                    confidence=0.95,
                )

        # 3) Fuzzy match ────────────────────────────────────────────────────────
        close = get_close_matches(normalised, self._exact_keys, n=1, cutoff=self.FUZZY_CUTOFF)
        if close:
            best_key = close[0]
            action, params = _EXACT[best_key]
            return IntentMatch(
                intent_name=best_key,
                action=action,
                params=dict(params),
                confidence=0.80,
            )

        return None


# ── Legacy INTENT_MAP alias (keeps autocomplete in main_window.py working) ───
INTENT_MAP: dict[str, str] = {k: v[0] for k, v in _EXACT.items()}
