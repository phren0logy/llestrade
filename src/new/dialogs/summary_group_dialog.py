"""Dialog for creating summary groups."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import Qt
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
    QTreeWidget,
    QTreeWidgetItem,
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
        self._populate_file_tree()

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

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setUniformRowHeights(True)
        self.file_tree.itemChanged.connect(self._on_tree_item_changed)
        self._block_tree_signal = False
        form.addRow("Documents", self.file_tree)

        self.manual_files_edit = QPlainTextEdit()
        self.manual_files_edit.setPlaceholderText("Additional files (one per line, optional)")
        self.manual_files_edit.setMinimumHeight(60)
        form.addRow("Extra Files", self.manual_files_edit)

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

        tree_files, directories = self._collect_selection()
        manual_files = [self._normalise_text(line.strip()) for line in self.manual_files_edit.toPlainText().splitlines() if line.strip()]
        files_set = {self._normalise_text(path) for path in tree_files if path}
        files_set.update(manual_files)
        files = sorted(files_set)

        directories = sorted({self._normalise_directory(path) for path in directories if path})

        provider_id, model = self.model_combo.currentData()
        description = self.description_edit.toPlainText().strip()
        system_prompt = self._normalise_text(self.system_prompt_edit.text().strip())
        user_prompt = self._normalise_text(self.user_prompt_edit.text().strip())

        self._group = SummaryGroup.create(
            name=name,
            description=description,
            files=files,
            directories=directories,
            provider_id=provider_id,
            model=model,
            system_prompt_path=system_prompt,
            user_prompt_path=user_prompt,
        )
        self.accept()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _populate_file_tree(self) -> None:
        self.file_tree.clear()
        if not self._project_dir:
            notice = QTreeWidgetItem(["No project directory available."])
            notice.setFlags(Qt.NoItemFlags)
            self.file_tree.addTopLevelItem(notice)
            return

        converted_root = self._project_dir / "converted_documents"
        if not converted_root.exists():
            notice = QTreeWidgetItem(["No converted documents found. Run conversion first."])
            notice.setFlags(Qt.NoItemFlags)
            self.file_tree.addTopLevelItem(notice)
            return

        converted_files = sorted(
            path.relative_to(converted_root).as_posix()
            for path in converted_root.rglob("*")
            if path.is_file()
        )

        if not converted_files:
            notice = QTreeWidgetItem(["Converted folder is empty. Run conversion first."])
            notice.setFlags(Qt.NoItemFlags)
            self.file_tree.addTopLevelItem(notice)
            return

        self._tree_nodes = {}
        self._block_tree_signal = True
        for path in converted_files:
            self._add_path_to_tree(path)
        self.file_tree.expandAll()
        self._block_tree_signal = False

    def _add_path_to_tree(self, relative_path: str) -> None:
        parts = relative_path.split("/")
        current_path = ""
        parent_item = self.file_tree.invisibleRootItem()

        for index, part in enumerate(parts):
            current_path = f"{current_path}/{part}" if current_path else part
            is_file = index == len(parts) - 1
            key = (current_path, is_file)

            existing = self._tree_nodes.get(key)
            if existing:
                parent_item = existing
                continue

            item = QTreeWidgetItem(parent_item, [part])
            item.setData(0, Qt.UserRole, ("file" if is_file else "dir", current_path))
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if not is_file:
                flags |= Qt.ItemFlag.ItemIsAutoTristate
            item.setFlags(flags)
            item.setCheckState(0, Qt.Unchecked)

            if not is_file:
                self._tree_nodes[(current_path, False)] = item
            else:
                self._tree_nodes[(current_path, True)] = item

            parent_item = item

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._block_tree_signal:
            return
        node_type, _ = item.data(0, Qt.UserRole) or (None, None)
        if node_type != "dir":
            return
        state = item.checkState(0)
        self._block_tree_signal = True
        for index in range(item.childCount()):
            child = item.child(index)
            child.setCheckState(0, state)
        self._block_tree_signal = False

    def _collect_selection(self) -> tuple[List[str], List[str]]:
        files: List[str] = []
        directories: List[str] = []
        root = self.file_tree.invisibleRootItem()
        for index in range(root.childCount()):
            self._collect_from_item(root.child(index), files, directories)
        return files, directories

    def _collect_from_item(self, item: QTreeWidgetItem, files: List[str], directories: List[str]) -> None:
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        node_type, path = data
        state = item.checkState(0)

        if node_type == "dir":
            if state == Qt.Checked:
                directories.append(path)
                return
        elif node_type == "file" and state == Qt.Checked:
            files.append(path)

        for index in range(item.childCount()):
            self._collect_from_item(item.child(index), files, directories)
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

    def _normalise_directory(self, path: str) -> str:
        normalised = self._normalise_text(path)
        return normalised.strip("/")
