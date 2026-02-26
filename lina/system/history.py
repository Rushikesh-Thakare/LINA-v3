"""
LINA v3 — History Manager
Persists command events as JSON-Lines with timestamps.
Supports retention-based cleanup and recent-entry retrieval.
"""

import json
import logging
import os
from datetime import datetime, timezone

from lina.config import LOG_DIR, HISTORY_DIR, HISTORY_RETENTION_DAYS

log = logging.getLogger(__name__)

_HISTORY_FILE = str(HISTORY_DIR / "commands.log")
_MAX_LINES = 2000      # hard cap on file size
_DISPLAY_LINES = 20    # default lines returned to UI


class HistoryManager:

    def __init__(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    # ── Write ─────────────────────────────────────────────────────────────────
    def log(self, entry: dict) -> None:
        """Append a JSON-Lines entry. 'ts' must already be set."""
        try:
            line = json.dumps(entry, ensure_ascii=False)
            with open(_HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as exc:
            log.warning("History write failed: %s", exc)

    # ── Read ──────────────────────────────────────────────────────────────────
    def recent(self, n: int = _DISPLAY_LINES) -> list[str]:
        """Return the last n raw JSON-Lines as strings."""
        if not os.path.exists(_HISTORY_FILE):
            return []
        try:
            with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return [l.strip() for l in lines[-n:] if l.strip()]
        except Exception as exc:
            log.warning("History read failed: %s", exc)
            return []

    def all_entries(self) -> list[dict]:
        """Return all history entries as parsed dicts."""
        entries = []
        if not os.path.exists(_HISTORY_FILE):
            return entries
        try:
            with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except Exception as exc:
            log.warning("History read failed: %s", exc)
        return entries

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def cleanup(self, days: int = HISTORY_RETENTION_DAYS) -> None:
        """Remove entries older than `days` days and enforce _MAX_LINES."""
        if not os.path.exists(_HISTORY_FILE):
            return
        cutoff = datetime.now(tz=timezone.utc).timestamp() - (days * 86_400)
        try:
            kept: list[str] = []
            with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        ts_str = obj.get("ts", "")
                        if ts_str:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                            if ts >= cutoff:
                                kept.append(line)
                        else:
                            kept.append(line)
                    except Exception:
                        kept.append(line)

            kept = kept[-_MAX_LINES:]
            with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
                f.writelines(kept)
            log.info("History cleanup: kept %d entries.", len(kept))
        except Exception as exc:
            log.warning("History cleanup failed: %s", exc)

    # ── Clear ────────────────────────────────────────────────────────────────
    def clear(self) -> None:
        """Wipe the history file."""
        try:
            open(_HISTORY_FILE, "w").close()
        except Exception as exc:
            log.warning("History clear failed: %s", exc)

    # ── Export ────────────────────────────────────────────────────────────────
    def export_json(self, dest_path: str) -> None:
        """Export all history to a pretty-printed JSON file."""
        entries = self.all_entries()
        with open(dest_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        log.info("Exported %d history entries to %s", len(entries), dest_path)
