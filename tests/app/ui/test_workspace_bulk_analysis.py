"""Integration tests for ProjectWorkspace bulk analysis behaviour."""

from __future__ import annotations

from pathlib import Path
import pytest
from PySide6.QtCore import QCoreApplication, QObject, QRunnable, Signal
from PySide6.QtWidgets import QApplication, QPushButton

from src.app.core.file_tracker import FileTracker
from src.app.core.project_manager import ProjectManager, ProjectMetadata
from src.app.core.summary_groups import SummaryGroup
from src.app.ui.stages import project_workspace
from src.app.ui.stages.project_workspace import ProjectWorkspace
from src.app.workers import bulk_analysis_worker


class _ImmediateThreadPool:
    """Thread pool stub that executes QRunnables synchronously."""

    def __init__(self) -> None:
        self.last_worker = None

    def start(self, worker: QRunnable) -> None:  # pragma: no cover - trivial stub
        self.last_worker = worker
        worker.run()


class _CaptureThreadPool:
    """Thread pool stub that captures the worker without executing it."""

    def __init__(self) -> None:
        self.last_worker: QRunnable | None = None

    def start(self, worker: QRunnable) -> None:  # pragma: no cover - trivial stub
        self.last_worker = worker


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _create_project_with_group(tmp_path: Path) -> tuple[ProjectManager, SummaryGroup]:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()

    manager = ProjectManager()
    manager.create_project(projects_root, ProjectMetadata(case_name="Bulk Analysis Demo"))

    converted_doc = manager.project_dir / "converted_documents" / "folder" / "record.md"
    converted_doc.parent.mkdir(parents=True, exist_ok=True)
    converted_doc.write_text("# Heading\nBody", encoding="utf-8")

    # Ensure the tracker sees our converted document so the workspace resolves it.
    FileTracker(manager.project_dir).scan()

    group = SummaryGroup.create(name="Demo Group", files=["folder/record.md"])
    saved = manager.save_summary_group(group)
    return manager, saved


def _find_button(action_widget, text: str) -> QPushButton:
    for button in action_widget.findChildren(QPushButton):
        if button.text() == text:
            return button
    raise AssertionError(f"Button with text '{text}' not found")


def test_workspace_run_executes_worker_and_updates_ui(tmp_path: Path, qt_app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    assert qt_app is not None

    manager, group = _create_project_with_group(tmp_path)

    pool = _ImmediateThreadPool()
    monkeypatch.setattr(project_workspace, "get_worker_pool", lambda: pool)

    monkeypatch.setattr(
        bulk_analysis_worker.BulkAnalysisWorker,
        "_create_provider",
        lambda self, config, system_prompt: object(),
    )
    monkeypatch.setattr(
        bulk_analysis_worker.BulkAnalysisWorker,
        "_invoke_provider",
        lambda self, provider, config, prompt, system_prompt, temperature=0.1, max_tokens=32000: "Summary output",
    )
    monkeypatch.setattr(
        bulk_analysis_worker,
        "should_chunk",
        lambda content, provider_id, model_name: (False, 10, 8192),
    )

    workspace = ProjectWorkspace()
    workspace.set_project(manager)
    QCoreApplication.processEvents()

    table = workspace._summary_table
    assert table is not None
    assert table.rowCount() == 1

    action_widget = table.cellWidget(0, 4)
    run_button = _find_button(action_widget, "Run Pending")
    run_button.click()
    QCoreApplication.processEvents()

    expected_output = manager.project_dir / "bulk_analysis" / group.slug / "folder" / "record_analysis.md"
    assert expected_output.exists()
    assert "Summary output" in expected_output.read_text(encoding="utf-8")

    assert group.group_id not in workspace._running_groups
    assert group.group_id not in workspace._bulk_progress
    assert run_button.isEnabled()

    status_item = table.item(0, 3)
    assert status_item is not None
    assert status_item.text() == "Ready"

    workspace.deleteLater()


class _StubBulkAnalysisWorker(QObject, QRunnable):
    """Bulk-analysis worker stub that supports cancellation flow."""

    progress = Signal(int, int, str)
    file_failed = Signal(str, str)
    finished = Signal(int, int)
    log_message = Signal(str)

    def __init__(
        self,
        *,
        project_dir: Path,
        group: SummaryGroup,
        files: list[str],
        metadata: ProjectMetadata | None,
        default_provider: tuple[str, str | None],
        force_rerun: bool = False,
    ) -> None:
        QObject.__init__(self)
        QRunnable.__init__(self)
        self.setAutoDelete(True)
        self.group = group
        self.cancel_called = False
        self.force_rerun = force_rerun

    def run(self) -> None:  # pragma: no cover - trivial stub
        self.log_message.emit("started")

    def cancel(self) -> None:  # pragma: no cover - trivial stub
        self.cancel_called = True


def test_workspace_cancel_updates_status_and_cleans_state(tmp_path: Path, qt_app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    assert qt_app is not None

    manager, group = _create_project_with_group(tmp_path)

    pool = _CaptureThreadPool()
    monkeypatch.setattr(project_workspace, "get_worker_pool", lambda: pool)
    monkeypatch.setattr(project_workspace, "BulkAnalysisWorker", _StubBulkAnalysisWorker)

    workspace = ProjectWorkspace()
    workspace.set_project(manager)
    QCoreApplication.processEvents()

    table = workspace._summary_table
    assert table is not None
    action_widget = table.cellWidget(0, 4)
    run_button = _find_button(action_widget, "Run Pending")
    run_button.click()
    QCoreApplication.processEvents()

    action_widget = table.cellWidget(0, 4)
    cancel_button = _find_button(action_widget, "Cancel")
    run_button = _find_button(action_widget, "Run Pending")

    assert pool.last_worker is not None
    worker = pool.last_worker
    assert isinstance(worker, _StubBulkAnalysisWorker)

    assert group.group_id in workspace._running_groups
    assert workspace._bulk_progress.get(group.group_id) == (0, 1)

    cancel_button.click()
    QCoreApplication.processEvents()

    assert worker.cancel_called is True
    assert group.group_id in workspace._cancelling_groups

    # Simulate the worker completing after cancellation.
    worker.finished.emit(0, 0)
    QCoreApplication.processEvents()

    assert group.group_id not in workspace._running_groups
    assert group.group_id not in workspace._cancelling_groups
    assert workspace._bulk_progress.get(group.group_id) is None

    refreshed_widget = table.cellWidget(0, 4)
    refreshed_run = _find_button(refreshed_widget, "Run Pending")
    refreshed_cancel = _find_button(refreshed_widget, "Cancel")
    assert refreshed_run.isEnabled()
    assert not refreshed_cancel.isEnabled()

    workspace.deleteLater()
