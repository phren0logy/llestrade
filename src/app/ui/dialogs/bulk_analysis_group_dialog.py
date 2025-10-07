"""Dialog for creating bulk analysis groups."""

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
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QTreeWidget,
    QTreeWidgetItem,
    QLabel,
    QGroupBox,
    QCheckBox,
    QSpinBox,
)

from src.config.app_config import get_available_providers_and_models
from src.config.prompt_store import get_bundled_dir, get_custom_dir
from src.config.paths import app_resource_root
from src.app.core.bulk_paths import iter_map_outputs
from src.app.core.bulk_analysis_groups import BulkAnalysisGroup
from src.app.core.project_manager import ProjectMetadata
from src.app.core.prompt_preview import generate_prompt_preview, PromptPreviewError
from src.app.core.prompt_placeholders import placeholder_summary
from .prompt_preview_dialog import PromptPreviewDialog

DEFAULT_SYSTEM_PROMPT = "prompts/document_analysis_system_prompt.md"
DEFAULT_USER_PROMPT = "prompts/document_bulk_analysis_prompt.md"


class BulkAnalysisGroupDialog(QDialog):
    """Collect information needed to create a bulk analysis group."""

    def __init__(
        self,
        project_dir: Path,
        parent: Optional[QWidget] = None,
        *,
        metadata: Optional[ProjectMetadata] = None,
    ) -> None:
        super().__init__(parent)
        self._project_dir = project_dir
        self._metadata = metadata
        self._group: Optional[BulkAnalysisGroup] = None
        self.setWindowTitle("New Bulk Analysis")
        self.setModal(True)
        self._build_ui()
        self._populate_file_tree()
        self._populate_map_outputs_tree()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build_group(self) -> BulkAnalysisGroup:
        if not self._group:
            raise RuntimeError("Dialog was not accepted; no bulk analysis group available")
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

        # Operation selector
        self.operation_combo = QComboBox()
        self.operation_combo.addItem("Per-document", "per_document")
        self.operation_combo.addItem("Combined", "combined")
        self.operation_combo.currentIndexChanged.connect(self._on_operation_changed)
        form.addRow("Operation", self.operation_combo)

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setUniformRowHeights(True)
        self.file_tree.itemChanged.connect(self._on_tree_item_changed)
        self._block_tree_signal = False
        form.addRow("Documents", self.file_tree)

        # Map outputs tree group (visible for Combined)
        self.map_tree_group = QGroupBox("Per-document Outputs (optional)")
        map_layout = QVBoxLayout(self.map_tree_group)
        self.map_tree = QTreeWidget()
        self.map_tree.setHeaderHidden(True)
        self.map_tree.setUniformRowHeights(True)
        self.map_tree.itemChanged.connect(self._on_map_tree_item_changed)
        map_layout.addWidget(self.map_tree)
        form.addRow(self.map_tree_group)

        self.manual_files_label = QLabel("Extra Files")
        self.manual_files_edit = QPlainTextEdit()
        self.manual_files_edit.setPlaceholderText("Additional files (one per line, optional)")
        self.manual_files_edit.setMinimumHeight(60)
        form.addRow(self.manual_files_label, self.manual_files_edit)

        self.system_prompt_edit = QLineEdit()
        self.system_prompt_edit.setToolTip(
            placeholder_summary("document_analysis_system_prompt")
        )
        self.system_prompt_button = QPushButton("Browse…")
        self.system_prompt_button.clicked.connect(lambda: self._choose_prompt_file(self.system_prompt_edit))
        form.addRow("System Prompt", self._wrap_with_button(self.system_prompt_edit, self.system_prompt_button))
        self._initialise_prompt_path(
            self.system_prompt_edit,
            "document_analysis_system_prompt.md",
            DEFAULT_SYSTEM_PROMPT,
        )

        self.user_prompt_edit = QLineEdit()
        self.user_prompt_edit.setToolTip(
            placeholder_summary("document_bulk_analysis_prompt")
        )
        self.user_prompt_button = QPushButton("Browse…")
        self.user_prompt_button.clicked.connect(lambda: self._choose_prompt_file(self.user_prompt_edit))
        form.addRow("User Prompt", self._wrap_with_button(self.user_prompt_edit, self.user_prompt_button))
        self._initialise_prompt_path(
            self.user_prompt_edit,
            "document_bulk_analysis_prompt.md",
            DEFAULT_USER_PROMPT,
        )

        self.preview_prompt_button = QPushButton("Preview Prompt")
        self.preview_prompt_button.clicked.connect(self._preview_prompt)
        form.addRow("", self.preview_prompt_button)

        self.model_combo = self._build_model_combo()
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        form.addRow("Model", self.model_combo)

        self.custom_model_label = QLabel("Custom model")
        self.custom_model_edit = QLineEdit()
        self.custom_model_edit.setPlaceholderText("e.g., claude-sonnet-4-5-20250929")
        form.addRow(self.custom_model_label, self.custom_model_edit)

        self.custom_context_label = QLabel("Custom context window (tokens)")
        self.custom_context_spin = QSpinBox()
        self.custom_context_spin.setRange(10000, 4000000)
        self.custom_context_spin.setSingleStep(1000)
        self.custom_context_spin.setValue(200000)
        form.addRow(self.custom_context_label, self.custom_context_spin)

        # Combined options
        self.order_combo = QComboBox()
        self.order_combo.addItem("By path", "path")
        self.order_combo.addItem("By modified time", "mtime")
        form.addRow("Combined Order", self.order_combo)

        self.output_template_edit = QLineEdit()
        self.output_template_edit.setPlaceholderText("combined_{timestamp}.md")
        self.output_template_edit.setText("combined_{timestamp}.md")
        form.addRow("Output Template", self.output_template_edit)

        self.reasoning_checkbox = QCheckBox("Use reasoning (thinking models)")
        form.addRow("Reasoning", self.reasoning_checkbox)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Initial visibility
        self._on_operation_changed()
        self._on_model_changed()

    def _is_allowed_file(self, path: Path) -> bool:
        """Return True if the file should be selectable (only .md or .txt)."""
        try:
            return path.suffix.lower() in {".md", ".txt"}
        except Exception:
            return False

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
        # Limit to Anthropic with two supported models and a Custom option
        combo.addItem("Custom…", ("custom", ""))
        combo.addItem(
            "Anthropic Claude (claude-sonnet-4-5-20250929)",
            ("anthropic", "claude-sonnet-4-5-20250929"),
        )
        combo.addItem(
            "Anthropic Claude (claude-opus-4-1-20250805)",
            ("anthropic", "claude-opus-4-1-20250805"),
        )
        return combo

    def _on_model_changed(self) -> None:
        data = self.model_combo.currentData()
        is_custom = bool(data) and data[0] == "custom"
        self.custom_model_label.setVisible(is_custom)
        self.custom_model_edit.setVisible(is_custom)
        self.custom_context_label.setVisible(is_custom)
        self.custom_context_spin.setVisible(is_custom)

    def _choose_prompt_file(self, line_edit: QLineEdit) -> None:
        # Default browse folder to user prompt store (custom), with safe fallbacks
        try:
            initial_dir = get_custom_dir()
        except Exception:
            initial_dir = self._project_dir if self._project_dir else Path.cwd()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Prompt File",
            str(initial_dir),
            "Prompt Files (*.txt *.md *.prompt);;All Files (*)",
        )
        if file_path:
            line_edit.setText(self._normalise_path(Path(file_path)))

    def _initialise_prompt_path(self, line_edit: QLineEdit, filename: str, fallback: str) -> None:
        path: Optional[Path] = None
        try:
            candidate = get_bundled_dir() / filename
            if candidate.exists():
                path = candidate
        except Exception:
            path = None

        if path is None:
            resource_root = app_resource_root()
            resource_fallback = resource_root / fallback
            if resource_fallback.exists():
                path = resource_fallback
            else:
                path = resource_fallback

        line_edit.setText(self._normalise_path(path))

    def _on_operation_changed(self) -> None:
        combined = self.operation_combo.currentData() == "combined"
        self.map_tree_group.setVisible(combined)
        # Combined options are still useful to adjust ahead of time
        self.order_combo.setEnabled(combined)
        self.output_template_edit.setEnabled(combined)
        self.reasoning_checkbox.setEnabled(True)
        # Show Extra Files only for Combined
        self.manual_files_label.setVisible(combined)
        self.manual_files_edit.setVisible(combined)

    def _on_map_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        # Mirror tri-state behavior used in the converted-docs tree
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        node_type, _ = data
        state = item.checkState(0)
        # Propagate to children when a directory/group toggles
        if node_type in ("map-dir", "map-group") and state in (Qt.Checked, Qt.Unchecked):
            for index in range(item.childCount()):
                child = item.child(index)
                child.setCheckState(0, state)
        # Update ancestors' partial/checked state
        self._sync_parent_state(item.parent())
        return

    # ------------------------------------------------------------------
    # Acceptance
    # ------------------------------------------------------------------
    def _handle_accept(self) -> None:
        group = self._build_group_instance()
        if group is None:
            return
        self._group = group
        self.accept()

    def _build_group_instance(self) -> Optional[BulkAnalysisGroup]:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please provide a name for the bulk analysis group.")
            return None

        tree_files, directories = self._collect_selection()
        manual_files_all = [
            self._normalise_text(line.strip())
            for line in self.manual_files_edit.toPlainText().splitlines()
            if line.strip()
        ]
        files_set = set()
        for path in tree_files:
            if not path:
                continue
            if Path(path).suffix.lower() in {".md", ".txt"}:
                files_set.add(self._normalise_text(path))
        for path in manual_files_all:
            if not path:
                continue
            if Path(path).suffix.lower() in {".md", ".txt"}:
                files_set.add(self._normalise_text(path))
        files = sorted(files_set)

        directories = sorted({self._normalise_directory(path) for path in directories if path})

        provider_id, model = self.model_combo.currentData()
        if provider_id == "custom":
            provider_id = "anthropic"
            model = self.custom_model_edit.text().strip()
            if not model:
                QMessageBox.warning(self, "Missing Model", "Please enter a model id for the custom option.")
                return None
            custom_window = int(self.custom_context_spin.value())
        else:
            custom_window = None

        description = self.description_edit.toPlainText().strip()
        system_prompt = self._normalise_text(self.system_prompt_edit.text().strip())
        user_prompt = self._normalise_text(self.user_prompt_edit.text().strip())

        op = self.operation_combo.currentData()
        if op == "combined":
            map_groups: list[str] = []
            map_dirs: list[str] = []
            map_files: list[str] = []
            root = self.map_tree.invisibleRootItem()
            nodes = [root]
            while nodes:
                node = nodes.pop()
                for i in range(node.childCount()):
                    child = node.child(i)
                    nodes.append(child)
                    data = child.data(0, Qt.UserRole)
                    if not data:
                        continue
                    kind, value = data
                    if child.checkState(0) != Qt.Checked:
                        continue
                    if kind == "map-group":
                        map_groups.append(str(value))
                    elif kind == "map-dir":
                        map_dirs.append(str(value))
                    elif kind == "map-file":
                        map_files.append(str(value))

            group = BulkAnalysisGroup.create(
                name=name,
                description=description,
                files=[],
                directories=[],
                provider_id=provider_id,
                model=model,
                system_prompt_path=system_prompt,
                user_prompt_path=user_prompt,
            )
            group.operation = "combined"
            group.combine_converted_files = files
            group.combine_converted_directories = directories
            group.combine_map_files = sorted(set(map_files))
            group.combine_map_groups = sorted(set(map_groups))
            group.combine_map_directories = sorted(set(map_dirs))
            group.combine_order = self.order_combo.currentData() or "path"
            templ = self.output_template_edit.text().strip() or "combined_{timestamp}.md"
            group.combine_output_template = templ
            group.use_reasoning = self.reasoning_checkbox.isChecked()
            group.model_context_window = custom_window
            return group

        group = BulkAnalysisGroup.create(
            name=name,
            description=description,
            files=files,
            directories=directories,
            provider_id=provider_id,
            model=model,
            system_prompt_path=system_prompt,
            user_prompt_path=user_prompt,
        )
        group.model_context_window = custom_window
        return group

    def _preview_prompt(self) -> None:
        group = self._build_group_instance()
        if group is None:
            return
        try:
            preview = generate_prompt_preview(self._project_dir, group, metadata=self._metadata)
        except PromptPreviewError as exc:
            QMessageBox.warning(self, "Prompt Preview", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            QMessageBox.warning(self, "Prompt Preview", "Failed to generate prompt preview.")
            return

        dialog = PromptPreviewDialog(self)
        dialog.set_prompts(preview.system_prompt, preview.user_prompt)
        dialog.exec()

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

        converted_files = []
        for path in converted_root.rglob("*"):
            if not path.is_file():
                continue
            # Hide Azure DI artefacts from the picker to avoid confusing users.
            if any(
                part in {".azure-di", ".azure_di"} or part.startswith(".azure-di") or part.startswith(".azure_di")
                for part in path.parts
            ):
                continue
            # Only allow markdown or text files
            if not self._is_allowed_file(path):
                continue
            converted_files.append(path.relative_to(converted_root).as_posix())

        converted_files.sort()

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

    def _populate_map_outputs_tree(self) -> None:
        self.map_tree.clear()
        if not self._project_dir:
            info = QTreeWidgetItem(["No project directory available."])
            info.setFlags(Qt.NoItemFlags)
            self.map_tree.addTopLevelItem(info)
            return
        ba_root = self._project_dir / "bulk_analysis"
        if not ba_root.exists():
            info = QTreeWidgetItem(["No per-document outputs found."])
            info.setFlags(Qt.NoItemFlags)
            self.map_tree.addTopLevelItem(info)
            return

        added = False
        for slug_dir in sorted(ba_root.iterdir()):
            if not slug_dir.is_dir():
                continue
            slug = slug_dir.name
            outputs = list(iter_map_outputs(self._project_dir, slug))
            if not outputs:
                continue

            added = True
            group_item = QTreeWidgetItem([slug])
            group_item.setData(0, Qt.UserRole, ("map-group", slug))
            flags = group_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate
            group_item.setFlags(flags)
            group_item.setCheckState(0, Qt.Unchecked)
            self.map_tree.addTopLevelItem(group_item)

            tree_nodes: dict[tuple[str, bool], QTreeWidgetItem] = {}
            for _, rel in sorted(outputs, key=lambda item: item[1]):
                self._add_map_path_to_tree(group_item, slug, rel, tree_nodes)

        if not added:
            info = QTreeWidgetItem(["No per-document outputs found."])
            info.setFlags(Qt.NoItemFlags)
            self.map_tree.addTopLevelItem(info)

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

    def _add_map_path_to_tree(self, group_item: QTreeWidgetItem, slug: str, relative_path: str, cache: dict) -> None:
        parts = relative_path.split("/")
        current_path = ""
        parent_item = group_item
        for index, part in enumerate(parts):
            current_path = f"{current_path}/{part}" if current_path else part
            is_file = index == len(parts) - 1
            key = (f"{slug}/{current_path}", is_file)
            existing = cache.get(key)
            if existing:
                parent_item = existing
                continue
            item = QTreeWidgetItem(parent_item, [part])
            if is_file:
                item.setData(0, Qt.UserRole, ("map-file", f"{slug}/{current_path}"))
            else:
                item.setData(0, Qt.UserRole, ("map-dir", f"{slug}/{current_path}"))
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if not is_file:
                flags |= Qt.ItemFlag.ItemIsAutoTristate
            item.setFlags(flags)
            item.setCheckState(0, Qt.Unchecked)
            cache[key] = item
            parent_item = item

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._block_tree_signal:
            return
        node_type, _ = item.data(0, Qt.UserRole) or (None, None)
        state = item.checkState(0)

        self._block_tree_signal = True
        if node_type == "dir" and state in (Qt.Checked, Qt.Unchecked):
            for index in range(item.childCount()):
                child = item.child(index)
                child.setCheckState(0, state)

        self._sync_parent_state(item.parent())
        self._block_tree_signal = False

    def _sync_parent_state(self, parent: Optional[QTreeWidgetItem]) -> None:
        while parent is not None:
            checked = unchecked = 0
            for index in range(parent.childCount()):
                state = parent.child(index).checkState(0)
                if state == Qt.Checked:
                    checked += 1
                elif state == Qt.Unchecked:
                    unchecked += 1
                else:
                    checked += 1
                    unchecked += 1
            if checked and not unchecked:
                parent.setCheckState(0, Qt.Checked)
            elif unchecked and not checked:
                parent.setCheckState(0, Qt.Unchecked)
            else:
                parent.setCheckState(0, Qt.PartiallyChecked)
            parent = parent.parent()

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
