"""
LINA v3 — Linux Distro Detection
Provides accurate distribution, version, and component information
to give the LLM better bash-generation context.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class DistroInfo:
    name: str
    id: str
    version: str
    package_manager: str
    desktop_env: str
    
    def __str__(self) -> str:
        return f"{self.name} ({self.desktop_env}, {self.package_manager})"


def detect_distro() -> DistroInfo:
    """
    Parses /etc/os-release and env vars to build a DistroInfo object.
    Never fails; provides sensible fallbacks.
    """
    # ── 1. OS Release ──
    os_name = "Linux"
    os_id = "linux"
    os_version = "Unknown"
    
    try:
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release", "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                        
                    if "=" not in line:
                        continue
                        
                    key, val = line.split("=", 1)
                    val = val.strip("\"'")
                    
                    if key == "PRETTY_NAME":
                        os_name = val
                    elif key == "ID":
                        os_id = val.lower()
                    elif key == "VERSION_ID":
                        os_version = val
    except Exception as exc:
        log.warning("Could not read /etc/os-release: %s", exc)

    # ── 2. Package Manager ──
    pm = "unknown"
    if shutil.which("apt"):
        pm = "apt"
    elif shutil.which("dnf"):
        pm = "dnf"
    elif shutil.which("pacman"):
        pm = "pacman"
    elif shutil.which("zypper"):
        pm = "zypper"
    elif shutil.which("apk"):
        pm = "apk"
    elif shutil.which("emerge"):
        pm = "emerge"
    elif os_id in ("ubuntu", "debian", "pop", "linuxmint", "elementary"):
        pm = "apt"
    elif os_id in ("fedora", "centos", "rhel", "rocky", "almalinux"):
        pm = "dnf"
    elif os_id in ("arch", "manjaro", "endeavouros"):
        pm = "pacman"

    # ── 3. Desktop Environment ──
    de = (
        os.environ.get("XDG_CURRENT_DESKTOP") 
        or os.environ.get("DESKTOP_SESSION") 
        or os.environ.get("SWAYSOCK") and "Sway"
        or os.environ.get("WAYLAND_DISPLAY") and "Wayland"
        or "Unknown DE/Headless"
    )
    
    # Clean up DE names (e.g. "ubuntu:GNOME" -> "GNOME")
    if de and ":" in de:
        de = de.split(":")[-1]

    info = DistroInfo(
        name=os_name,
        id=os_id,
        version=os_version,
        package_manager=pm,
        desktop_env=de
    )
    
    log.debug("Detected distro: %s", info)
    return info
