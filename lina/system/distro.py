"""
LINA v3 — Distro Detection
Reads /etc/os-release to identify the running Linux distribution.
"""

import logging

log = logging.getLogger(__name__)


def detect_distro() -> str:
    """
    Returns PRETTY_NAME from /etc/os-release, e.g. 'Ubuntu 22.04.3 LTS'.
    Falls back to 'Linux' if the file is missing or unreadable.
    """
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception as exc:
        log.debug("Could not read /etc/os-release: %s", exc)
    return "Linux"
