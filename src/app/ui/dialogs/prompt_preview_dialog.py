"""Modal dialog that displays rendered system/user prompts side by side."""

from __future__ import annotations

from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)


class PromptPreviewDialog(QDialog):
    """Simple dialog that renders the system and user prompts."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Prompt Preview")
        self.resize(900, 600)

        main_layout = QVBoxLayout(self)
        panes = QHBoxLayout()
        panes.setSpacing(12)

        self._system_edit = self._create_text_pane("System Prompt")
        self._user_edit = self._create_text_pane("User Prompt")

        panes.addWidget(self._system_edit)
        panes.addWidget(self._user_edit)
        main_layout.addLayout(panes)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        main_layout.addWidget(buttons)

    def _create_text_pane(self, title: str) -> QPlainTextEdit:
        container = QPlainTextEdit()
        container.setReadOnly(True)
        font = QFont("Courier New")
        font.setStyleHint(QFont.Monospace)
        container.setFont(font)
        container.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        container.setPlaceholderText(title)
        container.setToolTip(title)
        return container

    def set_prompts(self, system_prompt: str, user_prompt: str) -> None:
        self._system_edit.setPlainText(system_prompt)
        self._user_edit.setPlainText(user_prompt)
        self._system_edit.moveCursor(QTextCursor.Start)
        self._user_edit.moveCursor(QTextCursor.Start)


__all__ = ["PromptPreviewDialog"]
