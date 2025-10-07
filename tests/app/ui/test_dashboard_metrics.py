"""Tests for the dashboard metrics API provided by ProjectManager."""

from __future__ import annotations

from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea

_ = PySide6

from src.app.core.file_tracker import DashboardMetrics
from src.app.core.project_manager import ProjectManager, ProjectMetadata
from src.app.core.bulk_analysis_groups import BulkAnalysisGroup
from src.app.ui.stages.welcome_stage import WelcomeStage
from src.app.workers import DashboardWorker, get_worker_pool


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
    assert metrics.bulk_analysis_total == 0
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

    metrics = manager.get_dashboard_metrics(refresh=True)

    assert metrics.imported_total == 2
    assert metrics.bulk_analysis_total == 0
    assert metrics.pending_bulk_analysis == 2
    assert manager.dashboard_metrics == metrics


def test_dashboard_metrics_persist_across_project_reload(tmp_path: Path, qt_app: QApplication) -> None:
    assert qt_app is not None
    manager = ProjectManager()
    project_path = manager.create_project(tmp_path, ProjectMetadata(case_name="Persist Metrics"))

    converted = manager.project_dir / "converted_documents"
    converted.mkdir(exist_ok=True)
    (converted / "doc.md").write_text("---\nsource_format: pdf\n---\nbody")

    first_metrics = manager.get_dashboard_metrics(refresh=True)
    manager.save_project()

    reloaded = ProjectManager()
    assert reloaded.load_project(project_path)

    assert reloaded.dashboard_metrics.imported_total == first_metrics.imported_total
    assert reloaded.dashboard_metrics.last_scan is not None

    cached_metrics = reloaded.get_dashboard_metrics()
    assert cached_metrics == reloaded.dashboard_metrics
    assert cached_metrics.imported_total == 1


def test_read_dashboard_metrics_from_disk(tmp_path: Path, qt_app: QApplication) -> None:
    assert qt_app is not None
    manager = ProjectManager()
    project_path = manager.create_project(tmp_path, ProjectMetadata(case_name="Disk Metrics"))

    converted = manager.project_dir / "converted_documents"
    converted.mkdir(exist_ok=True)
    (converted / "doc.md").write_text("---\nsource_format: pdf\n---\nbody")

    manager.get_dashboard_metrics(refresh=True)
    manager.save_project()

    metrics = ProjectManager.read_dashboard_metrics_from_disk(project_path)

    assert metrics.imported_total == 1
    assert metrics.last_scan is not None
    assert metrics.pending_bulk_analysis == 1

def test_workspace_metrics_include_group_coverage(tmp_path: Path, qt_app: QApplication) -> None:
    assert qt_app is not None
    manager = ProjectManager()
    manager.create_project(tmp_path, ProjectMetadata(case_name="Workspace Coverage"))

    converted_dir = manager.project_dir / "converted_documents" / "folder"
    converted_dir.mkdir(parents=True, exist_ok=True)
    (converted_dir / "doc1.md").write_text("converted")
    (converted_dir / "doc2.md").write_text("converted")

    group = BulkAnalysisGroup.create(name="Case Files", directories=["folder"])
    manager.save_bulk_analysis_group(group)

    outputs_dir = manager.project_dir / "bulk_analysis" / group.slug / "outputs" / "folder"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    (outputs_dir / "doc1.md").write_text("analysis")

    metrics = manager.get_workspace_metrics(refresh=True)

    assert metrics.dashboard.imported_total == 2

    group_metrics = metrics.groups[group.group_id]
    assert group_metrics.converted_count == 2
    assert group_metrics.bulk_analysis_total == 1
    assert group_metrics.pending_bulk_analysis == 1
    assert set(group_metrics.converted_files) == {"folder/doc1.md", "folder/doc2.md"}


def test_welcome_stage_uses_persisted_metrics(
    tmp_path: Path, qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert qt_app is not None
    monkeypatch.setenv("FRD_SETTINGS_DIR", str(tmp_path / "settings"))
    manager = ProjectManager()
    project_path = manager.create_project(tmp_path, ProjectMetadata(case_name="Welcome Metrics"))

    converted = manager.project_dir / "converted_documents"
    converted.mkdir(exist_ok=True)
    (converted / "doc.md").write_text("---\nsource_format: pdf\n---\nbody")

    manager.get_dashboard_metrics(refresh=True)
    manager.save_project()

    stage = WelcomeStage()
    try:
        stage.showEvent(QShowEvent())
        stats_text = stage._project_stats_text(manager.project_path)
    finally:
        stage.deleteLater()

    assert "Converted: 1" in stats_text
    assert "Highlights: 0 of 1 (pending 1)" in stats_text
    assert "Bulk analysis: 0 of 1 (pending 1)" in stats_text
    assert "Last scan" in stats_text


def test_welcome_stage_refreshes_on_show_event(
    tmp_path: Path, qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert qt_app is not None
    monkeypatch.setenv("FRD_SETTINGS_DIR", str(tmp_path / "settings_refresh"))
    manager = ProjectManager()
    manager.create_project(tmp_path, ProjectMetadata(case_name="Refresh Metrics"))

    converted_dir = manager.project_dir / "converted_documents"
    converted_dir.mkdir(exist_ok=True)
    (converted_dir / "doc.md").write_text("---\nsource_format: pdf\n---\nbody")

    manager.get_dashboard_metrics(refresh=True)
    manager.save_project()

    stage = WelcomeStage()
    try:
        stage.showEvent(QShowEvent())
        qt_app.processEvents()

        stats_label = _find_stats_label(stage)
        assert stats_label is not None
        initial_text = stats_label.text()
        assert "Highlights: 0 of 1 (pending 1)" in initial_text
        assert "Bulk analysis: 0 of 1 (pending 1)" in initial_text

        outputs_dir = manager.project_dir / "bulk_analysis" / "manual" / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        (outputs_dir / "doc_analysis.md").write_text("analysis")

        manager.get_dashboard_metrics(refresh=True)
        manager.save_project()

        stage.showEvent(QShowEvent())
        qt_app.processEvents()

        updated_label = _find_stats_label(stage)
        assert updated_label is not None
        updated_text = updated_label.text()
        assert "Bulk analysis: 1 of 1" in updated_text
    finally:
        stage.deleteLater()


def _find_stats_label(stage: WelcomeStage) -> QLabel | None:
    for index in range(stage._recent_projects_layout.count()):
        item = stage._recent_projects_layout.itemAt(index)
        widget = item.widget()
        if isinstance(widget, QScrollArea):
            container = widget.widget()
            if not container:
                continue
            layout = container.layout()
            if not layout:
                continue
            for row in range(layout.count()):
                card = layout.itemAt(row).widget()
                if card is None:
                    continue
                for label in card.findChildren(QLabel):
                    if "Converted" in label.text():
                        return label
    return None


class _DummyWorker(DashboardWorker):
    def __init__(self) -> None:
        super().__init__(worker_name="dummy")
        self.invoked = False

    def _run(self) -> None:
        self.invoked = True


def test_worker_pool_singleton(qt_app: QApplication) -> None:
    pool_a = get_worker_pool()
    pool_b = get_worker_pool()
    assert pool_a is pool_b
    assert pool_a.maxThreadCount() == 3


def test_dashboard_worker_base_helpers() -> None:
    worker = _DummyWorker()
    assert not worker.is_cancelled()
    worker.run()
    assert worker.invoked
    worker.cancel()
    assert worker.is_cancelled()


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
