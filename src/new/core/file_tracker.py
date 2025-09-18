"""File tracking utilities for dashboard workflows."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    files: Dict[str, List[str]] = field(default_factory=dict)
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

    def to_dashboard_metrics(self) -> "DashboardMetrics":
        """Translate the snapshot into lightweight dashboard metrics."""
        return DashboardMetrics.from_snapshot(self)

    def to_json(self) -> Dict[str, object]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "counts": self.counts,
            "files": self.files,
            "missing": self.missing,
            "notes": self.notes,
            "version": self.version,
        }

    @classmethod
    def from_json(cls, payload: Dict[str, object]) -> "FileTrackerSnapshot":
        timestamp = payload.get("timestamp")
        return cls(
            timestamp=(
                datetime.fromisoformat(timestamp)
                if isinstance(timestamp, str)
                else datetime.now(timezone.utc)
            ),
            counts=dict(payload.get("counts", {})),
            files={k: list(v) for k, v in dict(payload.get("files", {})).items()},
            missing={k: list(v) for k, v in dict(payload.get("missing", {})).items()},
            notes=dict(payload.get("notes", {})),
            version=str(payload.get("version", TRACKER_VERSION)),
        )


@dataclass(frozen=True)
class DashboardMetrics:
    """Aggregated counts surfaced to the dashboard and welcome views."""

    last_scan: Optional[datetime]
    imported_total: int = 0
    processed_total: int = 0
    summaries_total: int = 0
    pending_processing: int = 0
    pending_summaries: int = 0
    notes: Dict[str, str] = field(default_factory=dict)
    snapshot_version: str = TRACKER_VERSION

    @classmethod
    def empty(cls) -> "DashboardMetrics":
        return cls(
            last_scan=None,
            imported_total=0,
            processed_total=0,
            summaries_total=0,
            pending_processing=0,
            pending_summaries=0,
            notes={},
            snapshot_version=TRACKER_VERSION,
        )

    @classmethod
    def from_snapshot(cls, snapshot: FileTrackerSnapshot) -> "DashboardMetrics":
        return cls(
            last_scan=snapshot.timestamp,
            imported_total=snapshot.imported_count,
            processed_total=snapshot.processed_count,
            summaries_total=snapshot.summaries_count,
            pending_processing=len(snapshot.missing.get("processed_missing", [])),
            pending_summaries=len(snapshot.missing.get("summaries_missing", [])),
            notes=dict(snapshot.notes),
            snapshot_version=snapshot.version,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "last_scan": self.last_scan.isoformat() if self.last_scan else None,
            "imported_total": self.imported_total,
            "processed_total": self.processed_total,
            "summaries_total": self.summaries_total,
            "pending_processing": self.pending_processing,
            "pending_summaries": self.pending_summaries,
            "notes": dict(self.notes),
            "snapshot_version": self.snapshot_version,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object] | None) -> "DashboardMetrics":
        if not payload:
            return cls.empty()
        last_scan_value = payload.get("last_scan") if isinstance(payload, dict) else None
        last_scan: Optional[datetime]
        if isinstance(last_scan_value, str):
            try:
                last_scan = datetime.fromisoformat(last_scan_value)
            except ValueError:
                last_scan = None
        else:
            last_scan = None
        return cls(
            last_scan=last_scan,
            imported_total=int(payload.get("imported_total", 0)),
            processed_total=int(payload.get("processed_total", 0)),
            summaries_total=int(payload.get("summaries_total", 0)),
            pending_processing=int(payload.get("pending_processing", 0)),
            pending_summaries=int(payload.get("pending_summaries", 0)),
            notes=dict(payload.get("notes", {})),
            snapshot_version=str(payload.get("snapshot_version", TRACKER_VERSION)),
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
        imported = self._gather_files("converted_documents")
        if not imported:
            imported = self._gather_files("imported_documents")
        processed = self._gather_files("processed_documents")
        summaries = self._gather_files("summaries")

        counts = {
            "imported": len(imported),
            "processed": len(processed),
            "summaries": len(summaries),
        }

        files = {
            "imported": sorted(imported),
            "processed": sorted(processed),
            "summaries": sorted(summaries),
        }

        missing = {
            "processed_missing": sorted(imported - processed),
            "summaries_missing": sorted(processed - summaries),
        }

        snapshot = FileTrackerSnapshot(
            timestamp=datetime.now(timezone.utc),
            counts=counts,
            files=files,
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


__all__ = ["FileTracker", "FileTrackerSnapshot", "DashboardMetrics"]
