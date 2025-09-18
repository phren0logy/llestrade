"""Tests for new project creation dialog and conversion helper plumbing."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox

_ = PySide6

from src.new.core.conversion_manager import ConversionJob
from src.new.core.project_manager import ProjectManager, ProjectMetadata
from src.new.dialogs.new_project_dialog import NewProjectDialog
from src.new.workers.conversion_worker import ConversionWorker
from src.new.core.file_tracker import FileTracker
from src.new.stages.project_workspace import ProjectWorkspace


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
    dialog._source_root = source_root
    dialog._source_line.setText(source_root.as_posix())
    dialog._populate_tree()

    dialog._output_base = output_base
    dialog._output_line.setText(output_base.as_posix())
    dialog._update_folder_preview()

    helper_index = dialog._helper_combo.findData("text_only")
    assert helper_index != -1
    dialog._helper_combo.setCurrentIndex(helper_index)
    option = dialog._helper_option_widgets.get("preserve_page_markers")
    assert option is not None
    option.setChecked(True)

    dialog._on_accept()
    config = dialog.result_config()
    assert config is not None
    assert config.conversion_helper == "text_only"
    assert config.conversion_options.get("preserve_page_markers") is True
    assert config.output_base == output_base
    assert config.selected_folders == ["bundle"]
    assert "Case-Name-2" in dialog._folder_preview_label.text()

    dialog.deleteLater()


def test_conversion_worker_respects_helper_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: Dict[str, str] = {}

    def fake_extract(_path: str) -> str:
        return "--- Page 1 ---\nHello\n--- Page 2 ---\nWorld"

    def fake_write(path: str, content: str) -> None:
        captured["path"] = path
        captured["content"] = content

    monkeypatch.setattr("src.new.workers.conversion_worker.extract_text_from_pdf", fake_extract)
    monkeypatch.setattr("src.new.workers.conversion_worker.write_file_content", fake_write)

    job = ConversionJob(
        source_path=tmp_path / "sample.pdf",
        relative_path="sample.pdf",
        destination_path=tmp_path / "converted" / "sample.md",
        conversion_type="pdf",
    )

    worker = ConversionWorker([job], helper="text_only", options={"preserve_page_markers": False})
    worker._convert_pdf(job)

    assert captured["path"].endswith("sample.md")
    assert captured["content"] == "Hello\nWorld"


def test_project_manager_update_conversion_helper_replaces_options(qt_app: QApplication) -> None:
    assert qt_app is not None
    manager = ProjectManager()
    manager.conversion_settings.options = {"legacy": True}

    manager.update_conversion_helper("text_only", preserve_page_markers=True)
    assert manager.conversion_settings.helper == "text_only"
    assert manager.conversion_settings.options == {"preserve_page_markers": True}

    manager.update_conversion_helper("default")
    assert manager.conversion_settings.helper == "default"
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
    manager.create_project(projects_root, ProjectMetadata(case_name="Missing Source"))

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
