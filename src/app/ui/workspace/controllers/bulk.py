"""Business-logic controller for the bulk analysis tab."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTreeWidgetItem,
    QWidget,
    QTableWidgetItem,
)

from src.app.core.bulk_analysis_groups import BulkAnalysisGroup
from src.app.core.file_tracker import WorkspaceGroupMetrics, WorkspaceMetrics
from src.app.ui.workspace.bulk_tab import BulkAnalysisTab
from src.app.ui.workspace.services import BulkAnalysisService

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.app.core.project_manager import ProjectManager

LOGGER = logging.getLogger(__name__)


class BulkAnalysisController:
    """Render and co-ordinate bulk analysis group state."""

    def __init__(
        self,
        tab: BulkAnalysisTab,
        *,
        workspace: QWidget,
        service: BulkAnalysisService,
        on_create_group: Callable[[], None],
        on_refresh_requested: Callable[[], None],
        on_refresh_groups: Callable[[], None],
        on_refresh_metrics: Callable[[], None],
        on_open_group_folder: Callable[[BulkAnalysisGroup], None],
        on_show_prompt_preview: Callable[[BulkAnalysisGroup], None],
        on_open_latest_combined: Callable[[BulkAnalysisGroup], None],
        on_delete_group: Callable[[BulkAnalysisGroup], None],
    ) -> None:
        self._tab = tab
        self._workspace = workspace
        self._service = service

        self._project_manager: Optional["ProjectManager"] = None
        self._latest_metrics: WorkspaceMetrics | None = None
        self._feature_enabled = True

        self._on_create_group = on_create_group
        self._on_refresh_requested = on_refresh_requested
        self._on_refresh_groups = on_refresh_groups
        self._on_refresh_metrics = on_refresh_metrics
        self._on_open_group_folder = on_open_group_folder
        self._on_show_prompt_preview = on_show_prompt_preview
        self._on_open_latest_combined = on_open_latest_combined
        self._on_delete_group = on_delete_group

        self._info_message: str = "No bulk analysis groups yet."
        self._running_groups: Set[str] = set()
        self._cancelling_groups: Set[str] = set()
        self._progress_map: Dict[str, tuple[int, int]] = {}
        self._failures: Dict[str, List[str]] = {}

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
        self._running_groups.clear()
        self._cancelling_groups.clear()
        self._progress_map.clear()
        self._failures.clear()
        self._latest_metrics = None
        self._tab.table.setRowCount(0)
        self._tab.empty_label.show()
        self._tab.log_text.clear()
        self._info_message = "No bulk analysis groups yet."
        self._tab.info_label.setText(self._info_message)
        self._tab.group_tree.clear()

    @property
    def tab(self) -> BulkAnalysisTab:
        """Expose the underlying tab widget for testing or orchestration."""
        return self._tab

    @property
    def running_groups(self) -> Set[str]:
        return set(self._running_groups)

    def is_running(self, group_id: str) -> bool:
        return group_id in self._running_groups

    def progress_for(self, group_id: str) -> Optional[tuple[int, int]]:
        return self._progress_map.get(group_id)

    def is_cancelling(self, group_id: str) -> bool:
        return group_id in self._cancelling_groups

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def refresh(
        self,
        *,
        groups: Sequence[BulkAnalysisGroup],
        workspace_metrics: WorkspaceMetrics | None,
    ) -> None:
        if not self._feature_enabled:
            return

        self._latest_metrics = workspace_metrics

        if not groups:
            self._tab.table.setRowCount(0)
            self._tab.empty_label.show()
        else:
            self._tab.empty_label.hide()
            self._tab.table.setRowCount(len(groups))

        total_docs = 0
        group_metrics: Dict[str, WorkspaceGroupMetrics] = {}
        if workspace_metrics:
            total_docs = workspace_metrics.dashboard.imported_total
            group_metrics = workspace_metrics.groups

        known_ids = {group.group_id for group in groups}
        self._prune_stale_states(known_ids)

        for row, group in enumerate(groups):
            metrics = group_metrics.get(group.group_id)
            self._populate_row(
                row=row,
                group=group,
                total_docs=total_docs,
                metrics=metrics,
            )

        if not groups:
            self._info_message = "No bulk analysis groups yet."
            self._tab.info_label.setText(self._info_message)
        elif self._running_groups or self._cancelling_groups:
            self._tab.info_label.setText(self._info_message)
        else:
            self._info_message = f"{len(groups)} bulk analysis group(s)"
            self._tab.info_label.setText(self._info_message)

        self._refresh_group_tree(groups)

    def _populate_row(
        self,
        *,
        row: int,
        group: BulkAnalysisGroup,
        total_docs: int,
        metrics: WorkspaceGroupMetrics | None,
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

        status_item = QTableWidgetItem(self._status_text(group, metrics))
        status_item.setTextAlignment(Qt.AlignCenter)
        table.setItem(row, 3, status_item)

        action_widget = self._build_action_widget(group, metrics)
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
    ) -> str:
        gid = group.group_id
        op_type = getattr(metrics, "operation", "per_document") if metrics else group.operation or "per_document"

        if gid in self._cancelling_groups:
            return "Cancelling…"
        if gid in self._running_groups:
            completed, total = self._progress_map.get(gid, (0, 0))
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
    ) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        is_running = group.group_id in self._running_groups
        op_type = getattr(metrics, "operation", "per_document") if metrics else group.operation or "per_document"

        if op_type == "combined":
            input_count = getattr(metrics, "combined_input_count", 0) if metrics else 0

            run_combined = QPushButton("Run Combined")
            run_combined.setEnabled(input_count > 0 and not is_running)
            run_combined.clicked.connect(lambda _, g=group: self.start_combined_run(g, False))
            layout.addWidget(run_combined)

            run_combined_all = QPushButton("Run Combined All")
            run_combined_all.setEnabled(input_count > 0 and not is_running)
            run_combined_all.clicked.connect(lambda _, g=group: self.start_combined_run(g, True))
            layout.addWidget(run_combined_all)
        else:
            pending_count = metrics.pending_bulk_analysis if metrics else None
            converted_count = metrics.converted_count if metrics else 0

            run_pending = QPushButton("Run Pending")
            run_pending.setEnabled((pending_count or 0) > 0 and not is_running)
            run_pending.clicked.connect(lambda _, g=group: self.start_map_run(g, False))
            layout.addWidget(run_pending)

            run_all = QPushButton("Run All")
            run_all.setEnabled(converted_count > 0 and not is_running)
            run_all.clicked.connect(lambda _, g=group: self.start_map_run(g, True))
            layout.addWidget(run_all)

        cancel_button = QPushButton("Cancel")
        cancel_button.setEnabled(is_running)
        cancel_button.clicked.connect(lambda _, g=group: self.cancel_run(g))
        layout.addWidget(cancel_button)

        open_button = QPushButton("Open Folder")
        open_button.clicked.connect(lambda _, g=group: self._on_open_group_folder(g))
        layout.addWidget(open_button)

        prompt_button = QPushButton("Preview Prompt")
        prompt_button.clicked.connect(lambda _, g=group: self._on_show_prompt_preview(g))
        layout.addWidget(prompt_button)

        combined_button = QPushButton("Open Combined Output")
        combined_button.clicked.connect(lambda _, g=group: self._on_open_latest_combined(g))
        layout.addWidget(combined_button)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(lambda _, g=group: self._on_delete_group(g))
        layout.addWidget(delete_button)

        layout.addStretch()
        return widget

    def _refresh_group_tree(self, groups: Sequence[BulkAnalysisGroup]) -> None:
        tree = self._tab.group_tree
        tree.clear()
        for group in groups:
            parent = QTreeWidgetItem([group.name])
            for directory in sorted(group.directories):
                parent.addChild(QTreeWidgetItem(["Directory", directory]))
            for file_path in sorted(set(group.files)):
                parent.addChild(QTreeWidgetItem(["File", file_path]))
            tree.addTopLevelItem(parent)
        tree.expandAll()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def start_map_run(self, group: BulkAnalysisGroup, force_rerun: bool) -> None:
        if not self._feature_enabled:
            return
        manager = self._project_manager
        if not manager or not manager.project_dir:
            QMessageBox.warning(self._workspace, "Bulk Analysis", "The project directory is not available.")
            return

        gid = group.group_id
        if gid in self._running_groups:
            QMessageBox.information(
                self._workspace,
                "Already Running",
                f"Bulk analysis for '{group.name}' is already in progress.",
            )
            return

        metrics = self._resolve_group_metrics(gid)
        if not metrics:
            QMessageBox.warning(
                self._workspace,
                "Bulk Analysis",
                "Project metrics are unavailable. Re-scan sources before running bulk analysis.",
            )
            self._on_refresh_groups()
            return

        if force_rerun:
            files = list(metrics.converted_files)
            if not files:
                QMessageBox.warning(
                    self._workspace,
                    "No Converted Documents",
                    "This group does not have any converted documents yet. Run conversion first.",
                )
                return
        else:
            pending = list(metrics.pending_files)
            if pending:
                files = pending
            else:
                QMessageBox.information(
                    self._workspace,
                    "Up to Date",
                    "All documents already have bulk analysis results. Use 'Run All' to re-process everything.",
                )
                return

        provider_default = (
            (manager.settings or {}).get("llm_provider", ""),
            (manager.settings or {}).get("llm_model", ""),
        )

        self._running_groups.add(gid)
        self._progress_map[gid] = (0, len(files))
        self._failures[gid] = []
        self._cancelling_groups.discard(gid)

        started = self._service.run_map(
            project_dir=manager.project_dir,
            group=group,
            files=files,
            metadata=manager.metadata,
            default_provider=provider_default,
            force_rerun=force_rerun,
            on_progress=self._handle_progress,
            on_failed=self._handle_failed,
            on_log=self._handle_log,
            on_finished=lambda group_id, successes, failures: self._handle_finished(
                group_id,
                successes,
                failures,
                operation="map",
            ),
        )
        if not started:
            self._running_groups.discard(gid)
            self._progress_map.pop(gid, None)
            self._failures.pop(gid, None)
            QMessageBox.information(
                self._workspace,
                "Already Running",
                f"Bulk analysis for '{group.name}' is already in progress.",
            )
            return

        mode_label = "all documents" if force_rerun else "pending documents"
        self._handle_log(gid, f"Starting bulk analysis for '{group.name}' ({len(files)} {mode_label}).")
        self._on_refresh_groups()

    def start_combined_run(self, group: BulkAnalysisGroup, force_rerun: bool) -> None:
        if not self._feature_enabled:
            return
        manager = self._project_manager
        if not manager or not manager.project_dir:
            QMessageBox.warning(self._workspace, "Bulk Analysis", "The project directory is not available.")
            return

        gid = group.group_id
        if gid in self._running_groups:
            QMessageBox.information(
                self._workspace,
                "Already Running",
                f"Combined operation for '{group.name}' is already in progress.",
            )
            return

        if force_rerun:
            confirm = QMessageBox.question(
                self._workspace,
                "Force Combined Re-run",
                (
                    "This will recompute the combined analysis and overwrite the latest output.\n\n"
                    "Do you want to proceed?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return

        self._running_groups.add(gid)
        self._progress_map[gid] = (0, 1)
        self._failures[gid] = []
        self._cancelling_groups.discard(gid)

        started = self._service.run_combined(
            project_dir=manager.project_dir,
            group=group,
            metadata=manager.metadata,
            force_rerun=force_rerun,
            on_progress=self._handle_progress,
            on_failed=self._handle_failed,
            on_log=self._handle_log,
            on_finished=lambda group_id, successes, failures: self._handle_finished(
                group_id,
                successes,
                failures,
                operation="combined",
            ),
        )
        if not started:
            self._running_groups.discard(gid)
            self._progress_map.pop(gid, None)
            self._failures.pop(gid, None)
            QMessageBox.information(
                self._workspace,
                "Already Running",
                f"Combined operation for '{group.name}' is already in progress.",
            )
            return

        mode_label = "force" if force_rerun else "standard"
        self._handle_log(gid, f"Starting combined operation for '{group.name}' ({mode_label}).")
        self._on_refresh_groups()

    def cancel_run(self, group: BulkAnalysisGroup) -> None:
        if not self._feature_enabled:
            return
        gid = group.group_id
        if self._service.cancel(gid):
            self._cancelling_groups.add(gid)
            self.set_info_message("Cancelling bulk analysis…")
        else:
            self._progress_map.pop(gid, None)
            self._failures.pop(gid, None)
            self._cancelling_groups.discard(gid)
            self.set_info_message("Bulk analysis cancelled.")
        self._on_refresh_groups()

    # ------------------------------------------------------------------
    # Worker callbacks
    # ------------------------------------------------------------------
    def _handle_progress(self, group_id: str, completed: int, total: int, relative_path: str) -> None:
        if group_id in self._cancelling_groups:
            return
        self._progress_map[group_id] = (completed, total)
        self._refresh_groups_safely(relative_path)

    def _handle_failed(self, group_id: str, relative_path: str, error: str) -> None:
        LOGGER.error("Bulk analysis failed for %s: %s", relative_path, error)
        self._failures.setdefault(group_id, []).append(f"{relative_path}: {error}")

    def _handle_log(self, group_id: str, message: str) -> None:
        LOGGER.info("[BulkAnalysis][%s] %s", group_id, message)
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        cursor = self._tab.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(formatted + "\n")
        self._tab.log_text.setTextCursor(cursor)
        self.set_info_message(message)

    def _handle_finished(self, group_id: str, successes: int, failures: int, *, operation: str) -> None:
        self._running_groups.discard(group_id)
        self._progress_map.pop(group_id, None)
        errors = self._failures.pop(group_id, [])

        was_cancelled = group_id in self._cancelling_groups
        if was_cancelled:
            self._cancelling_groups.discard(group_id)
            completion_message = "Bulk analysis cancelled."
        elif failures:
            completion_message = f"Bulk analysis completed with {failures} error(s)."
        else:
            completion_message = "Bulk analysis completed."

        self._handle_log(group_id, completion_message)

        if errors and not was_cancelled:
            QMessageBox.warning(
                self._workspace,
                "Bulk Analysis Issues",
                "Some documents failed during bulk analysis:\n" + "\n".join(errors),
            )

        if self._on_refresh_metrics:
            self._on_refresh_metrics()
        self._on_refresh_groups()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def set_info_message(self, message: str) -> None:
        self._info_message = message
        self._tab.info_label.setText(message)

    def append_log_message(self, message: str) -> None:
        cursor = self._tab.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(message + "\n")
        self._tab.log_text.setTextCursor(cursor)

    def _refresh_groups_safely(self, relative_path: str) -> None:
        self._tab.info_label.setText(f"Processing… {relative_path}")
        self._on_refresh_groups()

    def _resolve_group_metrics(self, group_id: str) -> Optional[WorkspaceGroupMetrics]:
        if self._latest_metrics and group_id in self._latest_metrics.groups:
            return self._latest_metrics.groups[group_id]

        manager = self._project_manager
        if not manager:
            return None
        try:
            metrics = manager.get_workspace_metrics()
        except Exception:
            LOGGER.exception("Failed to refresh workspace metrics for bulk analysis")
            return None
        self._latest_metrics = metrics
        return metrics.groups.get(group_id)

    def _prune_stale_states(self, valid_ids: Set[str]) -> None:
        for state_map in (self._progress_map, self._failures):
            for gid in list(state_map.keys()):
                if gid not in valid_ids:
                    state_map.pop(gid, None)
        self._running_groups.intersection_update(valid_ids)
        self._cancelling_groups.intersection_update(valid_ids)


__all__ = ["BulkAnalysisController"]
