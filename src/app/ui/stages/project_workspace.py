"""Dashboard workspace for the new UI."""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, List, Sequence, Set, Tuple

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from shiboken6 import isValid
from PySide6.QtGui import QDesktopServices, QColor, QBrush
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QDialog,
)
from PySide6.QtWidgets import QHeaderView

from src.app.core.conversion_manager import ConversionJob
from src.app.core.feature_flags import FeatureFlags
from src.app.core.file_tracker import WorkspaceMetrics
from src.app.core.project_manager import ProjectManager, ProjectMetadata
from src.app.core.bulk_analysis_groups import BulkAnalysisGroup
from src.app.core.bulk_paths import iter_map_outputs
from src.app.ui.dialogs.project_metadata_dialog import ProjectMetadataDialog
from src.app.ui.dialogs.bulk_analysis_group_dialog import BulkAnalysisGroupDialog
from src.app.ui.dialogs.prompt_preview_dialog import PromptPreviewDialog
from src.app.ui.workspace import BulkAnalysisTab, DocumentsTab, HighlightsTab, ReportsTab
from src.app.ui.workspace.controllers import (
    BulkAnalysisController,
    DocumentsController,
    HighlightsController,
    ReportsController,
)
from src.app.ui.workspace.qt_flags import (
    ITEM_IS_ENABLED,
    ITEM_IS_TRISTATE,
    ITEM_IS_USER_CHECKABLE,
)
from src.app.ui.workspace.services import HighlightsService, ReportsService
from src.app.workers import (
    BulkAnalysisWorker,
    BulkReduceWorker,
    ConversionWorker,
    WorkerCoordinator,
    get_worker_pool,
)
from src.app.workers.highlight_worker import HighlightExtractionSummary
from src.app.core.prompt_preview import generate_prompt_preview, PromptPreviewError

LOGGER = logging.getLogger(__name__)


