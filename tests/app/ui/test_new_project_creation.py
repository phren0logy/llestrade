"""Tests for new project creation dialog and conversion helper plumbing."""

from __future__ import annotations

from pathlib import Path
import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox

_ = PySide6

from src.app.core.conversion_manager import ConversionJob
from src.app.core.project_manager import ProjectManager, ProjectMetadata
from src.app.ui.dialogs.new_project_dialog import NewProjectDialog
from src.app.ui.dialogs.project_metadata_dialog import ProjectMetadataDialog
from src.app.ui.dialogs.summary_group_dialog import SummaryGroupDialog
from src.app.workers.conversion_worker import ConversionWorker
from src.app.core.file_tracker import FileTracker
from src.app.ui.stages.project_workspace import ProjectWorkspace


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    """Ensure a QApplication instance exists for widget-based tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_new_project_dialog_collects_helper_and_preview(tmp_path: Path, qt_app: QApplication) -> None:
    assert qt_app is not None
    source_root = tmp_path / "source"
    (source_root / "bundle").mkdir(parents=True)

    output_base = tmp_path / "output"
    output_base.mkdir()
    (output_base / "Case-Name").mkdir()

    dialog = NewProjectDialog()
    dialog._project_name_edit.setText("Case Name")
    dialog._subject_name_edit.setText("Jane Doe")
    dialog._dob_edit.setText("1975-08-19")
    dialog._case_info_edit.setPlainText("Referral for competency evaluation")
    dialog._source_root = source_root
    dialog._source_line.setText(source_root.as_posix())
    dialog._populate_tree()

    dialog._output_base = output_base
    dialog._output_line.setText(output_base.as_posix())
    dialog._update_folder_preview()

    assert dialog._helper_combo.count() == 1
    helper_id = dialog._helper_combo.itemData(0)
    assert helper_id == "azure_di"

    dialog._on_accept()
    config = dialog.result_config()
    assert config is not None
    assert config.subject_name == "Jane Doe"
    assert config.date_of_birth == "1975-08-19"
    assert config.case_description == "Referral for competency evaluation"
    assert config.conversion_helper == "azure_di"
    assert config.conversion_options == {}
    assert config.output_base == output_base
    assert config.selected_folders == ["bundle"]
    assert "Case-Name-2" in dialog._folder_preview_label.text()

    dialog.deleteLater()


def test_conversion_worker_uses_azure_when_configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    job = ConversionJob(
        source_path=tmp_path / "sample.pdf",
        relative_path="sample.pdf",
        destination_path=tmp_path / "converted" / "sample.md",
        conversion_type="pdf",
    )

    job.source_path.parent.mkdir(parents=True, exist_ok=True)
    job.source_path.write_bytes(b"pdf")

    produced_markdown = job.destination_path.parent / "sample.md"
    produced_json = job.destination_path.parent / ".azure-di" / "sample.json"

    def fake_process(_self, source_path, output_dir, json_dir, endpoint, key):
        assert json_dir is None
        produced_markdown.parent.mkdir(parents=True, exist_ok=True)
        produced_markdown.write_text("azure output")
        return None, str(produced_markdown)

    class StubSettings:
        def __init__(self) -> None:
            pass

        def get(self, key, default=None):
            if key == "azure_di_settings":
                return {"endpoint": "https://example"}
            return default

        def get_api_key(self, provider):
            if provider == "azure_di":
                return "secret"
            return None

    monkeypatch.setattr("src.app.workers.conversion_worker.SecureSettings", StubSettings)
    monkeypatch.setattr(
        "src.app.workers.conversion_worker.ConversionWorker._process_with_azure",
        fake_process,
    )

    worker = ConversionWorker([job], helper="azure_di")
    worker._convert_pdf_with_azure(job)

    content = job.destination_path.read_text()
    assert "azure output" in content
    assert not produced_json.exists()


def test_conversion_worker_raises_without_azure_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    job = ConversionJob(
        source_path=tmp_path / "sample.pdf",
        relative_path="sample.pdf",
        destination_path=tmp_path / "converted" / "sample.md",
        conversion_type="pdf",
    )

    job.source_path.parent.mkdir(parents=True, exist_ok=True)
    job.source_path.write_bytes(b"pdf")

    class EmptySettings:
        def __init__(self) -> None:
            pass

        def get(self, key, default=None):
            return default

        def get_api_key(self, provider):
            return None

    monkeypatch.setattr("src.app.workers.conversion_worker.SecureSettings", EmptySettings)

    worker = ConversionWorker([job], helper="azure_di")
    with pytest.raises(RuntimeError, match="Azure Document Intelligence credentials"):
        worker._convert_pdf_with_azure(job)


def test_project_manager_update_conversion_helper_replaces_options(qt_app: QApplication) -> None:
    assert qt_app is not None
    manager = ProjectManager()
    manager.conversion_settings.options = {"legacy": True}

    manager.update_conversion_helper("azure_di")
    assert manager.conversion_settings.helper == "azure_di"
    assert manager.conversion_settings.options == {}


def test_file_tracker_counts_converted_documents(tmp_path: Path, qt_app: QApplication) -> None:
    assert qt_app is not None
    project_root = tmp_path / "projects"
    project_root.mkdir()

    manager = ProjectManager()
    manager.create_project(project_root, ProjectMetadata(case_name="Tracker Demo"))

    converted_folder = manager.project_dir / "converted_documents"
    converted_folder.mkdir(parents=True, exist_ok=True)
    (converted_folder / "example.md").write_text("content")

    tracker = FileTracker(manager.project_dir)
    snapshot = tracker.scan()

    assert snapshot.imported_count == 1


def test_workspace_prompts_for_missing_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, qt_app: QApplication) -> None:
    assert qt_app is not None

    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    manager = ProjectManager()
    manager.create_project(
        projects_root,
        ProjectMetadata(
            case_name="Missing Source",
            subject_name="Alex Parker",
            date_of_birth="1981-02-14",
            case_description="Guardianship evaluation",
        ),
    )

    missing_root = tmp_path / "external_source"
    manager.update_source_state(root=missing_root.as_posix(), selected_folders=[], warnings=[])

    prompt_called = {"count": 0}

    def fake_question(*_args, **_kwargs):
        prompt_called["count"] += 1
        return QMessageBox.No

    monkeypatch.setattr(QMessageBox, "question", fake_question)

    workspace = ProjectWorkspace()
    workspace.set_project(manager)

    assert prompt_called["count"] == 1
    assert manager.source_state.warnings
    assert "Source folder" in manager.source_state.warnings[0]
    assert workspace._metadata_label is not None
    metadata_text = workspace._metadata_label.text()
    assert "Alex Parker" in metadata_text
    assert "1981-02-14" in metadata_text
    workspace.deleteLater()


def test_summary_group_dialog_lists_converted_documents(tmp_path: Path, qt_app: QApplication) -> None:
    assert qt_app is not None

    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    manager = ProjectManager()
    manager.create_project(projects_root, ProjectMetadata(case_name="Converted Demo"))

    converted_root = manager.project_dir / "converted_documents" / "folder"
    converted_root.mkdir(parents=True)
    (converted_root / "doc.md").write_text("content")

    dialog = SummaryGroupDialog(manager.project_dir)
    try:
        tree = dialog.file_tree
        top_labels = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
        assert "folder" in top_labels
        folder_item = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount()) if tree.topLevelItem(i).text(0) == "folder")
        child_names = [folder_item.child(i).text(0) for i in range(folder_item.childCount())]
        assert "doc.md" in child_names
    finally:
        dialog.deleteLater()


def test_project_metadata_dialog_updates_fields(qt_app: QApplication) -> None:
    assert qt_app is not None
    original = ProjectMetadata(
        case_name="Sample Case",
        subject_name="Initial Subject",
        date_of_birth="1990-05-10",
        case_description="Initial description",
    )

    dialog = ProjectMetadataDialog(original)
    dialog._subject_edit.setText("Updated Subject")
    dialog._dob_edit.setText("1991-06-11")
    dialog._case_info_edit.setPlainText("Updated details")

    result = dialog.result_metadata()
    assert result.subject_name == "Updated Subject"
    assert result.date_of_birth == "1991-06-11"
    assert result.case_description == "Updated details"

    dialog.deleteLater()
