"""File tracking utilities for dashboard workflows."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

LOGGER = logging.getLogger(__name__)

TRACKER_FILENAME = "file_tracker.json"
TRACKER_VERSION = "1"


@dataclass
class FileTrackerSnapshot:
    """Summary of document state within a project."""

    timestamp: datetime
    counts: Dict[str, int] = field(default_factory=dict)
    missing: Dict[str, List[str]] = field(default_factory=dict)
    notes: Dict[str, str] = field(default_factory=dict)
    version: str = TRACKER_VERSION

    @property
    def imported_count(self) -> int:
        return self.counts.get("imported", 0)

    @property
    def processed_count(self) -> int:
        return self.counts.get("processed", 0)

    @property
    def summaries_count(self) -> int:
        return self.counts.get("summaries", 0)

    @property
    def processed_ratio(self) -> Optional[float]:
        if self.imported_count == 0:
            return None
        return self.processed_count / self.imported_count

    def to_json(self) -> Dict[str, object]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "counts": self.counts,
            "missing": self.missing,
            "notes": self.notes,
            "version": self.version,
        }

    @classmethod
    def from_json(cls, payload: Dict[str, object]) -> "FileTrackerSnapshot":
        timestamp = payload.get("timestamp")
        return cls(
            timestamp=datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else datetime.utcnow(),
            counts=dict(payload.get("counts", {})),
            missing={k: list(v) for k, v in dict(payload.get("missing", {})).items()},
            notes=dict(payload.get("notes", {})),
            version=str(payload.get("version", TRACKER_VERSION)),
        )


class FileTracker:
    """Track files within a project directory.

    The tracker inspects three canonical subdirectories:
    - imported_documents/
    - processed_documents/
    - summaries/

    Each `scan()` collects counts and missing counterparts, then persists
    the snapshot to `file_tracker.json` under the project root.
    """

    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path
        self.snapshot: Optional[FileTrackerSnapshot] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load(self) -> Optional[FileTrackerSnapshot]:
        """Load the previously stored snapshot, if present."""
        tracker_path = self._tracker_file()
        if not tracker_path.exists():
            LOGGER.debug("No file tracker cache at %s", tracker_path)
            return None
        try:
            payload = json.loads(tracker_path.read_text())
            self.snapshot = FileTrackerSnapshot.from_json(payload)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Failed to load file tracker snapshot: %s", exc)
            self.snapshot = None
        return self.snapshot

    def scan(self) -> FileTrackerSnapshot:
        """Walk the project directories and generate a fresh snapshot."""
        imported = self._gather_files("imported_documents")
        processed = self._gather_files("processed_documents")
        summaries = self._gather_files("summaries")

        counts = {
            "imported": len(imported),
            "processed": len(processed),
            "summaries": len(summaries),
        }

        missing = {
            "processed_missing": sorted(imported - processed),
            "summaries_missing": sorted(processed - summaries),
        }

        snapshot = FileTrackerSnapshot(
            timestamp=datetime.utcnow(),
            counts=counts,
            missing=missing,
        )
        self.snapshot = snapshot
        self._write_snapshot(snapshot)
        return snapshot

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _tracker_file(self) -> Path:
        return self.project_path / TRACKER_FILENAME

    def _gather_files(self, folder_name: str) -> set[str]:
        folder = self.project_path / folder_name
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
            return set()

        collected: set[str] = set()
        for path in folder.rglob("*"):
            if path.is_file():
                collected.add(path.relative_to(folder).as_posix())
        return collected

    def _write_snapshot(self, snapshot: FileTrackerSnapshot) -> None:
        tracker_path = self._tracker_file()
        try:
            tracker_path.write_text(json.dumps(snapshot.to_json(), indent=2))
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.error("Failed to persist file tracker snapshot: %s", exc)


__all__ = ["FileTracker", "FileTrackerSnapshot"]
