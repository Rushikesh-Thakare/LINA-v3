"""
LINA v3 — Script Validator
Checks AI-generated bash scripts for dangerous patterns before execution.
This is a hard security gate — script is NEVER executed if validation fails.

Blocked patterns (per Gemini.md): rm -rf /, mkfs, dd, sudo, shutdown, reboot.
"""

import logging
import re

log = logging.getLogger(__name__)

# ── Dangerous bash patterns ────────────────────────────────────────────────────
_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+-rf\s+\/",              "rm -rf /"),
    (r"rm\s+-rf\s+--no-preserve-root", "rm -rf --no-preserve-root"),
    (r"\bmkfs\b",                   "mkfs (format disk)"),
    (r"\bdd\s+if=",                 "dd (raw disk write)"),
    (r"chmod\s+777\s+\/",           "chmod 777 /"),
    (r"\bchown\s+root",             "chown root"),
    (r"\buseradd\b",                "useradd"),
    (r"\buserdel\b",                "userdel"),
    (r"\bpasswd\b",                 "passwd"),
    (r"\bmount\s",                  "mount"),
    (r"\bumount\s",                 "umount"),
    (r"systemctl\s+stop\s",         "systemctl stop"),
    (r"\bshutdown\b",               "shutdown"),
    (r"\breboot\b",                 "reboot"),
    (r"\bhalt\b",                   "halt"),
    (r"kill\s+-9\s+1\b",            "kill -9 PID 1 (init)"),
    (r"\bpkill\s+-9\b",             "pkill -9"),
    (r"\biptables\b",               "iptables"),
    (r"\bfirewall-cmd\b",           "firewall-cmd"),
    (r"\bsudo\b",                   "sudo"),
    (r">/dev/sd",                   "write to block device"),
    (r">/dev/nvme",                 "write to NVMe device"),
    (r"\bcryptsetup\b",             "cryptsetup"),
    (r":\(\)\s*\{.*\}.*:",          "fork bomb"),
    (r"base64\s+-d.*\|.*sh",        "base64 decode to shell"),
    (r"curl.*\|.*sh",               "curl pipe to shell"),
    (r"wget.*-O.*-.*sh",            "wget pipe to shell"),
]


class ScriptValidator:
    """
    Validates AI-generated bash scripts.
    Returns (is_safe: bool, reason: str).
    """

    def validate(self, script: str) -> tuple[bool, str]:
        """
        Run all safety checks.
        Returns (True, "ok") if safe, (False, reason) if blocked.
        """
        if not script or len(script.strip()) < 2:
            return False, "Script is empty or too short."

        for pattern, label in _DANGEROUS_PATTERNS:
            if re.search(pattern, script, flags=re.IGNORECASE):
                reason = f"Blocked: dangerous pattern detected → '{label}'"
                log.warning("Validator blocked script: %s", reason)
                return False, reason

        log.debug("Script passed validation.")
        return True, "ok"
