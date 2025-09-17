"""Dialog for creating summary groups."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from src.config.app_config import get_available_providers_and_models
from src.new.core.summary_groups import SummaryGroup


class SummaryGroupDialog(QDialog):
    """Collect information needed to create a summary group."""

    def __init__(self, project_dir: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._project_dir = project_dir
        self._group: Optional[SummaryGroup] = None
        self.setWindowTitle("Create Summary Group")
        self.setModal(True)
        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build_group(self) -> SummaryGroup:
        if not self._group:
            raise RuntimeError("Dialog was not accepted; no summary group available")
        return self._group

    # ------------------------------------------------------------------
    # UI assembly
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., Clinical Records")
        form.addRow("Name", self.name_edit)

        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("Optional description")
        self.description_edit.setFixedHeight(60)
        form.addRow("Description", self.description_edit)

        self.files_edit = QPlainTextEdit()
        self.files_edit.setPlaceholderText("Enter relative paths, one per line (e.g., medical/doc1.md)")
        self.files_edit.setMinimumHeight(100)
        form.addRow("Files", self.files_edit)

        self.system_prompt_edit = QLineEdit()
        self.system_prompt_button = QPushButton("Browse…")
        self.system_prompt_button.clicked.connect(lambda: self._choose_prompt_file(self.system_prompt_edit))
        form.addRow("System Prompt", self._wrap_with_button(self.system_prompt_edit, self.system_prompt_button))

        self.user_prompt_edit = QLineEdit()
        self.user_prompt_button = QPushButton("Browse…")
        self.user_prompt_button.clicked.connect(lambda: self._choose_prompt_file(self.user_prompt_edit))
        form.addRow("User Prompt", self._wrap_with_button(self.user_prompt_edit, self.user_prompt_button))

        self.model_combo = self._build_model_combo()
        form.addRow("Model", self.model_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _wrap_with_button(self, line_edit: QLineEdit, button: QPushButton) -> QWidget:
        widget = QWidget()
        h_layout = QHBoxLayout(widget)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.addWidget(line_edit)
        h_layout.addWidget(button)
        return widget

    def _build_model_combo(self):
        combo = QComboBox()
        combo.setEditable(False)
        providers = get_available_providers_and_models()
        combo.addItem("(None)", ("", ""))
        for entry in providers:
            combo.addItem(entry["display_name"], (entry["id"], entry["model"]))
        return combo

    def _choose_prompt_file(self, line_edit: QLineEdit) -> None:
        initial_dir = self._project_dir if self._project_dir else Path.cwd()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Prompt File",
            str(initial_dir),
            "Prompt Files (*.txt *.md *.prompt);;All Files (*)",
        )
        if file_path:
            line_edit.setText(self._normalise_path(Path(file_path)))

    # ------------------------------------------------------------------
    # Acceptance
    # ------------------------------------------------------------------
    def _handle_accept(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please provide a name for the summary group.")
            return

        files = [line.strip() for line in self.files_edit.toPlainText().splitlines() if line.strip()]

        provider_id, model = self.model_combo.currentData()
        description = self.description_edit.toPlainText().strip()
        system_prompt = self._normalise_text(self.system_prompt_edit.text().strip())
        user_prompt = self._normalise_text(self.user_prompt_edit.text().strip())

        self._group = SummaryGroup.create(
            name=name,
            description=description,
            files=files,
            provider_id=provider_id,
            model=model,
            system_prompt_path=system_prompt,
            user_prompt_path=user_prompt,
        )
        self.accept()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _normalise_text(self, text: str) -> str:
        if not text:
            return ""
        path = Path(text)
        if not path.is_absolute():
            return text
        return self._normalise_path(path)

    def _normalise_path(self, path: Path) -> str:
        if not path:
            return ""
        if self._project_dir:
            try:
                project_dir = self._project_dir.resolve()
                relative = path.resolve().relative_to(project_dir)
                return str(relative)
            except Exception:
                pass
        return str(path)
