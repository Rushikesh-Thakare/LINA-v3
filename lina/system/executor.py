"""
LINA v3 — Sandbox Executor
Runs validated bash scripts safely.
Uses firejail if available, plain bash otherwise.
Handles GUI app detection (no sandbox for GUI processes).
"""

import hashlib
import logging
import os
import subprocess
import tempfile

from lina.config import AUDIT_MODE, PARANOID_MODE

log = logging.getLogger(__name__)

_GUI_APPS = frozenset([
    "gnome-terminal", "firefox", "google-chrome", "chromium",
    "nautilus", "nemo", "dolphin", "thunar",
    "gnome-calculator", "kcalc", "galculator",
])


class Executor:
    """
    Runs a validated bash script in a sandbox.
    Returns the stdout/stderr as a string.
    """

    def run(self, script: str) -> str:
        """
        Execute script and return its output.
        PARANOID_MODE is handled at the UI layer before this is called.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as tmp:
            tmp.write(script)
            tmp_path = tmp.name

        try:
            # Detect GUI launches — skip firejail for them
            launches_gui = any(app in script for app in _GUI_APPS)
            if launches_gui:
                subprocess.Popen(
                    ["bash", tmp_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return "Launched GUI application."

            # Use firejail if available
            if subprocess.call(
                ["which", "firejail"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ) == 0:
                result = subprocess.run(
                    ["firejail", "--noprofile", "--quiet", "--private", "--net=none",
                     "--nosound", "--no3d", "bash", tmp_path],
                    capture_output=True, text=True, timeout=30,
                )
            else:
                log.debug("firejail not found — running without sandbox.")
                result = subprocess.run(
                    ["bash", tmp_path],
                    capture_output=True, text=True, timeout=30,
                )

            output = result.stdout if result.returncode == 0 else result.stderr or result.stdout

            if AUDIT_MODE:
                h_s = hashlib.sha256(script.encode()).hexdigest()[:12]
                h_o = hashlib.sha256((output or "").encode()).hexdigest()[:12]
                log.info("[audit] script=%s output=%s rc=%d", h_s, h_o, result.returncode)

            return output or ""

        except subprocess.TimeoutExpired:
            log.warning("Script timed out.")
            return "Command timed out after 30 seconds."
        except Exception as exc:
            log.exception("Executor error: %s", exc)
            return f"Execution error: {exc}"
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