class ProjectWorkspace(QWidget):
    """Dashboard workspace showing documents and bulk analysis groups."""

    home_requested = Signal()

    def __init__(
        self,
        project_manager: Optional[ProjectManager] = None,
        parent: Optional[QWidget] = None,
        *,
        feature_flags: Optional[FeatureFlags] = None,
    ) -> None:
        super().__init__(parent)
        self._feature_flags = feature_flags or FeatureFlags()
        self._project_manager: Optional[ProjectManager] = None
        self._project_path_label = QLabel()
        self._metadata_label: QLabel | None = None
        self._edit_metadata_button: QPushButton | None = None
        self._home_button: QPushButton | None = None
        self._workspace_metrics: WorkspaceMetrics | None = None
        self._thread_pool = get_worker_pool()
        self._workers = WorkerCoordinator(self._thread_pool)
        self._inflight_sources: set[Path] = set()
        self._conversion_running = False
        self._conversion_total = 0
        self._running_groups: set[str] = set()
        self._bulk_progress: Dict[str, tuple[int, int]] = {}
        self._bulk_failures: Dict[str, List[str]] = {}
        self._cancelling_groups: set[str] = set()
        self._bulk_analysis_tab: BulkAnalysisTab | None = None
        self._bulk_controller: BulkAnalysisController | None = None
        self._missing_bulk_label: QLabel | None = None
        self._missing_highlights_label: QLabel | None = None
        self._highlights_tab: HighlightsTab | None = None
        self._highlights_controller: HighlightsController | None = None
        self._reports_tab: ReportsTab | None = None
        self._reports_controller: ReportsController | None = None

        self._documents_controller: DocumentsController | None = None
        self._highlight_service = HighlightsService(self._workers)
        self._reports_service = ReportsService(self._workers)
        self._build_ui()
        if project_manager:
            self.set_project(project_manager)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        self._home_button = QPushButton("home")
        self._home_button.setCursor(Qt.PointingHandCursor)
        self._home_button.setFlat(True)
        self._home_button.clicked.connect(self.home_requested.emit)
        top_bar.addWidget(self._home_button)

        self._project_path_label.setStyleSheet("font-weight: 600;")
        top_bar.addWidget(self._project_path_label)
        top_bar.addStretch()

        layout.addLayout(top_bar)

        self._tabs = QTabWidget()
        self._documents_tab = self._build_documents_tab()
        self._tabs.addTab(self._documents_tab, "Documents")
        self._highlights_tab = self._build_highlights_tab()
        self._tabs.addTab(self._highlights_tab, "Highlights")
        if self._feature_flags.bulk_analysis_groups_enabled:
            self._bulk_analysis_tab = self._build_bulk_analysis_tab()
            self._tabs.addTab(self._bulk_analysis_tab, "Bulk Analysis")
        self._reports_tab = self._build_reports_tab()
        self._tabs.addTab(self._reports_tab, "Reports")
        metadata_row = QHBoxLayout()
        metadata_row.setContentsMargins(0, 0, 0, 0)
        self._metadata_label = QLabel("Subject: — | DOB: —")
        self._metadata_label.setStyleSheet("color: #555;")
        metadata_row.addWidget(self._metadata_label)
        metadata_row.addStretch()
        self._edit_metadata_button = QPushButton("Edit Project Info…")
        self._edit_metadata_button.setEnabled(False)
        self._edit_metadata_button.clicked.connect(self._edit_project_metadata)
        metadata_row.addWidget(self._edit_metadata_button)
        layout.addLayout(metadata_row)
        layout.addWidget(self._tabs)

    def _build_documents_tab(self) -> QWidget:
        tab = DocumentsTab(parent=self)
        self._documents_controller = DocumentsController(self, tab, self._start_conversion)
        self._source_root_label = tab.source_root_label
        self._counts_label = tab.counts_label
        self._last_scan_label = tab.last_scan_label
        self._rescan_button = tab.rescan_button
        self._source_tree = tab.source_tree
        self._root_warning_label = tab.root_warning_label
        self._missing_highlights_label = tab.missing_highlights_label
        self._missing_bulk_label = tab.missing_bulk_label

        self._rescan_button.clicked.connect(lambda: self._trigger_conversion(auto_run=False))
        self._source_tree.itemChanged.connect(self._on_source_item_changed)
        return tab

    def _build_highlights_tab(self) -> HighlightsTab:
        tab = HighlightsTab(parent=self)
        self._highlights_controller = HighlightsController(
            self,
            tab,
            on_extract_requested=self._handle_highlight_extract_requested,
            counts_label=self._counts_label,
        )
        return tab

    def _build_reports_tab(self) -> ReportsTab:
        tab = ReportsTab(parent=self)
        self._reports_controller = ReportsController(self, tab, service=self._reports_service)
        return tab

    def _build_bulk_analysis_tab(self) -> QWidget:
        tab = BulkAnalysisTab(parent=self)
        self._bulk_analysis_tab = tab
        self._bulk_controller = BulkAnalysisController(
            tab,
            on_create_group=self._show_create_group_dialog,
            on_refresh_requested=self.refresh,
            on_start_group_run=lambda group, force: self._start_group_run(group, force_rerun=force),
            on_start_combined_run=lambda group, force: self._start_combined_run(group, force_rerun=force),
            on_cancel_group_run=self._cancel_group_run,
            on_open_group_folder=self._open_group_folder,
            on_show_prompt_preview=self._show_group_prompt_preview,
            on_open_latest_combined=self._open_latest_combined,
            on_delete_group=self._confirm_delete_group,
        )
        return tab

    def set_project(self, project_manager: ProjectManager) -> None:
        """Attach the workspace to a project manager."""
        self._project_manager = project_manager
        self._documents_controller.set_project(project_manager)
        if self._bulk_controller:
            self._bulk_controller.set_project(project_manager)
        if self._highlights_controller:
            self._highlights_controller.set_project(project_manager)
            self._highlights_controller.set_conversion_running(self._conversion_running)
        if self._reports_controller:
            self._reports_controller.set_project(project_manager)
        self._running_groups.clear()
        self._workers.clear()
        self._workspace_metrics = None
        project_dir = project_manager.project_dir
        project_path = Path(project_dir).resolve() if project_dir else None
        self._project_path_label.setText(
            f"Active project: {project_path}" if project_path else "Active project: (unsaved)"
        )
        if self._edit_metadata_button:
            self._edit_metadata_button.setEnabled(True)
        self._update_metadata_label()
        self.refresh()

    def project_manager(self) -> Optional[ProjectManager]:
        return self._project_manager

    @property
    def bulk_controller(self) -> BulkAnalysisController | None:
        return self._bulk_controller

    @property
    def bulk_tab(self) -> BulkAnalysisTab | None:
        return self._bulk_analysis_tab

    @property
    def reports_controller(self) -> ReportsController | None:
        return self._reports_controller

    def shutdown(self) -> None:
        """Cancel background work before disposing of the workspace."""

        self._workers.clear()
        self._running_groups.clear()
        self._bulk_progress.clear()
        self._bulk_failures.clear()
        self._documents_controller.shutdown()
        if self._bulk_controller:
            self._bulk_controller.set_project(None)
        if self._highlights_controller:
            self._highlights_controller.set_project(None)
        if self._reports_controller:
            self._reports_controller.shutdown()

    def refresh(self) -> None:
        if self._documents_controller:
            metrics = self._documents_controller.refresh()
            if metrics is not None:
                self._workspace_metrics = metrics
        else:
            self._populate_source_tree()
            self._update_source_root_label()
            self._refresh_file_tracker()
        self._refresh_reports_view()
        self._refresh_highlights_view()
        if self._feature_flags.bulk_analysis_groups_enabled:
            self._prune_running_groups()
            self._refresh_bulk_analysis_groups()
        else:
            self._running_groups.clear()
        self._update_metadata_label()

    def _update_metadata_label(self) -> None:
        if not self._metadata_label:
            return
        metadata = self._project_manager.metadata if self._project_manager else None
        if not metadata:
            self._metadata_label.setText("Subject: — | DOB: —")
            return

        subject = metadata.subject_name.strip() if metadata.subject_name else "—"
        dob = metadata.date_of_birth.strip() if metadata.date_of_birth else "—"
        parts = [f"Subject: {subject}", f"DOB: {dob}"]
        if metadata.case_description:
            first_line = metadata.case_description.strip().splitlines()[0]
            if len(first_line) > 80:
                first_line = first_line[:77] + "…"
            parts.append(f"Case info: {first_line}")
        self._metadata_label.setText(" | ".join(parts))

    def _edit_project_metadata(self) -> None:
        if not self._project_manager:
            return

        dialog = ProjectMetadataDialog(self._project_manager.metadata, self)
        if dialog.exec() != QDialog.Accepted:
            return

        updated = dialog.result_metadata()
        self._project_manager.update_metadata(metadata=updated)
        self._project_manager.save_project()
        self._update_metadata_label()

    def begin_initial_conversion(self) -> None:
        """Trigger an initial scan/conversion after project creation."""
        if self._feature_flags.auto_run_conversion_on_create:
            self._trigger_conversion(auto_run=True)

    def _refresh_file_tracker(self) -> None:
        if self._documents_controller:
            metrics = self._documents_controller.refresh_file_tracker()
            if metrics is not None:
                self._workspace_metrics = metrics
            return
        if not self._project_manager:
            return
        try:
            self._workspace_metrics = self._project_manager.get_workspace_metrics(refresh=True)
        except Exception:
            self._counts_label.setText("Scan failed")
            if getattr(self, "_missing_highlights_label", None):
                self._missing_highlights_label.setText("")
            if getattr(self, "_missing_bulk_label", None):
                self._missing_bulk_label.setText("")
            return

        metrics = self._workspace_metrics.dashboard

        converted_total = metrics.imported_total
        if converted_total:
            pdf_total = metrics.highlights_total + metrics.pending_highlights
            highlight_text = f"Highlights: {metrics.highlights_total} of {pdf_total}"
            if metrics.pending_highlights:
                highlight_text += f" (pending {metrics.pending_highlights})"
            bulk_text = f"Bulk analysis: {metrics.bulk_analysis_total} of {converted_total}"
            if metrics.pending_bulk_analysis:
                bulk_text += f" (pending {metrics.pending_bulk_analysis})"
            counts_text = (
                f"Converted: {converted_total} | "
                f"{highlight_text} | "
                f"{bulk_text}"
            )
        else:
            counts_text = "Converted: 0 | Highlights: 0 | Bulk analysis: 0"
        self._counts_label.setText(counts_text)

        bulk_missing = list(self._workspace_metrics.bulk_missing)
        highlights_missing = list(self._workspace_metrics.highlights_missing)

        if getattr(self, "_missing_highlights_label", None):
            self._missing_highlights_label.setText(
                "Highlights missing: " + (", ".join(highlights_missing) if highlights_missing else "None")
            )

        if getattr(self, "_missing_bulk_label", None):
            self._missing_bulk_label.setText(
                "Bulk analysis missing: " + (", ".join(bulk_missing) if bulk_missing else "None")
            )

        self._update_last_scan_label()

    def _refresh_highlights_view(self) -> None:
        if not self._highlights_controller:
            return
        highlight_state = self._project_manager.highlight_state if self._project_manager else None
        self._highlights_controller.set_conversion_running(self._conversion_running)
        self._highlights_controller.refresh(
            metrics=self._workspace_metrics,
            highlight_state=highlight_state,
        )

    def _refresh_reports_view(self) -> None:
        if self._reports_controller:
            self._reports_controller.refresh()

    def _handle_highlight_extract_requested(self) -> None:
        if not self._project_manager or not self._highlights_controller:
            return
        if self._highlight_service.is_running() or self._highlights_controller.is_running():
            QMessageBox.information(
                self,
                "Highlights",
                "Highlight extraction is already in progress.",
            )
            return

        started = self._highlight_service.run(
            project_manager=self._project_manager,
            on_started=self._highlights_controller.begin_extraction,
            on_progress=self._highlights_controller.update_progress,
            on_failed=self._highlights_controller.record_failure,
            on_finished=self._on_highlight_run_finished,
        )
        if not started:
            QMessageBox.information(
                self,
                "Highlights",
                "No converted PDFs are ready for highlight extraction.",
            )

    def _on_highlight_run_finished(
        self,
        summary: HighlightExtractionSummary | None,
        successes: int,
        failures: int,
    ) -> None:
        if self._highlights_controller:
            self._highlights_controller.finish(summary=summary, failures=failures)

        if summary and self._project_manager:
            self._project_manager.record_highlight_run(
                generated_at=summary.generated_at,
                documents_processed=summary.documents_processed,
                documents_with_highlights=summary.documents_with_highlights,
                total_highlights=summary.total_highlights,
                color_files_written=summary.color_files_written,
            )

        self._refresh_file_tracker()
        self._refresh_highlights_view()

    # ------------------------------------------------------------------
    # Source tree helpers
    # ------------------------------------------------------------------
    def _trigger_conversion(self, auto_run: bool) -> None:
        if self._documents_controller:
            self._documents_controller.trigger_conversion(auto_run)

    def _handle_rescan_clicked(self) -> None:
        self._trigger_conversion(auto_run=False)

    def _select_source_root(self) -> None:
        if not self._project_manager or not self._project_manager.project_dir:
            QMessageBox.warning(self, "Project Required", "Create or open a project first.")
            return
        start_dir = str(self._resolve_source_root() or self._project_manager.project_dir)
        chosen = QFileDialog.getExistingDirectory(self, "Select Source Folder", start_dir)
        if not chosen:
            return
        chosen_path = Path(chosen)
        if self._documents_controller:
            relative = self._documents_controller.to_project_relative(chosen_path)
        else:
            relative = self._to_project_relative(chosen_path)
        self._project_manager.update_source_state(
            root=relative,
            selected_folders=[],
            warnings=[],
        )
        if self._documents_controller:
            self._documents_controller.populate_source_tree()
            self._documents_controller.update_source_root_label()
            self._documents_controller.update_last_scan_label()
            self._documents_controller.set_root_warning([])
        else:
            self._populate_source_tree()
            self._update_source_root_label()
            self._update_last_scan_label()
            self._set_root_warning([])


    def _update_last_scan_label(self) -> None:
        if self._documents_controller:
            self._documents_controller.update_last_scan_label()
            return
        if not self._project_manager:
            self._last_scan_label.setText("")
            return
        metrics = None
        if self._workspace_metrics:
            metrics = self._workspace_metrics.dashboard
        elif self._project_manager.dashboard_metrics:
            metrics = self._project_manager.dashboard_metrics
        last_scan = metrics.last_scan if metrics else None
        if not last_scan and self._project_manager.source_state.last_scan:
            try:
                last_scan = datetime.fromisoformat(self._project_manager.source_state.last_scan)
            except ValueError:
                last_scan = self._project_manager.source_state.last_scan

        if not last_scan:
            self._last_scan_label.setText("Last scan: never")
            return
        if isinstance(last_scan, datetime):
            display = last_scan.strftime("Last scan: %Y-%m-%d %H:%M")
        else:
            display = f"Last scan: {last_scan}"
        self._last_scan_label.setText(display)

    def _populate_source_tree(self) -> None:
        if self._documents_controller:
            self._documents_controller.populate_source_tree()

    def _populate_directory_contents(self, *args, **kwargs) -> None:
        if self._documents_controller:
            self._documents_controller.populate_directory_contents(*args, **kwargs)

    def _iter_directories(self, root_path: Path) -> List[str]:
        if self._documents_controller:
            return self._documents_controller.iter_directories(root_path)
        return []

    def _normalise_relative_path(self, path: str) -> str:
        if self._documents_controller:
            return self._documents_controller.normalise_relative_path(path)
        return Path(path.strip('/')).as_posix() if path else ''

    def _apply_directory_flags(self, item: QTreeWidgetItem) -> None:
        if self._documents_controller:
            self._documents_controller.apply_directory_flags(item)

    def _should_skip_source_entry(self, entry: Path) -> bool:
        if self._documents_controller:
            return self._documents_controller.should_skip_source_entry(entry)
        return False

    def _is_path_tracked(self, relative: str, tracked: Set[str]) -> bool:
        if self._documents_controller:
            return self._documents_controller.is_path_tracked(relative, tracked)
        return False

    def _compute_new_directories(self, actual: Set[str], selected: Set[str], acknowledged: Set[str]) -> List[str]:
        if self._documents_controller:
            return self._documents_controller.compute_new_directories(actual, selected, acknowledged)
        return []

    def _mark_directory_as_new(self, relative: str) -> None:
        if self._documents_controller:
            self._documents_controller.mark_directory_as_new(relative)

    def _clear_new_directory_marker(self, relative: str) -> None:
        if self._documents_controller:
            self._documents_controller.clear_new_directory_marker(relative)

    def _acknowledge_directories(self, directories: Sequence[str]) -> None:
        if self._documents_controller:
            self._documents_controller.acknowledge_directories(directories)

    def _prompt_for_new_directories(self, new_dirs: Sequence[str]) -> None:
        if self._documents_controller:
            self._documents_controller.prompt_for_new_directories(new_dirs)

    def _expand_to_item(self, item: QTreeWidgetItem) -> None:
        if self._documents_controller:
            self._documents_controller.expand_to_item(item)

    def _handle_missing_directories(self, missing_dirs: Sequence[str]) -> None:
        if self._documents_controller:
            self._documents_controller.handle_missing_directories(missing_dirs)

    def _on_source_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._documents_controller:
            self._documents_controller.handle_source_item_changed(item, column)

    def _cascade_source_check_state(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        if self._documents_controller:
            self._documents_controller.cascade_source_check_state(item, state)

    def _update_parent_source_state(self, item: Optional[QTreeWidgetItem]) -> None:
        if self._documents_controller:
            self._documents_controller.update_parent_source_state(item)

    def _update_selected_folders_from_tree(self) -> None:
        if self._documents_controller:
            self._documents_controller.update_selected_folders_from_tree()

    def _collect_selected_directories(self) -> List[str]:
        if self._documents_controller:
            return self._documents_controller.collect_selected_directories()
        return []

    def _collect_selected_directories_from_item(self, item: QTreeWidgetItem, results: Set[str]) -> None:
        if self._documents_controller:
            self._documents_controller.collect_selected_directories_from_item(item, results)

    def _set_root_warning(self, warnings: List[str]) -> None:
        if self._documents_controller:
            self._documents_controller.set_root_warning(warnings)
        elif self._root_warning_label:
            if warnings:
                self._root_warning_label.setText("\n".join(warnings))
                self._root_warning_label.show()
            else:
                self._root_warning_label.clear()
                self._root_warning_label.hide()

    def _compute_root_warnings(self, root_path: Path) -> List[str]:
        if self._documents_controller:
            return self._documents_controller.compute_root_warnings(root_path)
        return []

    def _update_source_root_label(self) -> None:
        if self._documents_controller:
            self._documents_controller.update_source_root_label()
            return
        if not self._project_manager:
            self._source_root_label.setText("Source root: not set")
            return
        root_path = self._resolve_source_root()
        if not root_path or not root_path.exists():
            self._source_root_label.setText("Source root: not set")
        else:
            self._source_root_label.setText(f"Source root: {root_path}")

    def _prompt_reselect_source_root(self) -> None:
        if self._documents_controller:
            self._documents_controller.prompt_reselect_source_root()

    def _schedule_file_tracker_refresh(self) -> None:
        if self._documents_controller:
            self._documents_controller.schedule_file_tracker_refresh()

    def _run_scheduled_file_tracker_refresh(self) -> None:
        if self._documents_controller:
            self._documents_controller.run_scheduled_file_tracker_refresh()

    def _find_child(self, parent: QTreeWidgetItem, name: str) -> Optional[QTreeWidgetItem]:
        for index in range(parent.childCount()):
            child = parent.child(index)
            if child.text(0) == name:
                return child
        return None

    def _resolve_source_root(self) -> Optional[Path]:
        if not self._project_manager or not self._project_manager.project_dir:
            return None
        root_spec = (self._project_manager.source_state.root or "").strip()
        if not root_spec:
            return None
        root_path = Path(root_spec)
        if not root_path.is_absolute():
            root_path = (self._project_manager.project_dir / root_path).resolve()
        return root_path

    def _to_project_relative(self, path: Path) -> str:
        if not self._project_manager or not self._project_manager.project_dir:
            return path.as_posix()
        project_dir = Path(self._project_manager.project_dir).resolve()
        try:
            rel = path.resolve().relative_to(project_dir)
            return rel.as_posix()
        except ValueError:
            rel_str = os.path.relpath(path.resolve(), project_dir)
            return Path(rel_str).as_posix()

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------
    def _start_conversion(self, jobs: List[ConversionJob]) -> None:
        if not self._project_manager or not jobs:
            return

        self._conversion_running = True
        self._conversion_total = len(jobs)
        self._conversion_errors: List[str] = []
        self._rescan_button.setEnabled(False)
        self._counts_label.setText(f"Converting documents (0/{self._conversion_total})…")
        if self._highlights_controller:
            self._highlights_controller.set_conversion_running(True)

        self._inflight_sources.update(job.source_path for job in jobs)

        helper = self._project_manager.conversion_settings.helper
        options = dict(self._project_manager.conversion_settings.options or {})
        worker = ConversionWorker(jobs, helper=helper, options=options)
        worker.progress.connect(self._on_conversion_progress)
        worker.file_failed.connect(self._on_conversion_failed)
        worker.finished.connect(
            lambda success, failed, w=worker, js=jobs: self._on_conversion_finished(
                w, js, success, failed
            )
        )
        
        self._workers.start(self._conversion_key(), worker)

    def _on_conversion_progress(self, processed: int, total: int, relative_path: str) -> None:
        self._counts_label.setText(f"Converting documents ({processed}/{total})… {relative_path}")

    def _on_conversion_failed(self, source_path: str, error: str) -> None:
        message = f"{Path(source_path).name}: {error}"
        self._conversion_errors.append(message)

    def _on_conversion_finished(
        self,
        worker: ConversionWorker,
        jobs: Sequence[ConversionJob],
        successes: int,
        failures: int,
    ) -> None:
        stored = self._workers.pop(self._conversion_key())
        # Always attempt to delete the actual worker and any stored reference safely
        if worker and isValid(worker):
            worker.deleteLater()
        if stored and stored is not worker and isValid(stored):
            stored.deleteLater()
        for job in jobs:
            self._inflight_sources.discard(job.source_path)

        timestamp = datetime.utcnow().isoformat()
        warnings = self._documents_controller.current_warnings if self._documents_controller else []
        self._project_manager.update_source_state(last_scan=timestamp, warnings=warnings)
        self._update_last_scan_label()

        self._conversion_running = False
        self._rescan_button.setEnabled(True)
        if self._highlights_controller:
            self._highlights_controller.set_conversion_running(False)
        self._refresh_file_tracker()
        self._refresh_highlights_view()
        if failures:
            error_text = "\n".join(self._conversion_errors) or "Unknown errors"
            QMessageBox.warning(
                self,
                "Conversion Issues",
                "Some documents failed to convert:\n\n" + error_text,
            )

    # ------------------------------------------------------------------
    # Highlight extraction helpers
    # ------------------------------------------------------------------
    def _refresh_bulk_analysis_groups(self) -> None:
        if not self._feature_flags.bulk_analysis_groups_enabled:
            return
        if not self._bulk_controller:
            return

        groups: Sequence[BulkAnalysisGroup] = []
        if self._project_manager:
            try:
                groups = self._project_manager.list_bulk_analysis_groups()
            except Exception:
                groups = []

        self._bulk_controller.refresh(
            groups=groups,
            workspace_metrics=self._workspace_metrics,
            running_groups=self._running_groups,
            progress_map=self._bulk_progress,
            cancelling_groups=self._cancelling_groups,
        )

    def _show_create_group_dialog(self) -> None:
        if not self._feature_flags.bulk_analysis_groups_enabled:
            return
        if not self._project_manager or not self._project_manager.project_dir:
            return
        dialog = BulkAnalysisGroupDialog(
            self._project_manager.project_dir,
            self,
            metadata=self._project_manager.metadata,
        )
        if dialog.exec() == QDialog.Accepted:
            group = dialog.build_group()
            try:
                self._project_manager.save_bulk_analysis_group(group)
            except Exception as exc:
                QMessageBox.critical(self, "Create Bulk Analysis Group Failed", str(exc))
            else:
                self.refresh()

    def _confirm_delete_group(self, group: BulkAnalysisGroup) -> None:
        if not self._feature_flags.bulk_analysis_groups_enabled:
            return
        if not self._project_manager:
            return
        message = (
            f"Delete bulk analysis group '{group.name}'?\n\n"
            "All generated bulk analysis outputs stored in this group will be deleted."
        )
        reply = QMessageBox.question(
            self,
            "Delete Bulk Analysis Group",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if not self._project_manager.delete_bulk_analysis_group(group.group_id):
                QMessageBox.warning(self, "Delete Failed", "Could not delete the bulk analysis group.")
            else:
                self._cancel_group_run(group)
                self.refresh()

    def _open_group_folder(self, group: BulkAnalysisGroup) -> None:
        if not self._feature_flags.bulk_analysis_groups_enabled:
            return
        if not self._project_manager or not self._project_manager.project_dir:
            return
        folder = self._project_manager.project_dir / "bulk_analysis" / group.folder_name
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _show_group_prompt_preview(self, group: BulkAnalysisGroup) -> None:
        if not self._feature_flags.bulk_analysis_groups_enabled:
            return
        if not self._project_manager or not self._project_manager.project_dir:
            QMessageBox.warning(self, "Prompt Preview", "Open a project to preview prompts.")
            return

        project_dir = Path(self._project_manager.project_dir)
        metadata = self._project_manager.metadata

        try:
            preview = generate_prompt_preview(project_dir, group, metadata=metadata)
        except PromptPreviewError as exc:
            QMessageBox.warning(self, "Prompt Preview", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Prompt preview failed: %s", exc)
            QMessageBox.warning(self, "Prompt Preview", "Failed to generate prompt preview.")
            return

        dialog = PromptPreviewDialog(self)
        dialog.set_prompts(preview.system_prompt, preview.user_prompt)
        dialog.exec()

    def _open_latest_combined(self, group: BulkAnalysisGroup) -> None:
        if not self._feature_flags.bulk_analysis_groups_enabled:
            return
        if not self._project_manager or not self._project_manager.project_dir:
            return
        folder = self._project_manager.project_dir / "bulk_analysis" / group.folder_name / "reduce"
        if not folder.exists():
            QMessageBox.information(self, "No Outputs", "No combined outputs found for this operation.")
            return
        latest = None
        latest_m = None
        for f in folder.glob("combined_*.md"):
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            if latest is None or m > (latest_m or 0):
                latest = f
                latest_m = m
        if latest is None:
            QMessageBox.information(self, "No Outputs", "No combined outputs found for this operation.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(latest)))

    def _start_group_run(self, group: BulkAnalysisGroup, *, force_rerun: bool = False) -> None:
        if not self._feature_flags.bulk_analysis_groups_enabled:
            return
        if group.group_id in self._running_groups:
            QMessageBox.information(
                self,
                "Already Running",
                f"Bulk analysis for '{group.name}' is already in progress.",
            )
            return

        if not self._workspace_metrics and self._project_manager:
            try:
                self._workspace_metrics = self._project_manager.get_workspace_metrics()
            except Exception:
                self._workspace_metrics = None

        group_metrics = None
        if self._workspace_metrics:
            group_metrics = self._workspace_metrics.groups.get(group.group_id)

        if not group_metrics:
            QMessageBox.warning(
                self,
                "Bulk Analysis",
                "Project metrics are unavailable. Re-scan sources before running bulk analysis.",
            )
            return

        files: List[str] = []
        if force_rerun:
            converted = list(group_metrics.converted_files)
            if not converted:
                QMessageBox.warning(
                    self,
                    "No Converted Documents",
                    "This group does not have any converted documents yet. Run conversion first.",
                )
                return
            files = converted
        else:
            pending = list(group_metrics.pending_files)
            if pending:
                files = pending
            else:
                QMessageBox.information(
                    self,
                    "Up to Date",
                    "All documents already have bulk analysis results. Use 'Run All' to re-process everything.",
                )
                return

        if not self._project_manager or not self._project_manager.project_dir:
            QMessageBox.warning(self, "Missing Project", "The project directory is not available.")
            return

        provider_default = (
            (self._project_manager.settings or {}).get("llm_provider", ""),
            (self._project_manager.settings or {}).get("llm_model", ""),
        )
        worker = BulkAnalysisWorker(
            project_dir=self._project_manager.project_dir,
            group=group,
            files=files,
            metadata=self._project_manager.metadata,
            default_provider=provider_default,
            force_rerun=force_rerun,
        )
        worker.progress.connect(
            lambda done, total, path, gid=group.group_id: self._on_bulk_progress(gid, done, total, path)
        )
        worker.file_failed.connect(lambda rel, err, gid=group.group_id: self._on_bulk_failed(gid, rel, err))
        worker.finished.connect(
            lambda success, failed, w=worker, gid=group.group_id: self._on_bulk_finished(gid, w, success, failed)
        )
        worker.log_message.connect(lambda message, gid=group.group_id: self._on_bulk_log(gid, message))

        key = self._bulk_key(group.group_id)
        self._running_groups.add(group.group_id)
        self._bulk_progress[group.group_id] = (0, len(files))
        self._bulk_failures[group.group_id] = []
        self._cancelling_groups.discard(group.group_id)
        self._on_bulk_log(
            group.group_id,
            f"Starting bulk analysis for '{group.name}' ({len(files)} {'all documents' if force_rerun else 'pending documents'}).",
        )
        self._refresh_bulk_analysis_groups()
        self._workers.start(key, worker)

    def _start_combined_run(self, group: BulkAnalysisGroup, *, force_rerun: bool = False) -> None:
        if not self._feature_flags.bulk_analysis_groups_enabled:
            return
        if group.group_id in self._running_groups:
            QMessageBox.information(self, "Already Running", f"Combined operation for '{group.name}' is already in progress.")
            return
        if not self._project_manager or not self._project_manager.project_dir:
            QMessageBox.warning(self, "Missing Project", "The project directory is not available.")
            return
        if force_rerun:
            confirm = QMessageBox.question(
                self,
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

        worker = BulkReduceWorker(
            project_dir=self._project_manager.project_dir,
            group=group,
            metadata=self._project_manager.metadata,
            force_rerun=force_rerun,
        )
        gid = group.group_id
        key = f"combine:{gid}"
        self._running_groups.add(gid)
        self._bulk_progress[gid] = (0, 1)
        self._bulk_failures[gid] = []
        self._cancelling_groups.discard(gid)
        mode_label = "force" if force_rerun else "standard"
        self._on_bulk_log(gid, f"Starting combined operation for '{group.name}' ({mode_label}).")
        worker.progress.connect(lambda done, total, msg, g=gid: self._on_bulk_progress(g, done, total, msg))
        worker.file_failed.connect(lambda rel, err, g=gid: self._on_bulk_failed(g, rel, err))
        worker.log_message.connect(lambda message, g=gid: self._on_bulk_log(g, message))
        worker.finished.connect(lambda success, failed, w=worker, g=gid: self._on_bulk_finished(g, w, success, failed))
        self._workers.start(key, worker)

    def _cancel_group_run(self, group: BulkAnalysisGroup) -> None:
        if not self._feature_flags.bulk_analysis_groups_enabled:
            return
        key = self._bulk_key(group.group_id)
        worker = self._workers.get(key)
        if worker:
            worker.cancel()
            self._cancelling_groups.add(group.group_id)
            if self._bulk_controller:
                self._bulk_controller.set_info_message("Cancelling bulk analysis…")
        else:
            self._bulk_progress.pop(group.group_id, None)
            self._bulk_failures.pop(group.group_id, None)
            self._cancelling_groups.discard(group.group_id)
            if self._bulk_controller:
                self._bulk_controller.set_info_message("Bulk analysis cancelled.")
        self._refresh_bulk_analysis_groups()

    def _on_bulk_progress(self, group_id: str, completed: int, total: int, relative_path: str) -> None:
        if group_id in self._cancelling_groups:
            return
        self._bulk_progress[group_id] = (completed, total)
        if self._bulk_controller:
            self._bulk_controller.set_progress_message(completed, total, relative_path)
        self._refresh_bulk_analysis_groups()

    def _on_bulk_failed(self, group_id: str, relative_path: str, error: str) -> None:
        LOGGER.error("Bulk analysis failed for %s: %s", relative_path, error)
        self._bulk_failures.setdefault(group_id, []).append(f"{relative_path}: {error}")

    def _on_bulk_log(self, group_id: str, message: str) -> None:  # noqa: ARG002 - future use
        LOGGER.info("[BulkAnalysis][%s] %s", group_id, message)
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        if self._bulk_controller:
            self._bulk_controller.append_log_message(formatted)
            self._bulk_controller.set_info_message(message)

    def _on_bulk_finished(self, group_id: str, worker, successes: int, failures: int) -> None:
        key = self._bulk_key(group_id)
        stored = self._workers.pop(key)
        self._running_groups.discard(group_id)
        # Delete the specific worker instance and any different stored worker safely
        if worker and isValid(worker):
            worker.deleteLater()
        if stored and stored is not worker and isValid(stored):
            stored.deleteLater()
        self._bulk_progress.pop(group_id, None)
        errors = self._bulk_failures.pop(group_id, [])
        was_cancelled = group_id in self._cancelling_groups
        if was_cancelled:
            self._cancelling_groups.discard(group_id)

        if was_cancelled:
            completion_message = "Bulk analysis cancelled."
        elif failures:
            completion_message = f"Bulk analysis completed with {failures} error(s)."
        else:
            completion_message = "Bulk analysis completed."
        self._on_bulk_log(group_id, completion_message)

        if errors:
            QMessageBox.warning(
                self,
                "Bulk Analysis Issues",
                "Some documents failed during bulk analysis:\n" + "\n".join(errors),
            )

        self._refresh_file_tracker()
        self._refresh_bulk_analysis_groups()

    def _prune_running_groups(self, valid_ids: Optional[set[str]] = None) -> None:
        if not self._feature_flags.bulk_analysis_groups_enabled:
            return
        if valid_ids is None:
            valid_ids = set()
            if self._project_manager:
                try:
                    valid_ids = {
                        group.group_id for group in self._project_manager.list_bulk_analysis_groups()
                    }
                except Exception:
                    valid_ids = set()
        stale = [gid for gid in list(self._running_groups) if gid not in valid_ids]
        for gid in stale:
            key = self._bulk_key(gid)
            worker = self._workers.pop(key)
            if worker:
                worker.cancel()
                if isValid(worker):
                    worker.deleteLater()
            self._running_groups.discard(gid)
            self._bulk_progress.pop(gid, None)
            self._bulk_failures.pop(gid, None)
            self._cancelling_groups.discard(gid)

    # ------------------------------------------------------------------
    # Worker coordination helpers
    # ------------------------------------------------------------------
    def _conversion_key(self) -> str:
        return "conversion:active"

    def _bulk_key(self, group_id: str) -> str:
        return f"bulk:{group_id}"
