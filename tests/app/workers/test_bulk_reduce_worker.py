"""Tests for combined bulk-analysis input resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

_ = PySide6  # silence lint about unused import

from src.app.core.summary_groups import SummaryGroup
from src.app.workers.bulk_reduce_worker import BulkReduceWorker


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _write(project_dir: Path, relative: str, content: str) -> Path:
    path = project_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_resolve_inputs_supports_legacy_map_layout(tmp_path: Path, qt_app: QApplication) -> None:
    assert qt_app is not None

    project_dir = tmp_path
    _write(project_dir, "converted_documents/doc.md", "Converted")
    # Legacy layout stores per-document outputs directly under the group folder
    _write(project_dir, "bulk_analysis/group-one/folder/doc_analysis.md", "Summary")

    group = SummaryGroup.create(name="Combined")
    group.operation = "combined"
    group.combine_converted_files = ["doc.md"]
    group.combine_map_groups = ["group-one"]

    worker = BulkReduceWorker(project_dir=project_dir, group=group, metadata=None)
    inputs = worker._resolve_inputs()
    keys = {key for _, _, key in inputs}

    assert "converted/doc.md" in keys
    assert "map/group-one/folder/doc_analysis.md" in keys


def test_resolve_inputs_normalises_outputs_prefix(tmp_path: Path, qt_app: QApplication) -> None:
    assert qt_app is not None

    project_dir = tmp_path
    _write(project_dir, "converted_documents/base.md", "Converted")
    _write(project_dir, "bulk_analysis/group-two/outputs/sub/doc_analysis.md", "Summary")

    group = SummaryGroup.create(name="Combined Prefix")
    group.operation = "combined"
    group.combine_map_files = ["group-two/outputs/sub/doc_analysis.md"]
    group.combine_map_directories = ["group-two/outputs/sub"]

    worker = BulkReduceWorker(project_dir=project_dir, group=group, metadata=None)
    inputs = worker._resolve_inputs()
    keys = {key for _, _, key in inputs}

    expected = "map/group-two/sub/doc_analysis.md"
    assert keys == {expected}
