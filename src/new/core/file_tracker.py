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
    def bulk_analysis_count(self) -> int:
        return self.counts.get("bulk_analysis", 0)

    @property
    def summaries_count(self) -> int:
        """Compatibility alias for legacy callers."""
        return self.bulk_analysis_count

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
        counts = dict(payload.get("counts", {}))
        files = {k: list(v) for k, v in dict(payload.get("files", {})).items()}
        missing = {k: list(v) for k, v in dict(payload.get("missing", {})).items()}

        if "bulk_analysis" not in counts and "summaries" in counts:
            counts["bulk_analysis"] = counts.pop("summaries")
        if "bulk_analysis" not in files and "summaries" in files:
            files["bulk_analysis"] = files.pop("summaries")
        if "bulk_analysis_missing" not in missing and "summaries_missing" in missing:
            missing["bulk_analysis_missing"] = missing.pop("summaries_missing")

        return cls(
            timestamp=(
                datetime.fromisoformat(timestamp)
                if isinstance(timestamp, str)
                else datetime.now(timezone.utc)
            ),
            counts=counts,
            files=files,
            missing=missing,
            notes=dict(payload.get("notes", {})),
            version=str(payload.get("version", TRACKER_VERSION)),
        )


@dataclass(frozen=True)
class DashboardMetrics:
    """Aggregated counts surfaced to the dashboard and welcome views."""

    last_scan: Optional[datetime]
    imported_total: int = 0
    processed_total: int = 0
    bulk_analysis_total: int = 0
    pending_processing: int = 0
    pending_bulk_analysis: int = 0
    notes: Dict[str, str] = field(default_factory=dict)
    snapshot_version: str = TRACKER_VERSION

    @classmethod
    def empty(cls) -> "DashboardMetrics":
        return cls(
            last_scan=None,
            imported_total=0,
            processed_total=0,
            bulk_analysis_total=0,
            pending_processing=0,
            pending_bulk_analysis=0,
            notes={},
            snapshot_version=TRACKER_VERSION,
        )

    @classmethod
    def from_snapshot(cls, snapshot: FileTrackerSnapshot) -> "DashboardMetrics":
        return cls(
            last_scan=snapshot.timestamp,
            imported_total=snapshot.imported_count,
            processed_total=snapshot.processed_count,
            bulk_analysis_total=snapshot.bulk_analysis_count,
            pending_processing=len(snapshot.missing.get("processed_missing", [])),
            pending_bulk_analysis=len(snapshot.missing.get("bulk_analysis_missing", [])),
            notes=dict(snapshot.notes),
            snapshot_version=snapshot.version,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "last_scan": self.last_scan.isoformat() if self.last_scan else None,
            "imported_total": self.imported_total,
            "processed_total": self.processed_total,
            "bulk_analysis_total": self.bulk_analysis_total,
            "pending_processing": self.pending_processing,
            "pending_bulk_analysis": self.pending_bulk_analysis,
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
        bulk_total = payload.get("bulk_analysis_total") if isinstance(payload, dict) else None
        if bulk_total is None and isinstance(payload, dict):
            bulk_total = payload.get("summaries_total")

        pending_bulk = payload.get("pending_bulk_analysis") if isinstance(payload, dict) else None
        if pending_bulk is None and isinstance(payload, dict):
            pending_bulk = payload.get("pending_summaries")

        return cls(
            last_scan=last_scan,
            imported_total=int(payload.get("imported_total", 0)),
            processed_total=int(payload.get("processed_total", 0)),
            bulk_analysis_total=int(bulk_total or 0),
            pending_processing=int(payload.get("pending_processing", 0)),
            pending_bulk_analysis=int(pending_bulk or 0),
            notes=dict(payload.get("notes", {})),
            snapshot_version=str(payload.get("snapshot_version", TRACKER_VERSION)),
        )

class FileTracker:
    """Track files within a project directory.

    The tracker inspects three canonical subdirectories:
    - imported_documents/
    - processed_documents/
    - bulk_analysis/

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
        bulk_analysis = self._gather_files("bulk_analysis")

        counts = {
            "imported": len(imported),
            "processed": len(processed),
            "bulk_analysis": len(bulk_analysis),
        }

        files = {
            "imported": sorted(imported),
            "processed": sorted(processed),
            "bulk_analysis": sorted(bulk_analysis),
        }

        missing = {
            "processed_missing": sorted(imported - processed),
            "bulk_analysis_missing": sorted(processed - bulk_analysis),
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
