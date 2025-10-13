"""Integration tests for ProjectWorkspace bulk analysis behaviour."""

from __future__ import annotations

from pathlib import Path
import pytest
from PySide6.QtCore import QCoreApplication, QObject, QRunnable, Signal
from PySide6.QtWidgets import QApplication, QPushButton

from src.app.core.bulk_analysis_runner import PromptBundle

from src.app.core.file_tracker import FileTracker
from src.app.core.project_manager import ProjectManager, ProjectMetadata
from src.app.core.bulk_analysis_groups import BulkAnalysisGroup
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


def _create_project_with_group(tmp_path: Path) -> tuple[ProjectManager, BulkAnalysisGroup]:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()

    manager = ProjectManager()
    manager.create_project(projects_root, ProjectMetadata(case_name="Bulk Analysis Demo"))

    converted_doc = manager.project_dir / "converted_documents" / "folder" / "record.md"
    converted_doc.parent.mkdir(parents=True, exist_ok=True)
    converted_doc.write_text("# Heading\nBody", encoding="utf-8")

    # Ensure the tracker sees our converted document so the workspace resolves it.
    FileTracker(manager.project_dir).scan()

    group = BulkAnalysisGroup.create(name="Demo Group", files=["folder/record.md"])
    saved = manager.save_bulk_analysis_group(group)
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

    controller = workspace.bulk_controller
    assert controller is not None
    table = controller.tab.table
    assert table.rowCount() == 1

    action_widget = table.cellWidget(0, 5)
    run_button = _find_button(action_widget, "Run Pending")
    run_button.click()
    for _ in range(10):
        QCoreApplication.processEvents()
        if not controller.is_running(group.group_id):
            break
    else:
        pytest.fail("Bulk analysis run did not complete")

    expected_output = manager.project_dir / "bulk_analysis" / group.slug / "folder" / "record_analysis.md"
    assert expected_output.exists()
    assert "Summary output" in expected_output.read_text(encoding="utf-8")

    assert controller.progress_for(group.group_id) is None
    assert controller.progress_for(group.group_id) is None
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
        group: BulkAnalysisGroup,
        files: list[str],
        metadata: ProjectMetadata | None,
        default_provider: tuple[str, str | None],
        force_rerun: bool = False,
        placeholder_values: dict[str, str] | None = None,
        project_name: str = "",
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
    monkeypatch.setattr("src.app.ui.workspace.services.bulk.BulkAnalysisWorker", _StubBulkAnalysisWorker)

    workspace = ProjectWorkspace()
    workspace.set_project(manager)
    QCoreApplication.processEvents()

    controller = workspace.bulk_controller
    assert controller is not None
    table = controller.tab.table
    action_widget = table.cellWidget(0, 5)
    run_button = _find_button(action_widget, "Run Pending")
    run_button.click()
    QCoreApplication.processEvents()

    action_widget = table.cellWidget(0, 5)
    cancel_button = _find_button(action_widget, "Cancel")
    run_button = _find_button(action_widget, "Run Pending")

    assert pool.last_worker is not None
    worker = pool.last_worker
    assert isinstance(worker, _StubBulkAnalysisWorker)

    assert controller.is_running(group.group_id)
    assert controller.progress_for(group.group_id) == (0, 1)

    cancel_button.click()
    for _ in range(10):
        QCoreApplication.processEvents()
        if controller.is_cancelling(group.group_id):
            break
    else:
        pytest.fail("Cancellation did not register")

    assert worker.cancel_called is True
    assert controller.is_cancelling(group.group_id)

    # Simulate the worker completing after cancellation.
    worker.finished.emit(0, 0)
    for _ in range(10):
        QCoreApplication.processEvents()
        if not controller.is_running(group.group_id):
            break
    else:
        pytest.fail("Bulk analysis worker did not finish after cancellation")

    assert not controller.is_running(group.group_id)
    assert not controller.is_cancelling(group.group_id)
    assert controller.progress_for(group.group_id) is None

    refreshed_widget = table.cellWidget(0, 5)
    refreshed_run = _find_button(refreshed_widget, "Run Pending")
    refreshed_cancel = _find_button(refreshed_widget, "Cancel")
    assert refreshed_run.isEnabled()
    assert not refreshed_cancel.isEnabled()

    workspace.deleteLater()


def test_placeholder_analysis_includes_metadata_values(
    tmp_path: Path,
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert qt_app is not None

    manager, group = _create_project_with_group(tmp_path)
    metadata = manager.metadata
    assert metadata is not None
    metadata.subject_name = "Jane Roe"
    metadata.date_of_birth = "1970-01-01"
    metadata.case_description = "Sample case description."

    bundle = PromptBundle(
        system_template="System uses {subject_name} and {case_info}",
        user_template="User prompt for {subject_name} born {subject_dob}",
    )
    monkeypatch.setattr(
        "src.app.ui.workspace.controllers.bulk.load_prompts",
        lambda *_args, **_kwargs: bundle,
    )

    workspace = ProjectWorkspace()
    workspace.set_project(manager)
    controller = workspace.bulk_controller
    assert controller is not None

    analysis, missing_required, missing_optional = controller._analyse_placeholders(group)
    assert analysis is not None
    assert "subject_name" not in missing_optional
    assert "subject_dob" not in missing_optional
    assert "case_info" not in missing_optional
    assert "document_name" not in missing_optional

    workspace.deleteLater()
