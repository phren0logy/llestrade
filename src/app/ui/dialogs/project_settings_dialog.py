"""Dialog for editing project metadata and placeholder configuration."""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.app.core.placeholders import ProjectPlaceholders
from src.app.core.placeholders.system import SYSTEM_PLACEHOLDERS
from src.app.core.project_manager import ProjectManager, ProjectMetadata
from src.app.ui.widgets import PlaceholderEditorConfig, PlaceholderEditorWidget


class ProjectSettingsDialog(QDialog):
    """Allow users to edit project metadata and placeholder values."""

    def __init__(self, manager: ProjectManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Project Settings")
        self.resize(520, 560)

        self._manager = manager
        self._metadata = manager.metadata or ProjectMetadata(case_name=manager.project_name or "")

        self._subject_edit = QLineEdit(self._metadata.subject_name or "")
        self._subject_edit.setPlaceholderText("e.g., Jane Doe")

        self._dob_edit = QLineEdit(self._metadata.date_of_birth or "")
        self._dob_edit.setPlaceholderText("e.g., 1975-08-19")

        self._case_info_edit = QPlainTextEdit(self._metadata.case_description or "")
        self._case_info_edit.setPlaceholderText("Case notes, referral questions, contextual details…")
        self._case_info_edit.setMinimumHeight(120)

        placeholder_config = PlaceholderEditorConfig(allow_export=True, system_keys=SYSTEM_PLACEHOLDERS)
        self._placeholder_editor = PlaceholderEditorWidget(config=placeholder_config)
        try:
            placeholders = manager.placeholders
        except AttributeError:
            placeholders = ProjectPlaceholders()
        self._placeholder_editor.set_placeholders(placeholders)
        self._placeholder_editor.set_system_value("project_name", self._metadata.case_name or manager.project_name or "")

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #b26a00;")
        self._status_label.hide()

        self._build_ui()

    # ------------------------------------------------------------------
    # UI assembly
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info = QLabel(
            "Update project metadata and placeholders. System placeholders (project name, timestamp, source paths) "
            "remain read-only but are listed for reference."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #555;")
        layout.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)

        form.addRow("Subject name:", self._subject_edit)
        form.addRow("Subject DOB:", self._dob_edit)
        form.addRow("Case info:", self._case_info_edit)
        form.addRow("Placeholders:", self._placeholder_editor)

        layout.addLayout(form)
        layout.addWidget(self._status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_accept(self) -> None:
        if not self._placeholder_editor.validate(parent=self):
            return

        updated_metadata = replace(
            self._metadata,
            subject_name=self._subject_edit.text().strip(),
            date_of_birth=self._dob_edit.text().strip(),
            case_description=self._case_info_edit.toPlainText().strip(),
        )

        try:
            self._manager.update_metadata(metadata=updated_metadata)
            placeholders = self._placeholder_editor.placeholders()
            self._manager.set_placeholders(placeholders)
            self._manager.save_project()
        except Exception as exc:  # pragma: no cover - UI feedback
            QMessageBox.critical(self, "Save Failed", f"Failed to update project settings:\n\n{exc}")
            return

        self.accept()


__all__ = ["ProjectSettingsDialog"]
