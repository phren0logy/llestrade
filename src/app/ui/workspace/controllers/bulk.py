"""Business-logic controller for the bulk analysis tab."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
    QTableWidgetItem,
)

from src.app.core.bulk_analysis_groups import BulkAnalysisGroup
from src.app.core.file_tracker import WorkspaceGroupMetrics, WorkspaceMetrics
from src.app.ui.workspace.bulk_tab import BulkAnalysisTab

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.app.core.project_manager import ProjectManager


class BulkAnalysisController:
    """Render and co-ordinate bulk analysis group state."""

    def __init__(
        self,
        tab: BulkAnalysisTab,
        *,
        on_create_group: Callable[[], None],
        on_refresh_requested: Callable[[], None],
        on_start_group_run: Callable[[BulkAnalysisGroup, bool], None],
        on_start_combined_run: Callable[[BulkAnalysisGroup, bool], None],
        on_cancel_group_run: Callable[[BulkAnalysisGroup], None],
        on_open_group_folder: Callable[[BulkAnalysisGroup], None],
        on_show_prompt_preview: Callable[[BulkAnalysisGroup], None],
        on_open_latest_combined: Callable[[BulkAnalysisGroup], None],
        on_delete_group: Callable[[BulkAnalysisGroup], None],
    ) -> None:
        self._tab = tab
        self._project_manager: Optional["ProjectManager"] = None
        self._feature_enabled = True

        self._on_create_group = on_create_group
        self._on_refresh_requested = on_refresh_requested
        self._on_start_group_run = on_start_group_run
        self._on_start_combined_run = on_start_combined_run
        self._on_cancel_group_run = on_cancel_group_run
        self._on_open_group_folder = on_open_group_folder
        self._on_show_prompt_preview = on_show_prompt_preview
        self._on_open_latest_combined = on_open_latest_combined
        self._on_delete_group = on_delete_group

        self._info_message: str = "No bulk analysis groups yet."

        self._tab.create_button.clicked.connect(self._on_create_group)
        self._tab.refresh_button.clicked.connect(self._on_refresh_requested)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def set_feature_enabled(self, enabled: bool) -> None:
        self._feature_enabled = enabled
        self._tab.setEnabled(enabled)

    def set_project(self, project_manager: Optional["ProjectManager"]) -> None:
        self._project_manager = project_manager
        self._tab.table.setRowCount(0)
        self._tab.empty_label.show()
        self._tab.log_text.clear()
        self._info_message = "No bulk analysis groups yet."
        self._tab.info_label.setText(self._info_message)
        self._tab.group_tree.clear()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def refresh(
        self,
        *,
        groups: Sequence[BulkAnalysisGroup],
        workspace_metrics: WorkspaceMetrics | None,
        running_groups: Set[str],
        progress_map: Dict[str, tuple[int, int]],
        cancelling_groups: Set[str],
    ) -> None:
        if not self._feature_enabled:
            return

        tab = self._tab

        if not groups:
            tab.table.setRowCount(0)
            tab.empty_label.show()
        else:
            tab.empty_label.hide()
            tab.table.setRowCount(len(groups))

        total_docs = 0
        group_metrics: Dict[str, WorkspaceGroupMetrics] = {}
        if workspace_metrics:
            total_docs = workspace_metrics.dashboard.imported_total
            group_metrics = workspace_metrics.groups

        for row, group in enumerate(groups):
            metrics = group_metrics.get(group.group_id)
            self._populate_row(
                row=row,
                group=group,
                total_docs=total_docs,
                metrics=metrics,
                running_groups=running_groups,
                progress_map=progress_map,
                cancelling_groups=cancelling_groups,
            )

        if not groups:
            self._info_message = "No bulk analysis groups yet."
            tab.info_label.setText(self._info_message)
        elif running_groups or cancelling_groups:
            tab.info_label.setText(self._info_message)
        else:
            message = f"{len(groups)} bulk analysis group(s)"
            self._info_message = message
            tab.info_label.setText(message)

        self._refresh_group_tree()

    def _populate_row(
        self,
        *,
        row: int,
        group: BulkAnalysisGroup,
        total_docs: int,
        metrics: WorkspaceGroupMetrics | None,
        running_groups: Set[str],
        progress_map: Dict[str, tuple[int, int]],
        cancelling_groups: Set[str],
    ) -> None:
        table = self._tab.table
        description = group.description or ""

        name_item = QTableWidgetItem(group.name)
        name_item.setData(Qt.UserRole, group.group_id)
        table.setItem(row, 0, name_item)

        op_type = getattr(metrics, "operation", "per_document") if metrics else group.operation or "per_document"
        converted_count = metrics.converted_count if metrics else 0
        if op_type == "combined":
            input_count = getattr(metrics, "combined_input_count", 0) if metrics else 0
            coverage_text = f"Combined — Inputs: {input_count}"
        else:
            coverage_text = f"{converted_count} of {total_docs}" if total_docs else str(converted_count)
        coverage_item = QTableWidgetItem(coverage_text)
        coverage_item.setTextAlignment(Qt.AlignCenter)
        table.setItem(row, 1, coverage_item)

        updated_text = group.updated_at.strftime("%Y-%m-%d %H:%M")
        updated_item = QTableWidgetItem(updated_text)
        updated_item.setTextAlignment(Qt.AlignCenter)
        table.setItem(row, 2, updated_item)

        status_item = QTableWidgetItem(
            self._status_text(group, metrics, running_groups, progress_map, cancelling_groups)
        )
        status_item.setTextAlignment(Qt.AlignCenter)
        table.setItem(row, 3, status_item)

        action_widget = self._build_action_widget(group, metrics, running_groups)
        table.setCellWidget(row, 4, action_widget)

        tooltip_lines: List[str] = []
        if description:
            tooltip_lines.append(description)
        if group.directories:
            tooltip_lines.append("Directories: " + ", ".join(group.directories))
        extra_files = sorted(set(group.files))
        if extra_files:
            tooltip_lines.append("Files: " + ", ".join(extra_files))
        if metrics and metrics.converted_files:
            tooltip_lines.append(
                "Converted files (" + str(metrics.converted_count) + "): " + ", ".join(metrics.converted_files)
            )
        if tooltip_lines:
            name_item.setToolTip("\n".join(tooltip_lines))

    def _status_text(
        self,
        group: BulkAnalysisGroup,
        metrics: WorkspaceGroupMetrics | None,
        running_groups: Set[str],
        progress_map: Dict[str, tuple[int, int]],
        cancelling_groups: Set[str],
    ) -> str:
        gid = group.group_id
        op_type = getattr(metrics, "operation", "per_document") if metrics else group.operation or "per_document"

        if gid in cancelling_groups:
            return "Cancelling…"
        if gid in running_groups:
            completed, total = progress_map.get(gid, (0, 0))
            if total:
                return f"Running ({completed}/{total})"
            return "Running…"

        if op_type == "combined":
            input_count = getattr(metrics, "combined_input_count", 0) if metrics else 0
            if input_count == 0:
                return "No inputs"
            if metrics and getattr(metrics, "combined_is_stale", False):
                return "Stale"
            return "Ready"

        converted_count = metrics.converted_count if metrics else 0
        if not converted_count:
            return "No converted files"
        if metrics and metrics.pending_bulk_analysis:
            return f"Pending bulk ({metrics.pending_bulk_analysis})"
        return "Ready"

    def _build_action_widget(
        self,
        group: BulkAnalysisGroup,
        metrics: WorkspaceGroupMetrics | None,
        running_groups: Set[str],
    ) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        is_running = group.group_id in running_groups
        op_type = getattr(metrics, "operation", "per_document") if metrics else group.operation or "per_document"

        if op_type == "combined":
            input_count = getattr(metrics, "combined_input_count", 0) if metrics else 0

            run_combined = QPushButton("Run Combined")
            run_combined.setEnabled(input_count > 0 and not is_running)
            run_combined.clicked.connect(lambda _, g=group: self._on_start_combined_run(g, False))
            layout.addWidget(run_combined)

            run_combined_all = QPushButton("Run Combined All")
            run_combined_all.setEnabled(input_count > 0 and not is_running)
            run_combined_all.clicked.connect(lambda _, g=group: self._on_start_combined_run(g, True))
            layout.addWidget(run_combined_all)
        else:
            pending_count = metrics.pending_bulk_analysis if metrics else None
            converted_count = metrics.converted_count if metrics else 0

            run_pending = QPushButton("Run Pending")
            run_pending.setEnabled((pending_count is None or pending_count > 0) and not is_running)
            run_pending.clicked.connect(lambda _, g=group: self._on_start_group_run(g, False))
            layout.addWidget(run_pending)

            run_all = QPushButton("Run All")
            run_all.setEnabled((converted_count > 0 or pending_count is None) and not is_running)
            run_all.clicked.connect(lambda _, g=group: self._on_start_group_run(g, True))
            layout.addWidget(run_all)

        cancel_button = QPushButton("Cancel")
        cancel_button.setEnabled(is_running)
        cancel_button.clicked.connect(lambda _, g=group: self._on_cancel_group_run(g))
        layout.addWidget(cancel_button)

        if op_type == "combined":
            open_latest = QPushButton("Open Latest")
            open_latest.clicked.connect(lambda _, g=group: self._on_open_latest_combined(g))
            layout.addWidget(open_latest)

        open_folder = QPushButton("Open Folder")
        open_folder.clicked.connect(lambda _, g=group: self._on_open_group_folder(g))
        layout.addWidget(open_folder)

        prompt_preview = QPushButton("Prompt Preview")
        prompt_preview.clicked.connect(lambda _, g=group: self._on_show_prompt_preview(g))
        layout.addWidget(prompt_preview)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(lambda _, g=group: self._on_delete_group(g))
        layout.addWidget(delete_button)

        return widget

    def _refresh_group_tree(self) -> None:
        tree = self._tab.group_tree
        tree.clear()

        project_manager = self._project_manager
        if not project_manager:
            self._add_placeholder_item(tree, "Open a project to view folders.")
            return

        root_path = self._resolve_source_root()
        if not root_path or not root_path.exists():
            self._add_placeholder_item(tree, "Source folder not set.")
            return

        directories = sorted(self._iter_directories(root_path))
        if not directories:
            self._add_placeholder_item(tree, "No subfolders available.")
            return

        tree.setUpdatesEnabled(False)
        root_item = tree.invisibleRootItem()
        for relative_path in directories:
            parts = relative_path.split("/")
            parent = root_item
            for part in parts:
                child = self._find_child(parent, part)
                if child is None:
                    child = QTreeWidgetItem([part])
                    parent.addChild(child)
                parent = child
        tree.expandAll()
        tree.setUpdatesEnabled(True)

    def _add_placeholder_item(self, tree: QWidget, text: str) -> None:
        placeholder = QTreeWidgetItem([text])
        placeholder.setFlags(Qt.NoItemFlags)
        tree.addTopLevelItem(placeholder)

    def _find_child(self, parent: QTreeWidgetItem, name: str) -> Optional[QTreeWidgetItem]:
        for index in range(parent.childCount()):
            child = parent.child(index)
            if child.text(0) == name:
                return child
        return None

    def _resolve_source_root(self) -> Optional[Path]:
        pm = self._project_manager
        if not pm or not pm.project_dir:
            return None
        root_spec = (pm.source_state.root or "").strip()
        if not root_spec:
            return None
        root_path = Path(root_spec)
        if not root_path.is_absolute():
            root_path = (pm.project_dir / root_path).resolve()
        return root_path

    def _iter_directories(self, root_path: Path) -> Iterable[str]:
        for path in root_path.rglob("*"):
            if path.is_dir():
                try:
                    yield path.relative_to(root_path).as_posix()
                except ValueError:
                    continue

    # ------------------------------------------------------------------
    # Messaging helpers
    # ------------------------------------------------------------------
    def clear_log(self) -> None:
        self._tab.log_text.clear()

    def append_log_message(self, message: str) -> None:
        self._tab.log_text.append(message)
        self._tab.log_text.moveCursor(QTextCursor.End)

    def set_info_message(self, message: str) -> None:
        self._info_message = message
        self._tab.info_label.setText(message)

    def set_progress_message(self, completed: int, total: int, relative_path: str) -> None:
        message = f"Running bulk analysis ({completed}/{total})… {relative_path}"
        self.set_info_message(message)
