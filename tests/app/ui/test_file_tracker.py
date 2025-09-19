import json
from pathlib import Path
import pytest

from src.app.core.file_tracker import FileTracker


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    for folder in ("imported_documents", "processed_documents", "bulk_analysis"):
        (tmp_path / folder).mkdir()
    return tmp_path


def write_file(path: Path, name: str, content: str = "sample") -> None:
    full_path = path / name
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)


def load_tracker_snapshot(root: Path) -> dict:
    payload = json.loads((root / "file_tracker.json").read_text())
    payload["counts"] = {k: int(v) for k, v in payload.get("counts", {}).items()}
    return payload


def test_scan_empty_project_creates_tracker(project_root: Path):
    tracker = FileTracker(project_root)
    snapshot = tracker.scan()

    assert snapshot.imported_count == 0
    assert snapshot.processed_count == 0
    assert snapshot.bulk_analysis_count == 0
    assert snapshot.missing["processed_missing"] == []
    assert snapshot.missing["bulk_analysis_missing"] == []

    stored = load_tracker_snapshot(project_root)
    assert stored["counts"] == {"imported": 0, "processed": 0, "bulk_analysis": 0}
    assert stored["files"] == {"imported": [], "processed": [], "bulk_analysis": []}


def test_scan_detects_missing_processed_and_bulk_outputs(project_root: Path):
    write_file(project_root / "imported_documents", "case/doc1.md")
    write_file(project_root / "processed_documents", "case/doc2.md")

    tracker = FileTracker(project_root)
    snapshot = tracker.scan()

    assert snapshot.imported_count == 1
    assert snapshot.processed_count == 1
    assert snapshot.files["processed"] == ["case/doc2.md"]
    assert snapshot.missing["processed_missing"] == ["case/doc1.md"]
    assert snapshot.missing["bulk_analysis_missing"] == ["case/doc2.md"]


def test_scan_updates_when_new_files_added(project_root: Path):
    tracker = FileTracker(project_root)
    tracker.scan()

    write_file(project_root / "imported_documents", "doc1.md")
    snapshot = tracker.scan()
    assert snapshot.imported_count == 1
    assert tracker.snapshot is snapshot

    write_file(project_root / "bulk_analysis", "doc1.md")
    snapshot = tracker.scan()
    assert snapshot.bulk_analysis_count == 1
    assert snapshot.files["bulk_analysis"] == ["doc1.md"]
    assert snapshot.missing["bulk_analysis_missing"] == []


def test_load_returns_none_when_no_snapshot(project_root: Path):
    tracker = FileTracker(project_root)
    assert tracker.load() is None


def test_load_reads_previous_snapshot(project_root: Path):
    tracker = FileTracker(project_root)
    tracker.scan()

    loaded = FileTracker(project_root).load()
    assert loaded is not None
    assert loaded.counts == tracker.snapshot.counts
