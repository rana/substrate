"""Append-only NDJSON logging for Substrate runtime."""

import json
from pathlib import Path
from typing import Any

from substrate.runtime.types import utc_now_iso


class EventLog:
    """Append-only event log in NDJSON format.

    All significant events are recorded for auditability.
    Logs are never modified or truncated.
    """

    def __init__(self, log_path: Path) -> None:
        """Initialize event log.

        Args:
            log_path: Path to the NDJSON log file.
        """
        self._path = log_path

    @property
    def path(self) -> Path:
        """Return the log file path."""
        return self._path

    def append(
        self,
        event: str,
        node_id: str | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Append an event to the log.

        Args:
            event: Event type identifier.
            node_id: Associated node ID, if any.
            payload: Additional event data.
        """
        record = {
            "ts": utc_now_iso(),
            "node_id": node_id,
            "event": event,
            "payload": payload or {},
        }

        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")

    def ensure_exists(self) -> None:
        """Ensure the log file exists (create empty if not)."""
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.touch()
