"""
LINA v3 — Execution Sandbox
Handles safe bash script execution using firejail (if available).
Also provides GUI app and URL launching functionality.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def output(self) -> str:
        """Combined stdout/stderr, trimmed."""
        combined = f"{self.stdout}\n{self.stderr}".strip()
        return combined if combined else ("(No output)" if self.success else "(Failed with no output)")


class ScriptExecutor:
    """
    Executes bash scripts in a safe, sandboxed environment.
    Falls back to raw bash if firejail is not installed.
    """

    def __init__(self):
        self._has_firejail = shutil.which("firejail") is not None
        if self._has_firejail:
            log.info("Firejail found — sandboxing enabled.")
        else:
            log.warning("Firejail not found — running scripts natively in bash.")

    def run_shell(self, script: str, timeout: int = 10) -> ExecutionResult:
        """
        Run a bash snippet securely.
        Writes to a tempfile, executes, and cleans up.
        """
        temp_path = ""
        try:
            fd, temp_path = tempfile.mkstemp(prefix="lina_script_", suffix=".sh")
            with os.fdopen(fd, "w") as f:
                # Add set -e for safer execution
                f.write("#!/bin/bash\nset -e\n" + script)
            
            os.chmod(temp_path, 0o700)

            if self._has_firejail:
                # Minimal sandbox: no profile, private /tmp, no network by default, no sound
                cmd = [
                    "firejail", 
                    "--noprofile", 
                    "--quiet", 
                    "--private", 
                    "--net=none", 
                    "--nosound", 
                    "bash", temp_path
                ]
            else:
                cmd = ["bash", temp_path]

            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return ExecutionResult(
                stdout=process.stdout,
                stderr=process.stderr,
                returncode=process.returncode,
                timed_out=False,
            )

        except subprocess.TimeoutExpired as exc:
            log.error("Script timed out after %ds", timeout)
            return ExecutionResult(
                stdout=exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                stderr=exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
                returncode=-1,
                timed_out=True,
            )
        except Exception as exc:
            log.exception("Execution failed unexpectedly: %s", exc)
            return ExecutionResult(
                stdout="",
                stderr=str(exc),
                returncode=-2,
                timed_out=False,
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def launch_gui(self, app: str) -> bool:
        """
        Launch a GUI application detached from the main process.
        """
        if not shutil.which(app):
            return False
            
        try:
            subprocess.Popen(
                [app],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except Exception as exc:
            log.error("Failed to launch GUI app %s: %s", app, exc)
            return False

    def open_url(self, url: str) -> bool:
        """
        Open a URL in the default browser.
        """
        cmd = shutil.which("xdg-open")
        if not cmd:
            log.error("xdg-open not found.")
            return False
            
        try:
            subprocess.Popen(
                [cmd, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except Exception as exc:
            log.error("Failed to open URL %s: %s", url, exc)
            return False
