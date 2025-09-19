"""Dialog for editing project metadata details."""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from src.app.core.project_manager import ProjectMetadata


class ProjectMetadataDialog(QDialog):
    """Collect or edit high-level project metadata."""

    def __init__(self, metadata: Optional[ProjectMetadata], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Project Details")
        self.resize(420, 260)

        self._original = metadata or ProjectMetadata(case_name="")

        self._subject_edit = QLineEdit(self._original.subject_name)
        self._subject_edit.setPlaceholderText("e.g., Jane Doe")

        self._dob_edit = QLineEdit(self._original.date_of_birth)
        self._dob_edit.setPlaceholderText("e.g., 1975-08-19")

        self._case_info_edit = QPlainTextEdit(self._original.case_description or "")
        self._case_info_edit.setPlaceholderText("Case notes, referral questions, contextual details…")
        self._case_info_edit.setMinimumHeight(100)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("Subject name:", self._subject_edit)
        form.addRow("Subject DOB:", self._dob_edit)
        form.addRow("Case info:", self._case_info_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    def result_metadata(self) -> ProjectMetadata:
        """Return an updated metadata object with edits applied."""

        return replace(
            self._original,
            subject_name=self._subject_edit.text().strip(),
            date_of_birth=self._dob_edit.text().strip(),
            case_description=self._case_info_edit.toPlainText().strip(),
        )

