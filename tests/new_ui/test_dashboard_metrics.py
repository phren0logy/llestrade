"""Tests for the dashboard metrics API provided by ProjectManager."""

from __future__ import annotations

from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

_ = PySide6

from src.new.core.file_tracker import DashboardMetrics
from src.new.core.project_manager import ProjectManager, ProjectMetadata
from src.new.stages.welcome_stage import WelcomeStage


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_get_dashboard_metrics_scans_when_missing(tmp_path: Path, qt_app: QApplication) -> None:
    assert qt_app is not None
    manager = ProjectManager()
    manager.create_project(tmp_path, ProjectMetadata(case_name="Metrics Demo"))

    metrics = manager.get_dashboard_metrics()

    assert metrics.imported_total == 0
    assert metrics.processed_total == 0
    assert metrics.bulk_analysis_total == 0
    assert metrics.pending_processing == 0
    assert metrics.pending_bulk_analysis == 0
    assert metrics.last_scan is not None
    assert manager.dashboard_metrics == metrics
    assert manager.source_state.last_scan is not None


def test_dashboard_metrics_refresh_counts_files(tmp_path: Path, qt_app: QApplication) -> None:
    assert qt_app is not None
    manager = ProjectManager()
    manager.create_project(tmp_path, ProjectMetadata(case_name="Metrics Files"))

    converted = manager.project_dir / "converted_documents" / "folder"
    converted.mkdir(parents=True, exist_ok=True)
    (converted / "doc1.md").write_text("converted")
    (converted / "doc2.md").write_text("converted")

    processed = manager.project_dir / "processed_documents" / "folder"
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "doc1.md").write_text("processed")

    metrics = manager.get_dashboard_metrics(refresh=True)

    assert metrics.imported_total == 2
    assert metrics.processed_total == 1
    assert metrics.bulk_analysis_total == 0
    assert metrics.pending_processing == 1  # doc2.md still pending processing
    assert metrics.pending_bulk_analysis == 1  # doc1.md awaits bulk analysis
    assert manager.dashboard_metrics == metrics


def test_dashboard_metrics_persist_across_project_reload(tmp_path: Path, qt_app: QApplication) -> None:
    assert qt_app is not None
    manager = ProjectManager()
    project_path = manager.create_project(tmp_path, ProjectMetadata(case_name="Persist Metrics"))

    converted = manager.project_dir / "converted_documents"
    converted.mkdir(exist_ok=True)
    (converted / "doc.md").write_text("data")

    first_metrics = manager.get_dashboard_metrics(refresh=True)
    manager.save_project()

    reloaded = ProjectManager()
    assert reloaded.load_project(project_path)

    assert reloaded.dashboard_metrics.imported_total == first_metrics.imported_total
    assert reloaded.dashboard_metrics.last_scan is not None

    cached_metrics = reloaded.get_dashboard_metrics()
    assert cached_metrics == reloaded.dashboard_metrics
    assert cached_metrics.imported_total == 1


def test_welcome_stage_uses_persisted_metrics(tmp_path: Path, qt_app: QApplication) -> None:
    assert qt_app is not None
    manager = ProjectManager()
    project_path = manager.create_project(tmp_path, ProjectMetadata(case_name="Welcome Metrics"))

    converted = manager.project_dir / "converted_documents"
    converted.mkdir(exist_ok=True)
    (converted / "doc.md").write_text("data")

    manager.get_dashboard_metrics(refresh=True)
    manager.save_project()

    stage = WelcomeStage()
    try:
        stats_text = stage._project_stats_text(manager.project_path)
    finally:
        stage.deleteLater()

    assert "Converted 1" in stats_text
    assert "Processed" in stats_text


def test_dashboard_metrics_from_dict_accepts_legacy_keys() -> None:
    payload = {
        "imported_total": 5,
        "processed_total": 4,
        "summaries_total": 3,
        "pending_processing": 1,
        "pending_summaries": 2,
    }

    metrics = DashboardMetrics.from_dict(payload)

    assert metrics.bulk_analysis_total == 3
    assert metrics.pending_bulk_analysis == 2
