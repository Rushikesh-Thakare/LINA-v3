"""
LINA v3 — History Manager
Records commands and their results in JSONL format.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path

from lina.config import HISTORY_DIR

log = logging.getLogger(__name__)


@dataclass
class HistoryEntry:
    command: str
    script: str
    output_preview: str
    status: str
    timestamp: str
    entry_type: str


class HistoryManager:
    """
    Manages daily JSON-Lines history files.
    Format: history_YYYY-MM-DD.jsonl
    """

    def __init__(self, history_dir: str | Path = HISTORY_DIR, retention_days: int = 7):
        self.history_dir = Path(history_dir)
        self.retention_days = retention_days
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self._current_file = self._get_daily_path()

    def _get_daily_path(self, date: datetime | None = None) -> Path:
        dt = date or datetime.now()
        filename = f"history_{dt.strftime('%Y-%m-%d')}.jsonl"
        return self.history_dir / filename

    def log(self, entry: HistoryEntry | dict) -> None:
        """Log an entry. Handles both the dataclass and raw dicts for backward compatibility."""
        path = self._get_daily_path()
        
        # Keep internal references updated
        if path != self._current_file:
            self._current_file = path

        # Convert to dict if it's the dataclass
        data = asdict(entry) if isinstance(entry, HistoryEntry) else entry

        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as exc:
            log.error("Failed to log history: %s", exc)

    def last_n(self, n: int) -> list[HistoryEntry]:
        """Returns the last N history entries, parsed as dataclass instances."""
        entries = []
        # Look backwards through daily files until we have N entries
        for i in range(self.retention_days):
            date = datetime.now() - timedelta(days=i)
            path = self._get_daily_path(date)
            
            if not path.exists():
                continue
                
            try:
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    
                # Parse lines backwards
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(HistoryEntry(
                            command=data.get("command", ""),
                            script=data.get("script", ""),
                            output_preview=data.get("output", "")[:200] if "output" in data else data.get("output_preview", ""),
                            status=data.get("status", "ok"),
                            timestamp=data.get("timestamp", data.get("ts", "")),
                            entry_type=data.get("entry_type", data.get("type", "unknown"))
                        ))
                        if len(entries) >= n:
                            # We have enough; because we iterated backwards, they are newest-first.
                            # We reverse them before returning to give oldest-first chronological order.
                            entries.reverse()
                            return entries
                    except json.JSONDecodeError:
                        continue
            except Exception as exc:
                log.warning("Could not read history file %s: %s", path, exc)

        entries.reverse()
        return entries

    def cleanup_old(self) -> None:
        """Delete files older than retention_days."""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        count = 0
        try:
            for path in self.history_dir.glob("history_*.jsonl"):
                # Extract date from filename: history_YYYY-MM-DD.jsonl
                stem = path.stem.replace("history_", "")
                try:
                    file_date = datetime.strptime(stem, "%Y-%m-%d")
                    if file_date < cutoff:
                        path.unlink()
                        count += 1
                except ValueError:
                    pass
            if count > 0:
                log.info("History cleanup: removed %d old files.", count)
        except Exception as exc:
            log.error("History cleanup failed: %s", exc)

    def export_json(self, destination: str) -> bool:
        """Merge all history into a single JSON array at destination."""
        all_entries = []
        try:
            # Sort files chronologically
            files = sorted(self.history_dir.glob("history_*.jsonl"))
            for path in files:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            try:
                                all_entries.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
                                
            with open(destination, "w", encoding="utf-8") as f:
                json.dump(all_entries, f, indent=2, ensure_ascii=False)
            return True
        except Exception as exc:
            log.error("History export failed: %s", exc)
            return False

    def clear(self) -> None:
        """Wipe the history directory entirely."""
        try:
            shutil.rmtree(self.history_dir)
            self.history_dir.mkdir(parents=True, exist_ok=True)
            log.info("History cleared.")
        except Exception as exc:
            log.error("Failed to clear history: %s", exc)
