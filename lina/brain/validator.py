"""
LINA v3 — Script Safety Validator
Multi-level risk assessment for AI-generated bash scripts.

Risk levels (ascending danger):
  SAFE      → allow silently
  LOW_RISK  → allow + log warning
  HIGH_RISK → allow + emit warning (UI can require confirmation)
  BLOCKED   → reject, never execute
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


# ── Risk levels ───────────────────────────────────────────────────────────────

class RiskLevel(Enum):
    SAFE      = "safe"
    LOW_RISK  = "low_risk"
    HIGH_RISK = "high_risk"
    BLOCKED   = "blocked"


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    is_safe:        bool         # False only when BLOCKED
    blocked_reason: str          # Human-readable reason if not safe, else ""
    risk_level:     RiskLevel


_OK    = ValidationResult(is_safe=True,  blocked_reason="", risk_level=RiskLevel.SAFE)
_WARN  = ValidationResult(is_safe=True,  blocked_reason="", risk_level=RiskLevel.LOW_RISK)


# ── Pattern tables ────────────────────────────────────────────────────────────

# BLOCKED — always rejected, no exceptions
_BLOCKED_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|--force\s+)?-[a-zA-Z]*r[a-zA-Z]*\s+[/\"']*\s*[\"']?\s*$", re.I),
     "Recursive delete on root (rm -rf /)"),
    (re.compile(r"rm\s+.*--no-preserve-root", re.I),
     "Dangerous rm with --no-preserve-root"),
    (re.compile(r"\bmkfs\b", re.I),
     "Disk formatting (mkfs) is not allowed"),
    (re.compile(r"\bdd\b.*\bif\s*=", re.I),
     "Raw disk operation (dd) is not allowed"),
    (re.compile(r">\s*/dev/(sd[a-z]|nvme|hd[a-z])", re.I),
     "Writing directly to block device is not allowed"),
    (re.compile(r"\bcryptsetup\b", re.I),
     "Disk encryption commands are not allowed"),
    (re.compile(r"\bchmod\s+777\s+/\b", re.I),
     "Changing root permissions is not allowed"),
    (re.compile(r"\b(useradd|userdel|usermod|groupadd|groupdel)\b", re.I),
     "User/group management is not allowed"),
    (re.compile(r"\bpasswd\b", re.I),
     "Password changes are not allowed"),
    (re.compile(r"\b(shutdown|reboot|halt|poweroff|init\s+0|init\s+6)\b", re.I),
     "System shutdown/reboot is not allowed"),
    (re.compile(r"\bkill\s+(-9\s+)?1\b", re.I),
     "Killing PID 1 (init/systemd) is not allowed"),
    # Remote code execution
    (re.compile(r"(curl|wget)\s+.*\|\s*(ba?sh|sh|python|perl|ruby|php)", re.I),
     "Piping remote content to a shell is not allowed (remote code execution)"),
    (re.compile(r"\beval\s*[\$\`\"']", re.I),
     "eval with variable/command content is not allowed"),
    (re.compile(r"base64\s+(-d|--decode).*\|\s*(ba?sh|sh)", re.I),
     "Decoding and running base64-encoded code is not allowed"),
    # Fork bomb
    (re.compile(r":\(\)\{.*\|.*:&\s*\}", re.I),
     "Fork bomb pattern detected"),
    # History/logging suppression
    (re.compile(r"unset\s+HISTFILE|HISTSIZE\s*=\s*0", re.I),
     "Disabling shell history is not allowed"),
]

# HIGH_RISK — allowed but emit warning
_HIGH_RISK_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bsudo\b", re.I),
     "Command uses sudo (elevated privileges)"),
    (re.compile(r"\bsystemctl\s+(stop|disable|mask|kill)\b", re.I),
     "Stopping/disabling a system service"),
    (re.compile(r"\brm\s+.*-[a-zA-Z]*r[a-zA-Z]*", re.I),
     "Recursive delete (rm -r)"),
    (re.compile(r"\b(pip|pip3|pip2)\s+install\b", re.I),
     "Installing Python packages"),
    (re.compile(r"\b(apt|apt-get|dnf|yum|pacman|zypper)\s+(install|remove|purge)\b", re.I),
     "System package installation/removal"),
    (re.compile(r"\bchmod\b.*[0-7]{3}", re.I),
     "Changing file permissions"),
    (re.compile(r"\bchown\b", re.I),
     "Changing file ownership"),
    (re.compile(r"\bmv\b.*(/etc|/usr|/boot|/lib)\b", re.I),
     "Moving files in protected system directories"),
    (re.compile(r"\bnohup\b|\bdisown\b", re.I),
     "Running process detached from terminal"),
]

# LOW_RISK — allowed, logged
_LOW_RISK_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(curl|wget|ping|nc|ncat|netcat)\b", re.I),
     "Network access command"),
    (re.compile(r">>?\s*/(?!dev/null)", re.I),
     "File write/append operation"),
    (re.compile(r"\bssh\b", re.I),
     "SSH connection"),
    (re.compile(r"\bscp\b|\brsync\b", re.I),
     "Remote file transfer"),
]

# Max script length — prevents prompt injection abuse
_MAX_SCRIPT_CHARS = 500


# ══════════════════════════════════════════════════════════════════════════════
# ScriptValidator
# ══════════════════════════════════════════════════════════════════════════════

class ScriptValidator:
    """
    Validates AI-generated bash scripts before execution.

    Usage:
        result = ScriptValidator().validate(script)
        if not result.is_safe:
            speak(result.blocked_reason)
            return
        if result.risk_level == RiskLevel.HIGH_RISK:
            ask_confirmation()
    """

    def validate(self, script: str) -> ValidationResult:
        """
        Full validation for LLM-generated scripts.
        Returns ValidationResult with is_safe, blocked_reason, risk_level.
        """
        script = script.strip()

        # ── Empty script ──────────────────────────────────────────────────────
        if not script:
            return ValidationResult(
                is_safe=False,
                blocked_reason="Empty script — nothing to run.",
                risk_level=RiskLevel.BLOCKED,
            )

        # ── Length guard (prevents prompt injection abuse) ────────────────────
        if len(script) > _MAX_SCRIPT_CHARS:
            return ValidationResult(
                is_safe=False,
                blocked_reason=(
                    f"Script too long ({len(script)} chars > {_MAX_SCRIPT_CHARS} max). "
                    "This may indicate prompt injection."
                ),
                risk_level=RiskLevel.BLOCKED,
            )

        # ── BLOCKED patterns ──────────────────────────────────────────────────
        for pattern, reason in _BLOCKED_PATTERNS:
            if pattern.search(script):
                return ValidationResult(
                    is_safe=False,
                    blocked_reason=reason,
                    risk_level=RiskLevel.BLOCKED,
                )

        # ── HIGH_RISK patterns ────────────────────────────────────────────────
        for pattern, reason in _HIGH_RISK_PATTERNS:
            if pattern.search(script):
                return ValidationResult(
                    is_safe=True,    # allowed but risky
                    blocked_reason=reason,
                    risk_level=RiskLevel.HIGH_RISK,
                )

        # ── LOW_RISK patterns ─────────────────────────────────────────────────
        for pattern, reason in _LOW_RISK_PATTERNS:
            if pattern.search(script):
                return ValidationResult(
                    is_safe=True,
                    blocked_reason=reason,
                    risk_level=RiskLevel.LOW_RISK,
                )

        return ValidationResult(is_safe=True, blocked_reason="", risk_level=RiskLevel.SAFE)

    def validate_intent_command(self, cmd: str) -> ValidationResult:
        """
        Lighter validation for pre-vetted intent router commands.
        Skips the dangerous-pattern check — just verifies non-empty + length.
        """
        cmd = cmd.strip()
        if not cmd:
            return ValidationResult(
                is_safe=False,
                blocked_reason="Empty intent command.",
                risk_level=RiskLevel.BLOCKED,
            )
        # Intent commands can be longer (e.g. curl for weather)
        if len(cmd) > 1000:
            return ValidationResult(
                is_safe=False,
                blocked_reason="Intent command exceeds max length.",
                risk_level=RiskLevel.BLOCKED,
            )
        return ValidationResult(is_safe=True, blocked_reason="", risk_level=RiskLevel.SAFE)
