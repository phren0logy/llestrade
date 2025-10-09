"""Presentation widget for the highlights tab."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from src.app.ui.widgets import SmartBanner


class HighlightsTab(QWidget):
    """Encapsulate the highlights dashboard UI widgets."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.counts_label = QLabel("Highlights extracted: 0 | Pending: 0")
        self.counts_label.setWordWrap(False)

        self.last_run_label = QLabel("Last run: —")
        self.last_run_label.setStyleSheet("color: #666;")

        self.status_label = QLabel("Highlights have not been extracted yet.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #555;")

        self.extract_button = QPushButton("Extract Highlights")
        self.extract_button.setEnabled(False)

        self.open_folder_button = QPushButton("Open Highlights Folder")
        self.open_folder_button.setEnabled(False)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Category", "Relative Path"])
        self.tree.setIndentation(18)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setHeaderHidden(False)
        self.tree.setWordWrap(True)

        self.pending_banner = SmartBanner(parent=self)
        self.pending_banner.hide()

        self.pending_list = QListWidget()
        self.pending_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.pending_list.setUniformItemSizes(True)
        self.pending_list.setMinimumHeight(140)
        self.pending_list.hide()

        self._build_layout()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(self.counts_label)
        header_layout.addStretch()
        header_layout.addWidget(self.last_run_label)
        layout.addLayout(header_layout)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addWidget(self.extract_button)
        button_row.addWidget(self.open_folder_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        layout.addWidget(self.status_label)
        layout.addWidget(self.pending_banner)
        layout.addWidget(self.pending_list)
        layout.addWidget(self.tree, stretch=1)


__all__ = ["HighlightsTab"]
