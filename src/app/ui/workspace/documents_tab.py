"""Presentation widget for the dashboard Documents tab."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class DocumentsTab(QWidget):
    """Encapsulate the Documents tab UI elements.

    The tab intentionally keeps behaviour-free for the initial refactor step; it
    merely builds and exposes the widgets so ``ProjectWorkspace`` can continue
    driving the conversion workflow while we migrate logic gradually.
    """

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.source_root_label = QLabel("Source root: not set")
        self.source_root_label.setStyleSheet("font-weight: bold;")

        self.counts_label = QLabel("Re-scan pending…")
        self.last_scan_label = QLabel("")
        self.last_scan_label.setStyleSheet("color: #666;")

        self.rescan_button = QPushButton("Re-scan")

        self.source_tree = QTreeWidget()
        self.source_tree.setHeaderHidden(True)
        self.source_tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.source_tree.setUniformRowHeights(True)

        self.root_warning_label = QLabel("")
        self.root_warning_label.setWordWrap(True)
        self.root_warning_label.setStyleSheet("color: #b26a00;")
        self.root_warning_label.hide()

        self.missing_highlights_label = QLabel("Highlights missing: —")
        self.missing_highlights_label.setWordWrap(True)

        self.missing_bulk_label = QLabel("Bulk analysis missing: —")
        self.missing_bulk_label.setWordWrap(True)

        self._build_layout()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Source root selector header
        root_layout = QHBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.source_root_label)
        root_layout.addStretch()
        layout.addLayout(root_layout)

        # Counts and scan controls
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(self.counts_label)
        header_layout.addStretch()
        header_layout.addWidget(self.last_scan_label)
        header_layout.addWidget(self.rescan_button)
        layout.addLayout(header_layout)

        # Folder tree
        layout.addWidget(self.source_tree)

        # Additional status labels
        layout.addWidget(self.root_warning_label)
        layout.addWidget(self.missing_highlights_label)
        layout.addWidget(self.missing_bulk_label)

        layout.addStretch()

    # Convenience accessors for code that still expects specific widget types
    # ------------------------------------------------------------------
    def add_top_level_item(self, item: QTreeWidgetItem) -> None:
        self.source_tree.addTopLevelItem(item)

    def clear_tree(self) -> None:
        self.source_tree.clear()

