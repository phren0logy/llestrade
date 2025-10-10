"""Reusable widget for editing project placeholder keys/values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QFileDialog,
    QHeaderView,
)

from src.app.core.placeholders import (
    PlaceholderEntry,
    PlaceholderSetDescriptor,
    PlaceholderSetRegistry,
    ProjectPlaceholders,
    parse_placeholder_file,
)
from src.app.core.placeholders.parser import PlaceholderParseError
from src.app.core.placeholders.system import SYSTEM_PLACEHOLDERS
from src.config.placeholder_store import get_placeholder_custom_dir


PLACEHOLDER_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class PlaceholderEditorConfig:
    """Configuration for placeholder editor widget."""

    allow_export: bool = False
    allow_system_keys: bool = True
    system_keys: Optional[Iterable[str]] = None


class PlaceholderEditorWidget(QWidget):
    """Editable table of placeholder keys/values with bundled/custom set picker."""

    def __init__(
        self,
        *,
        parent: Optional[QWidget] = None,
        config: Optional[PlaceholderEditorConfig] = None,
    ) -> None:
        super().__init__(parent)
        self._registry = PlaceholderSetRegistry()
        self._entries: List[PlaceholderEntry] = []
        cfg = config or PlaceholderEditorConfig()
        system_keys = set(cfg.system_keys) if cfg.system_keys is not None else set(SYSTEM_PLACEHOLDERS)
        self._system_keys: Set[str] = system_keys if cfg.allow_system_keys else set()
        self._allow_export = cfg.allow_export

        self._set_combo = QComboBox()
        self._set_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._set_combo.currentIndexChanged.connect(self._on_set_changed)

        self._set_hint = QLabel("")
        self._set_hint.setStyleSheet("color: #666; font-size: 11px;")
        self._set_hint.hide()

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Key", "Value"])
        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self._table.cellChanged.connect(self._on_cell_changed)

        self._summary_label = QLabel("No placeholders configured.")
        self._summary_label.setStyleSheet("color: #666;")

        self._add_btn = QPushButton("Add Placeholder")
        self._add_btn.clicked.connect(self._add_placeholder)
        self._remove_btn = QPushButton("Remove Selected")
        self._remove_btn.clicked.connect(self._remove_selected)
        self._import_btn = QPushButton("Import from File…")
        self._import_btn.clicked.connect(self._import_from_file)
        self._export_btn = QPushButton("Export to Markdown…")
        self._export_btn.clicked.connect(self._export_to_file)
        self._export_btn.setVisible(self._allow_export)

        self._build_layout()
        self.refresh_sets(select_default=True)
        self._ensure_system_entries()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        selector_row = QHBoxLayout()
        selector_row.setContentsMargins(0, 0, 0, 0)
        selector_row.setSpacing(6)
        selector_row.addWidget(self._set_combo, stretch=1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(lambda: self.refresh_sets(select_default=False))
        selector_row.addWidget(refresh_btn)
        selector_row.addWidget(self._import_btn)
        if self._allow_export:
            selector_row.addWidget(self._export_btn)

        layout.addLayout(selector_row)
        layout.addWidget(self._set_hint)
        layout.addWidget(self._table, stretch=1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)
        button_row.addWidget(self._add_btn)
        button_row.addWidget(self._remove_btn)
        button_row.addStretch()
        layout.addLayout(button_row)
        layout.addWidget(self._summary_label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh_sets(self, *, select_default: bool = False) -> None:
        """Reload bundled/custom placeholder sets into the combo."""

        self._set_combo.blockSignals(True)
        self._set_combo.clear()
        self._set_combo.addItem("No placeholder set", None)
        descriptors: List[PlaceholderSetDescriptor] = []
        try:
            self._registry.refresh()
            descriptors = self._registry.all_sets()
        except Exception:
            descriptors = []

        for descriptor in descriptors:
            prefix = "Custom" if descriptor.origin == "custom" else "Bundled"
            self._set_combo.addItem(f"{prefix}: {descriptor.name}", descriptor)

        self._set_combo.blockSignals(False)
        self._set_hint.hide()

        if select_default and descriptors:
            self._set_combo.setCurrentIndex(1)
        else:
            self._set_combo.setCurrentIndex(0)

    def set_placeholders(self, placeholders: ProjectPlaceholders) -> None:
        """Populate the table from existing project placeholders."""

        self._entries = [
            PlaceholderEntry(key=entry.key, value=entry.value, read_only=entry.read_only)
            for entry in placeholders.entries
        ]
        self._ensure_system_entries()
        self._refresh_table()

    def placeholders(self) -> ProjectPlaceholders:
        """Return placeholders represented by the widget."""

        payload = ProjectPlaceholders()
        for entry in self._entries:
            payload.set_value(entry.key, entry.value, read_only=entry.read_only)
        return payload

    def validate(self, *, parent: Optional[QWidget] = None) -> bool:
        """Validate placeholder entries (keys unique, snake_case)."""

        if parent is None:
            parent = self
        seen: Set[str] = set()
        for row, entry in enumerate(self._entries):
            key = entry.key.strip()
            if not key:
                QMessageBox.warning(parent, "Placeholder Key Required", "All placeholders must have a key (snake_case).")
                self._select_row(row, edit_column=0)
                return False
            if not PLACEHOLDER_KEY_RE.fullmatch(key):
                QMessageBox.warning(
                    parent,
                    "Invalid Placeholder Key",
                    f"Placeholder '{key}' must be snake_case (letters, numbers, underscores).",
                )
                self._select_row(row, edit_column=0)
                return False
            if key in seen:
                QMessageBox.warning(parent, "Duplicate Placeholder Key", f"Placeholder '{key}' is duplicated.")
                self._select_row(row, edit_column=0)
                return False
            seen.add(key)
            entry.key = key
        return True

    def set_system_value(self, key: str, value: str) -> None:
        """Update the value for a system placeholder (if it exists)."""

        for entry in self._entries:
            if entry.key == key:
                entry.value = value
                self._update_table_row(entry)
                break

    # ------------------------------------------------------------------
    # Internal logic
    # ------------------------------------------------------------------
    def _ensure_system_entries(self) -> None:
        if not self._system_keys:
            return
        existing = {entry.key: entry for entry in self._entries}
        for key in sorted(self._system_keys):
            if key in existing:
                existing[key].read_only = True
            else:
                self._entries.append(PlaceholderEntry(key=key, value="", read_only=True))
        self._entries.sort(key=lambda e: (0 if e.read_only else 1, e.key))

    def _on_set_changed(self, index: int) -> None:
        descriptor = self._set_combo.itemData(index)
        if descriptor is None:
            self._set_hint.hide()
            return
        if not isinstance(descriptor, PlaceholderSetDescriptor):
            return
        self._apply_placeholder_keys(descriptor.keys)
        origin = "Custom" if descriptor.origin == "custom" else "Bundled"
        self._set_hint.setText(f"Loaded from {origin.lower()} placeholder set '{descriptor.name}'.")
        self._set_hint.show()

    def _apply_placeholder_keys(self, keys: Sequence[str]) -> None:
        """Merge placeholder keys from a set, preserving existing values where possible."""

        existing = {entry.key: entry for entry in self._entries}
        new_entries: List[PlaceholderEntry] = []
        seen: Set[str] = set()
        for key in keys:
            seen.add(key)
            if key in existing:
                entry = existing[key]
                new_entries.append(PlaceholderEntry(key=entry.key, value=entry.value, read_only=entry.read_only))
            else:
                read_only = key in self._system_keys
                new_entries.append(PlaceholderEntry(key=key, value="", read_only=read_only))

        # Preserve extra entries not in the set (custom additions)
        for entry in self._entries:
            if entry.key not in seen:
                new_entries.append(PlaceholderEntry(key=entry.key, value=entry.value, read_only=entry.read_only))

        self._entries = new_entries
        self._ensure_system_entries()
        self._refresh_table()

    def _refresh_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            key_item = QTableWidgetItem(entry.key)
            value_item = QTableWidgetItem(entry.value)
            if entry.read_only:
                flags = key_item.flags() & ~Qt.ItemIsEditable
                key_item.setFlags(flags)
                value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
                key_item.setForeground(QColor(120, 120, 120))
                value_item.setForeground(QColor(120, 120, 120))
            self._table.setItem(row, 0, key_item)
            self._table.setItem(row, 1, value_item)
        self._table.blockSignals(False)
        self._update_summary()

    def _update_table_row(self, entry: PlaceholderEntry) -> None:
        for row, current in enumerate(self._entries):
            if current is entry:
                self._table.blockSignals(True)
                self._table.item(row, 0).setText(entry.key)
                self._table.item(row, 1).setText(entry.value)
                self._table.blockSignals(False)
                break
        self._update_summary()

    def _on_cell_changed(self, row: int, column: int) -> None:
        if not (0 <= row < len(self._entries)):
            return
        item = self._table.item(row, column)
        if not item:
            return
        entry = self._entries[row]
        if column == 0:
            entry.key = item.text().strip()
        else:
            entry.value = item.text()
        self._update_summary()

    def _update_summary(self) -> None:
        total = len(self._entries)
        if not total:
            self._summary_label.setText("No placeholders configured.")
        else:
            self._summary_label.setText(f"{total} placeholder{'s' if total != 1 else ''} configured.")

    def _add_placeholder(self) -> None:
        self._entries.append(PlaceholderEntry(key="", value=""))
        self._refresh_table()
        self._select_row(len(self._entries) - 1, edit_column=0)

    def _remove_selected(self) -> None:
        selection = self._table.selectionModel().selectedRows()
        if not selection:
            return
        row = selection[0].row()
        entry = self._entries[row]
        if entry.read_only:
            QMessageBox.information(
                self,
                "Cannot Remove Placeholder",
                "System placeholders cannot be removed.",
            )
            return
        del self._entries[row]
        self._refresh_table()

    def _import_from_file(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select Placeholder List",
            str(Path.home()),
            "Markdown Files (*.md)",
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            parsed = parse_placeholder_file(path)
        except PlaceholderParseError as exc:
            QMessageBox.warning(self, "Invalid Placeholder File", str(exc))
            return
        self._apply_placeholder_keys(parsed.keys)

        dest_dir = get_placeholder_custom_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / path.name
        try:
            if path.resolve() != dest_path.resolve():
                dest_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Import Failed",
                f"Could not copy placeholder file:\n\n{exc}",
            )
            return

        self.refresh_sets(select_default=False)

        target_name = dest_path.stem
        for index in range(self._set_combo.count()):
            descriptor = self._set_combo.itemData(index)
            if (
                isinstance(descriptor, PlaceholderSetDescriptor)
                and descriptor.origin == "custom"
                and descriptor.name == target_name
            ):
                self._set_combo.setCurrentIndex(index)
                break
        else:
            self._set_hint.setText(f"Loaded from file: {path.name}")
            self._set_hint.show()

    def _export_to_file(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export Placeholder List",
            str(Path.home() / "placeholder_set.md"),
            "Markdown Files (*.md)",
        )
        if not path_str:
            return
        path = Path(path_str)
        keys = [entry.key for entry in self._entries]
        content = "\n".join(f"- {key}" for key in keys)
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Export Failed", f"Could not write file: {exc}")

    def _select_row(self, row: int, *, edit_column: int = 1) -> None:
        if not (0 <= row < self._table.rowCount()):
            return
        self._table.selectRow(row)
        self._table.scrollToItem(self._table.item(row, 0))
        item = self._table.item(row, edit_column)
        if item and not self._entries[row].read_only:
            self._table.editItem(item)


__all__ = ["PlaceholderEditorWidget", "PlaceholderEditorConfig"]
