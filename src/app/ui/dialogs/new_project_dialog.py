"""Dialog for creating a new project with source/output configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.app.core.project_manager import _ensure_unique_dir, _sanitize_project_folder
from src.app.core.conversion_helpers import registry, ConversionHelper
from src.app.core.placeholders import (
    PlaceholderEntry,
    PlaceholderSetDescriptor,
    PlaceholderSetRegistry,
    ProjectPlaceholders,
    parse_placeholder_file,
)
from src.app.core.placeholders.parser import PlaceholderParseError




def _available_helpers() -> List[ConversionHelper]:
    return registry().list_helpers()


PLACEHOLDER_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class NewProjectConfig:
    name: str
    subject_name: str
    date_of_birth: str
    case_description: str
    source_root: Path
    selected_folders: List[str]
    output_base: Path
    conversion_helper: str
    conversion_options: Dict[str, Any]
    placeholders: ProjectPlaceholders = field(default_factory=ProjectPlaceholders)


class NewProjectDialog(QDialog):
    """Collect project name, source root (with folder selections) and output base."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Project")
        self.resize(640, 520)

        self._project_name_edit = QLineEdit()
        self._subject_name_edit = QLineEdit()
        self._subject_name_edit.setPlaceholderText("e.g., Jane Doe")
        self._dob_edit = QLineEdit()
        self._dob_edit.setPlaceholderText("e.g., 1975-08-19")
        self._case_info_edit = QPlainTextEdit()
        self._case_info_edit.setPlaceholderText("Key case context, referral questions, etc.")
        self._case_info_edit.setFixedHeight(80)
        self._source_line = QLineEdit()
        self._source_line.setReadOnly(True)
        self._output_line = QLineEdit()
        self._output_line.setReadOnly(True)

        self._placeholder_registry = PlaceholderSetRegistry()
        self._placeholder_entries: List[PlaceholderEntry] = []
        self._placeholder_combo = QComboBox()
        self._placeholder_table = QTableWidget(0, 2)
        self._placeholder_table.setHorizontalHeaderLabels(["Key", "Value"])
        self._placeholder_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._placeholder_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._placeholder_table.verticalHeader().setVisible(False)
        self._placeholder_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._placeholder_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._placeholder_table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self._placeholder_table.cellChanged.connect(self._on_placeholder_cell_changed)
        self._placeholder_add_btn = QPushButton("Add Placeholder")
        self._placeholder_remove_btn = QPushButton("Remove Selected")
        self._placeholder_info_label = QLabel("No placeholders selected.")
        self._placeholder_info_label.setStyleSheet("color: #666;")
        self._placeholder_source_hint = QLabel("")
        self._placeholder_source_hint.setStyleSheet("color: #666; font-size: 11px;")
        self._placeholder_source_hint.hide()
        self._placeholder_combo.currentIndexChanged.connect(self._on_placeholder_set_changed)
        self._placeholder_add_btn.clicked.connect(self._add_placeholder_row)
        self._placeholder_remove_btn.clicked.connect(self._remove_selected_placeholder)
        self._current_placeholder_set: Optional[str] = None

        self._folder_preview_label = QLabel("Select an output location to preview the project folder.")
        self._folder_preview_label.setWordWrap(True)
        self._folder_preview_label.setStyleSheet("color: #666;")

        self._helper_combo = QComboBox()
        self._helper_description_label = QLabel("")
        self._helper_description_label.setWordWrap(True)
        self._helper_description_label.setStyleSheet("color: #555;")
        self._helper_options_container = QVBoxLayout()
        self._helper_options_container.setContentsMargins(0, 0, 0, 0)
        self._helper_options_container.setSpacing(4)
        self._helper_option_widgets: Dict[str, QCheckBox] = {}
        self._helper_options_state: Dict[str, Any] = {}

        self._source_tree = QTreeWidget()
        self._source_tree.setHeaderHidden(True)
        self._source_tree.setSelectionMode(QTreeWidget.NoSelection)
        self._source_tree.itemChanged.connect(self._on_item_changed)

        self._root_notice = QLabel("Select a source folder to populate available subfolders.")
        self._root_notice.setWordWrap(True)
        self._root_notice.setStyleSheet("color: #666;")

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #b26a00;")
        self._status_label.hide()

        self._selected_folders: List[str] = []
        self._auto_select = True
        self._source_root: Optional[Path] = None
        self._output_base: Optional[Path] = None
        self._current_warnings: List[str] = []

        self._build_ui()
        self._populate_placeholder_sets()
        self._refresh_placeholder_table()
        self._init_helper_controls()
        self._project_name_edit.textChanged.connect(self._update_folder_preview)

        self._result: Optional[NewProjectConfig] = None

    # ------------------------------------------------------------------
    # UI assembly
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        form.addRow("Project name:", self._project_name_edit)

        form.addRow("Subject name:", self._subject_name_edit)
        form.addRow("Subject DOB:", self._dob_edit)
        form.addRow("Case info:", self._case_info_edit)

        placeholder_container = QWidget()
        placeholder_layout = QVBoxLayout(placeholder_container)
        placeholder_layout.setContentsMargins(0, 0, 0, 0)
        placeholder_layout.setSpacing(6)

        placeholder_source_row = QHBoxLayout()
        placeholder_source_row.setContentsMargins(0, 0, 0, 0)
        placeholder_source_row.setSpacing(6)
        placeholder_source_row.addWidget(self._placeholder_combo, stretch=1)
        placeholder_browse_btn = QPushButton("Browse…")
        placeholder_browse_btn.clicked.connect(self._browse_placeholder_file)
        placeholder_source_row.addWidget(placeholder_browse_btn)
        placeholder_layout.addLayout(placeholder_source_row)
        placeholder_layout.addWidget(self._placeholder_source_hint)

        placeholder_layout.addWidget(self._placeholder_table, stretch=1)

        placeholder_controls = QHBoxLayout()
        placeholder_controls.setContentsMargins(0, 0, 0, 0)
        placeholder_controls.setSpacing(6)
        placeholder_controls.addWidget(self._placeholder_add_btn)
        placeholder_controls.addWidget(self._placeholder_remove_btn)
        placeholder_controls.addStretch()
        placeholder_layout.addLayout(placeholder_controls)
        placeholder_layout.addWidget(self._placeholder_info_label)

        form.addRow("Placeholders:", placeholder_container)

        source_row = QHBoxLayout()
        source_row.addWidget(self._source_line)
        source_btn = QPushButton("Choose…")
        source_btn.clicked.connect(self._select_source_root)
        source_row.addWidget(source_btn)
        form.addRow("Source folder:", source_row)

        output_row = QHBoxLayout()
        output_row.addWidget(self._output_line)
        output_btn = QPushButton("Choose…")
        output_btn.clicked.connect(self._select_output_base)
        output_row.addWidget(output_btn)
        form.addRow("Output location:", output_row)

        folder_container = QWidget()
        folder_layout = QVBoxLayout(folder_container)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(4)
        self._folder_preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        folder_layout.addWidget(self._folder_preview_label)
        form.addRow("Project folder:", folder_container)

        helper_layout = QVBoxLayout()
        helper_layout.setContentsMargins(0, 0, 0, 0)
        helper_layout.setSpacing(6)
        self._helper_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._helper_description_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        helper_layout.addWidget(self._helper_combo)
        helper_layout.addWidget(self._helper_description_label)

        options_host = QWidget()
        options_host.setLayout(self._helper_options_container)
        helper_layout.addWidget(options_host)

        helper_widget = QWidget()
        helper_widget.setLayout(helper_layout)
        form.addRow("Conversion helper:", helper_widget)

        layout.addLayout(form)
        layout.addWidget(self._root_notice)
        layout.addWidget(self._source_tree, stretch=1)
        layout.addWidget(self._status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def result_config(self) -> Optional[NewProjectConfig]:
        return self._result

    def current_warnings(self) -> List[str]:
        return list(self._current_warnings)

    # ------------------------------------------------------------------
    # Slots and helpers
    # ------------------------------------------------------------------
    def _select_source_root(self) -> None:
        start_dir = self._source_root.as_posix() if self._source_root else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select Source Folder", start_dir)
        if not chosen:
            return
        self._source_root = Path(chosen).resolve()
        self._source_line.setText(self._source_root.as_posix())
        self._populate_tree()

    def _select_output_base(self) -> None:
        start_dir = self._output_base.as_posix() if self._output_base else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select Output Location", start_dir)
        if not chosen:
            return
        self._output_base = Path(chosen).resolve()
        self._output_line.setText(self._output_base.as_posix())
        self._update_folder_preview()

    def _populate_tree(self) -> None:
        self._source_tree.blockSignals(True)
        self._source_tree.clear()
        self._source_tree.blockSignals(False)
        self._selected_folders.clear()
        self._status_label.hide()

        if not self._source_root or not self._source_root.exists():
            self._root_notice.setText("Select a valid source folder to continue.")
            return

        directories = sorted(self._iter_directories(self._source_root))
        if not directories:
            self._root_notice.setText(
                "No subfolders detected. Create subfolders to include documents in processing."
            )
        else:
            self._root_notice.setText(
                "Toggle folders to include them in conversion. All folders are selected by default."
            )

        self._auto_select = True
        for relative in directories:
            parts = relative.split("/")
            parent = self._source_tree.invisibleRootItem()
            path_parts: List[str] = []
            for part in parts:
                path_parts.append(part)
                rel_key = "/".join(path_parts)
                child = self._find_child(parent, part)
                if child is None:
                    child = QTreeWidgetItem([part])
                    child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                    child.setData(0, Qt.UserRole, rel_key)
                    child.setCheckState(0, Qt.Checked)
                    parent.addChild(child)
                parent = child

        self._selected_folders = self._collect_selected()
        self._auto_select = False
        self._update_status()

    def _iter_directories(self, root: Path) -> List[str]:
        results: List[str] = []
        for path in root.rglob("*"):
            if path.is_dir():
                results.append(path.relative_to(root).as_posix())
        return results

    def _find_child(self, parent: QTreeWidgetItem, name: str) -> Optional[QTreeWidgetItem]:
        for idx in range(parent.childCount()):
            child = parent.child(idx)
            if child.text(0) == name:
                return child
        return None

    def _collect_selected(self) -> List[str]:
        selected: List[str] = []
        root = self._source_tree.invisibleRootItem()
        stack = [root]
        while stack:
            current = stack.pop()
            for idx in range(current.childCount()):
                child = current.child(idx)
                stack.append(child)
                if child.checkState(0) == Qt.Checked:
                    rel = child.data(0, Qt.UserRole)
                    if rel:
                        selected.append(str(rel))
        selected.sort()
        return selected

    def _set_partial_state(self, item: QTreeWidgetItem) -> None:
        checked = 0
        unchecked = 0
        for idx in range(item.childCount()):
            state = item.child(idx).checkState(0)
            if state == Qt.Checked:
                checked += 1
            elif state == Qt.Unchecked:
                unchecked += 1
        if checked and unchecked:
            item.setCheckState(0, Qt.PartiallyChecked)
        elif checked:
            item.setCheckState(0, Qt.Checked)
        else:
            item.setCheckState(0, Qt.Unchecked)

    def _update_parents(self, item: Optional[QTreeWidgetItem]) -> None:
        while item is not None and item is not self._source_tree.invisibleRootItem():
            self._set_partial_state(item)
            item = item.parent()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0 or self._auto_select:
            return
        state = item.checkState(0)

        def cascade(node: QTreeWidgetItem, target_state: Qt.CheckState) -> None:
            for idx in range(node.childCount()):
                child = node.child(idx)
                child.setCheckState(0, target_state)
                cascade(child, target_state)

        cascade(item, state)
        self._update_parents(item.parent())
        self._selected_folders = self._collect_selected()
        self._auto_select = False
        self._update_status()

    def _update_status(self) -> None:
        warnings: List[str] = []
        if self._source_root and any(child.is_file() for child in self._source_root.iterdir()):
            warnings.append(
                "Files in the source root will be ignored. Place documents inside subfolders."
            )
        if not self._selected_folders:
            warnings.append("Select at least one folder to include in conversion.")

        self._current_warnings = warnings
        if warnings:
            self._status_label.setText("\n".join(warnings))
            self._status_label.show()
        else:
            self._status_label.clear()
            self._status_label.hide()

    # ------------------------------------------------------------------
    # Placeholder set management
    # ------------------------------------------------------------------
    def _populate_placeholder_sets(self) -> None:
        self._placeholder_combo.blockSignals(True)
        self._placeholder_combo.clear()
        self._placeholder_combo.addItem("No placeholder set", None)
        try:
            self._placeholder_registry.refresh()
            descriptors = self._placeholder_registry.all_sets()
        except Exception:
            descriptors = []

        for descriptor in descriptors:
            prefix = "Custom" if descriptor.origin == "custom" else "Bundled"
            label = f"{prefix}: {descriptor.name}"
            self._placeholder_combo.addItem(label, descriptor)

        self._placeholder_combo.addItem("Browse…", "__browse__")
        self._placeholder_combo.setCurrentIndex(0)
        self._placeholder_combo.blockSignals(False)
        self._set_placeholder_source_hint(None)

    def _set_placeholder_source_hint(self, text: Optional[str]) -> None:
        if text:
            self._placeholder_source_hint.setText(text)
            self._placeholder_source_hint.show()
        else:
            self._placeholder_source_hint.clear()
            self._placeholder_source_hint.hide()

    def _on_placeholder_set_changed(self, index: int) -> None:
        data = self._placeholder_combo.itemData(index)
        if data == "__browse__":
            self._placeholder_combo.blockSignals(True)
            self._placeholder_combo.setCurrentIndex(0)
            self._placeholder_combo.blockSignals(False)
            self._browse_placeholder_file()
            return

        if not data:
            self._set_placeholder_source_hint(None)
            return

        descriptor: PlaceholderSetDescriptor = data
        self._apply_placeholder_keys(descriptor.keys)
        origin = "Custom" if descriptor.origin == "custom" else "Bundled"
        self._current_placeholder_set = descriptor.name
        self._set_placeholder_source_hint(f"Loaded from {origin.lower()} placeholder set '{descriptor.name}'.")

    def _apply_placeholder_keys(self, keys: Sequence[str]) -> None:
        existing_map = {entry.key: entry for entry in self._placeholder_entries}
        new_entries: List[PlaceholderEntry] = []
        seen: set[str] = set()
        for key in keys:
            existing = existing_map.get(key)
            if existing:
                new_entries.append(PlaceholderEntry(key=existing.key, value=existing.value, read_only=existing.read_only))
            else:
                new_entries.append(PlaceholderEntry(key=key, value=""))
            seen.add(key)

        for entry in self._placeholder_entries:
            if entry.key not in seen:
                new_entries.append(PlaceholderEntry(key=entry.key, value=entry.value, read_only=entry.read_only))

        self._placeholder_entries = new_entries
        self._refresh_placeholder_table()

    def _refresh_placeholder_table(self, *, select_row: Optional[int] = None, edit_key: bool = False) -> None:
        self._placeholder_table.blockSignals(True)
        self._placeholder_table.setRowCount(len(self._placeholder_entries))
        for row, entry in enumerate(self._placeholder_entries):
            key_item = QTableWidgetItem(entry.key)
            value_item = QTableWidgetItem(entry.value)
            if entry.read_only:
                key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable)
                value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
                key_item.setForeground(QColor(120, 120, 120))
                value_item.setForeground(QColor(120, 120, 120))
            self._placeholder_table.setItem(row, 0, key_item)
            self._placeholder_table.setItem(row, 1, value_item)
        self._placeholder_table.blockSignals(False)
        self._update_placeholder_summary()

        if select_row is not None and 0 <= select_row < self._placeholder_table.rowCount():
            self._placeholder_table.selectRow(select_row)
            if edit_key:
                self._placeholder_table.editItem(self._placeholder_table.item(select_row, 0))
            else:
                self._placeholder_table.editItem(self._placeholder_table.item(select_row, 1))

    def _update_placeholder_summary(self) -> None:
        total = len(self._placeholder_entries)
        if not total:
            self._placeholder_info_label.setText("No custom placeholders configured.")
        else:
            self._placeholder_info_label.setText(f"{total} placeholder{'s' if total != 1 else ''} configured.")

    def _on_placeholder_cell_changed(self, row: int, column: int) -> None:
        if not (0 <= row < len(self._placeholder_entries)):
            return
        item = self._placeholder_table.item(row, column)
        if not item:
            return
        entry = self._placeholder_entries[row]
        if column == 0:
            entry.key = item.text().strip()
        else:
            entry.value = item.text()
        self._update_placeholder_summary()

    def _add_placeholder_row(self) -> None:
        entry = PlaceholderEntry(key="", value="")
        self._placeholder_entries.append(entry)
        self._refresh_placeholder_table(select_row=len(self._placeholder_entries) - 1, edit_key=True)

    def _remove_selected_placeholder(self) -> None:
        selected_rows = self._placeholder_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        entry = self._placeholder_entries[row]
        if entry.read_only:
            QMessageBox.information(
                self,
                "Cannot Remove Placeholder",
                "System placeholders cannot be removed.",
            )
            return
        del self._placeholder_entries[row]
        self._refresh_placeholder_table()

    def _browse_placeholder_file(self) -> None:
        start_dir = str(self._source_root) if self._source_root else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Placeholder List",
            start_dir,
            "Markdown Files (*.md)",
        )
        if not path:
            return
        try:
            parsed = parse_placeholder_file(Path(path))
        except PlaceholderParseError as exc:
            QMessageBox.warning(self, "Invalid Placeholder File", str(exc))
            return
        self._apply_placeholder_keys(parsed.keys)
        self._set_placeholder_source_hint(f"Loaded from file: {Path(path).name}")
        self._current_placeholder_set = Path(path).name

    def _validate_placeholder_entries(self) -> bool:
        seen: set[str] = set()
        for row, entry in enumerate(self._placeholder_entries):
            key = entry.key.strip()
            if not key:
                QMessageBox.warning(self, "Placeholder Key Required", "All placeholders must have a key (snake_case).")
                self._placeholder_table.selectRow(row)
                self._placeholder_table.editItem(self._placeholder_table.item(row, 0))
                return False
            if not PLACEHOLDER_KEY_RE.fullmatch(key):
                QMessageBox.warning(
                    self,
                    "Invalid Placeholder Key",
                    f"Placeholder '{key}' must be snake_case (letters, numbers, underscores).",
                )
                self._placeholder_table.selectRow(row)
                self._placeholder_table.editItem(self._placeholder_table.item(row, 0))
                return False
            if key in seen:
                QMessageBox.warning(self, "Duplicate Placeholder Key", f"Placeholder '{key}' is duplicated. Keys must be unique.")
                self._placeholder_table.selectRow(row)
                return False
            entry.key = key
            seen.add(key)
        return True

    def _collect_project_placeholders(self) -> ProjectPlaceholders:
        placeholders = ProjectPlaceholders()
        for entry in self._placeholder_entries:
            placeholders.set_value(entry.key, entry.value, read_only=entry.read_only)
        return placeholders

    def _init_helper_controls(self) -> None:
        self._helper_combo.blockSignals(True)
        self._helper_combo.clear()
        for helper in _available_helpers():
            self._helper_combo.addItem(helper.name, userData=helper.helper_id)
        self._helper_combo.blockSignals(False)
        self._helper_combo.currentIndexChanged.connect(self._on_helper_changed)
        self._on_helper_changed(self._helper_combo.currentIndex())

    def _on_helper_changed(self, index: int) -> None:
        helper_key = self._helper_combo.itemData(index)
        helper = registry().get(helper_key) if helper_key else None
        if helper is None:
            helper = registry().default_helper()
        self._helper_description_label.setText(helper.description)

        while self._helper_options_container.count():
            item = self._helper_options_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._helper_option_widgets.clear()
        self._helper_options_state.clear()

        options = helper.options
        if not options:
            placeholder = QLabel("No additional settings for this helper.")
            placeholder.setStyleSheet("color: #777;")
            self._helper_options_container.addWidget(placeholder)
            return

        for option in options:
            if option.option_type == "checkbox":
                checkbox = QCheckBox(option.label)
                checked = bool(option.default)
                checkbox.setChecked(checked)
                if option.tooltip:
                    checkbox.setToolTip(option.tooltip)
                checkbox.stateChanged.connect(
                    lambda state, key=option.key: self._on_option_changed(
                        key, state == Qt.CheckState.Checked.value
                    )
                )
                self._helper_option_widgets[option.key] = checkbox
                self._helper_options_state[option.key] = checked
                self._helper_options_container.addWidget(checkbox)
            else:
                unsupported = QLabel(f"Unsupported option type: {option.option_type}")
                unsupported.setStyleSheet("color: #b26a00;")
                self._helper_options_container.addWidget(unsupported)

    def _on_option_changed(self, key: str, value: bool) -> None:
        self._helper_options_state[key] = value

    def _current_helper_key(self) -> str:
        index = self._helper_combo.currentIndex()
        helper_key = self._helper_combo.itemData(index)
        helper_key = helper_key or registry().default_helper().helper_id
        return helper_key

    def _current_helper_options(self) -> Dict[str, Any]:
        return dict(self._helper_options_state)

    def _update_folder_preview(self) -> None:
        name = self._project_name_edit.text().strip()
        if not name:
            self._folder_preview_label.setText("Enter a project name to preview the folder name.")
            return

        sanitized = _sanitize_project_folder(name)
        if not self._output_base:
            self._folder_preview_label.setText(
                f"Folder will be named '{sanitized}'. Select an output location to preview the full path."
            )
            return

        candidate = _ensure_unique_dir(self._output_base, sanitized)
        candidate_display = candidate.as_posix()
        if candidate.name != sanitized:
            self._folder_preview_label.setText(
                f"Existing folder detected. Project will use '{candidate_display}'."
            )
        else:
            self._folder_preview_label.setText(
                f"Project folder will be created at '{candidate_display}'."
            )

    def _on_accept(self) -> None:
        name = self._project_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Project Name Required", "Enter a project name to continue.")
            return
        if not self._source_root:
            QMessageBox.warning(self, "Source Required", "Select a source folder to continue.")
            return
        if not self._output_base:
            QMessageBox.warning(self, "Output Required", "Select an output location to continue.")
            return
        if not self._selected_folders:
            QMessageBox.warning(self, "No Folders Selected", "Select at least one folder to include.")
            return

        if not self._validate_placeholder_entries():
            return

        config = NewProjectConfig(
            name=name,
            subject_name=self._subject_name_edit.text().strip(),
            date_of_birth=self._dob_edit.text().strip(),
            case_description=self._case_info_edit.toPlainText().strip(),
            source_root=self._source_root,
            selected_folders=list(self._selected_folders),
            output_base=self._output_base,
            conversion_helper=self._current_helper_key(),
            conversion_options=self._current_helper_options(),
            placeholders=self._collect_project_placeholders(),
        )
        self._result = config
        self.accept()
