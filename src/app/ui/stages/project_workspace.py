"""Dashboard workspace for the new UI."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Sequence

from PySide6.QtCore import Qt, QUrl
from shiboken6 import isValid
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QDialog,
)
from PySide6.QtWidgets import QHeaderView

from src.app.core.conversion_manager import ConversionJob, build_conversion_jobs
from src.app.core.feature_flags import FeatureFlags
from src.app.core.file_tracker import WorkspaceMetrics, WorkspaceGroupMetrics
from src.app.core.project_manager import ProjectManager
from src.app.core.summary_groups import SummaryGroup
from src.app.ui.dialogs.project_metadata_dialog import ProjectMetadataDialog
from src.app.ui.dialogs.summary_group_dialog import SummaryGroupDialog
from src.app.workers import (
    BulkAnalysisWorker,
    BulkReduceWorker,
    ConversionWorker,
    HighlightWorker,
    WorkerCoordinator,
    get_worker_pool,
)

LOGGER = logging.getLogger(__name__)


class ProjectWorkspace(QWidget):
    """Dashboard workspace showing documents and bulk analysis groups."""

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
        self._workspace_metrics: WorkspaceMetrics | None = None
        self._current_warnings: List[str] = []
        self._thread_pool = get_worker_pool()
        self._workers = WorkerCoordinator(self._thread_pool)
        self._inflight_sources: set[Path] = set()
        self._conversion_running = False
        self._conversion_total = 0
        self._missing_root_prompted = False
        self._running_groups: set[str] = set()
        self._bulk_progress: Dict[str, tuple[int, int]] = {}
        self._bulk_failures: Dict[str, List[str]] = {}
        self._cancelling_groups: set[str] = set()
        self._summary_tab: QWidget | None = None
        self._summary_table: QTableWidget | None = None
        self._summary_empty_label: QLabel | None = None
        self._summary_info_label: QLabel | None = None
        self._missing_bulk_label: QLabel | None = None
        self._group_source_tree: QTreeWidget | None = None
        self._extract_highlights_button: QPushButton | None = None
        self._highlight_running = False
        self._highlight_total = 0
        self._highlight_errors: List[str] = []
        self._missing_highlights_label: QLabel | None = None

        self._build_ui()
        if project_manager:
            self.set_project(project_manager)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self._tabs = QTabWidget()
        self._documents_tab = self._build_documents_tab()
        self._tabs.addTab(self._documents_tab, "Documents")
        if self._feature_flags.summary_groups_enabled:
            self._summary_tab = self._build_summary_groups_tab()
            self._tabs.addTab(self._summary_tab, "Bulk Analysis")
        layout.addWidget(self._project_path_label)
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
        widget = QWidget()
        tab_layout = QVBoxLayout(widget)
        tab_layout.setSpacing(8)

        # Source root selector
        root_layout = QHBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        self._source_root_label = QLabel("Source root: not set")
        self._source_root_label.setStyleSheet("font-weight: bold;")
        root_layout.addWidget(self._source_root_label)
        root_layout.addStretch()
        tab_layout.addLayout(root_layout)

        # Counts + scan controls
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        self._counts_label = QLabel("Re-scan pending…")
        header_layout.addWidget(self._counts_label)
        header_layout.addStretch()
        self._last_scan_label = QLabel("")
        self._last_scan_label.setStyleSheet("color: #666;")
        header_layout.addWidget(self._last_scan_label)
        self._extract_highlights_button = QPushButton("Extract highlights")
        self._extract_highlights_button.setEnabled(False)
        self._extract_highlights_button.clicked.connect(self._trigger_highlight_extraction)
        header_layout.addWidget(self._extract_highlights_button)
        self._rescan_button = QPushButton("Re-scan")
        self._rescan_button.clicked.connect(lambda: self._trigger_conversion(auto_run=False))
        header_layout.addWidget(self._rescan_button)
        tab_layout.addLayout(header_layout)

        # Tree view for folder selection
        self._source_tree = QTreeWidget()
        self._source_tree.setHeaderHidden(True)
        self._source_tree.setSelectionMode(QAbstractItemView.NoSelection)
        tab_layout.addWidget(self._source_tree)

        self._root_warning_label = QLabel("")
        self._root_warning_label.setWordWrap(True)
        self._root_warning_label.setStyleSheet("color: #b26a00;")
        tab_layout.addWidget(self._root_warning_label)
        self._root_warning_label.hide()

        self._missing_highlights_label = QLabel("Highlights missing: —")
        self._missing_highlights_label.setWordWrap(True)
        tab_layout.addWidget(self._missing_highlights_label)

        self._missing_bulk_label = QLabel("Bulk analysis missing: —")

        self._missing_bulk_label.setWordWrap(True)
        tab_layout.addWidget(self._missing_bulk_label)

        tab_layout.addStretch()
        return widget

    def _build_summary_groups_tab(self) -> QWidget:
        self._summary_tab = QWidget()
        layout = QVBoxLayout(self._summary_tab)
        layout.setSpacing(8)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(QLabel("Manage bulk analysis groups to organise processed documents."))
        header_layout.addStretch()
        create_button = QPushButton("Create Group…")
        create_button.clicked.connect(self._show_create_group_dialog)
        header_layout.addWidget(create_button)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        header_layout.addWidget(refresh_button)
        layout.addLayout(header_layout)

        self._summary_info_label = QLabel("No bulk analysis groups yet.")
        layout.addWidget(self._summary_info_label)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        table_container = QVBoxLayout()
        table_container.setSpacing(6)

        self._summary_table = QTableWidget(0, 5)
        self._summary_table.setHorizontalHeaderLabels(["Group", "Coverage", "Updated", "Status", "Actions"])
        self._summary_table.verticalHeader().setVisible(False)
        self._summary_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._summary_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._summary_table.setSelectionMode(QAbstractItemView.NoSelection)
        header = self._summary_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        table_container.addWidget(self._summary_table)

        self._summary_empty_label = QLabel("No bulk analysis groups created yet.")
        self._summary_empty_label.setAlignment(Qt.AlignCenter)
        self._summary_empty_label.setStyleSheet("color: #666; padding: 20px;")
        table_container.addWidget(self._summary_empty_label)
        self._summary_empty_label.hide()

        content_layout.addLayout(table_container, 2)

        tree_container = QVBoxLayout()
        tree_container.setSpacing(4)
        tree_label = QLabel("Folder coverage (read-only)")
        tree_label.setStyleSheet("color: #666; font-size: 11px;")
        tree_container.addWidget(tree_label)

        self._group_source_tree = QTreeWidget()
        self._group_source_tree.setHeaderHidden(True)
        self._group_source_tree.setUniformRowHeights(True)
        self._group_source_tree.setSelectionMode(QAbstractItemView.NoSelection)
        self._group_source_tree.setFocusPolicy(Qt.NoFocus)
        tree_container.addWidget(self._group_source_tree)

        content_layout.addLayout(tree_container, 1)

        layout.addLayout(content_layout)

        return self._summary_tab

    def set_project(self, project_manager: ProjectManager) -> None:
        """Attach the workspace to a project manager."""
        self._project_manager = project_manager
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
        if self._extract_highlights_button:
            self._extract_highlights_button.setEnabled(True)
        self._update_metadata_label()
        self._populate_source_tree()
        self._update_source_root_label()
        self._update_last_scan_label()
        self.refresh()

    def project_manager(self) -> Optional[ProjectManager]:
        return self._project_manager

    def refresh(self) -> None:
        self._populate_source_tree()
        self._update_source_root_label()
        self._refresh_file_tracker()
        if self._feature_flags.summary_groups_enabled:
            self._prune_running_groups()
            self._refresh_summary_groups()
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
        if not self._project_manager:
            return
        try:
            self._workspace_metrics = self._project_manager.get_workspace_metrics(refresh=True)
        except Exception as exc:
            self._counts_label.setText("Scan failed")
            if getattr(self, "_missing_highlights_label", None):
                self._missing_highlights_label.setText("")
            if getattr(self, "_missing_bulk_label", None):
                self._missing_bulk_label.setText("")
            return

        metrics = self._workspace_metrics.dashboard

        converted_total = metrics.imported_total
        if converted_total:
            highlight_text = f"Highlights: {metrics.highlights_total} of {converted_total}"
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

    # ------------------------------------------------------------------
    # Source tree helpers
    # ------------------------------------------------------------------
    def _trigger_conversion(self, auto_run: bool) -> None:
        if not self._project_manager:
            return
        if self._conversion_running:
            QMessageBox.information(
                self,
                "Conversion Running",
                "Document conversion is already in progress.",
            )
            return

        jobs = self._collect_conversion_jobs()
        if not jobs:
            if not auto_run:
                QMessageBox.information(self, "Conversion", "No new files detected.")
            return

        if not auto_run:
            reply = QMessageBox.question(
                self,
                "Convert Documents",
                f"Convert {len(jobs)} new document(s) to markdown now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                return

        self._start_conversion(jobs)

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
        relative = self._to_project_relative(chosen_path)
        self._project_manager.update_source_state(
            root=relative,
            selected_folders=[],
            warnings=[],
        )
        self._populate_source_tree()
        self._update_source_root_label()
        self._update_last_scan_label()
        self._set_root_warning([])

    def _prompt_reselect_source_root(self) -> None:
        if not self._project_manager:
            return
        root_spec = self._project_manager.source_state.root
        if not root_spec:
            return
        response = QMessageBox.question(
            self,
            "Source Folder Missing",
            "The previously selected source folder cannot be found.\n"
            "Do you want to locate it now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if response == QMessageBox.Yes:
            self._missing_root_prompted = False
            self._select_source_root()

    def _update_source_root_label(self) -> None:
        if not self._project_manager:
            self._source_root_label.setText("Source root: not set")
            return
        root_path = self._resolve_source_root()
        if not root_path or not root_path.exists():
            self._source_root_label.setText("Source root: not set")
        else:
            self._source_root_label.setText(f"Source root: {root_path}")

    def _update_last_scan_label(self) -> None:
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
        if not hasattr(self, "_source_tree"):
            return
        self._source_tree.clear()

        if not self._project_manager:
            self._source_tree.setDisabled(True)
            self._set_root_warning([])
            return

        root_path = self._resolve_source_root()
        if not root_path or not root_path.exists():
            self._source_tree.setDisabled(True)
            warning = [
                "Source folder missing. Update the project location to resume scanning."
                if self._project_manager and self._project_manager.source_state.root
                else "Select a source folder to begin tracking documents."
            ]
            self._set_root_warning(warning)
            if self._project_manager:
                self._project_manager.update_source_state(warnings=warning)
                if not self._missing_root_prompted:
                    self._missing_root_prompted = True
                    self._prompt_reselect_source_root()
            return

        self._source_tree.setDisabled(False)
        self._missing_root_prompted = False

        selected = sorted(self._project_manager.source_state.selected_folders or [])
        self._current_warnings = self._compute_root_warnings(root_path)
        self._set_root_warning(self._current_warnings)
        if self._project_manager:
            self._project_manager.update_source_state(warnings=self._current_warnings)

        root_label = root_path.name or root_path.as_posix()
        root_item = QTreeWidgetItem([root_label])
        root_item.setData(0, Qt.UserRole, root_path.as_posix())
        self._source_tree.addTopLevelItem(root_item)

        if not selected:
            placeholder = QTreeWidgetItem(["No folders were selected during project setup."])
            placeholder.setFlags(Qt.NoItemFlags)
            root_item.addChild(placeholder)
        else:
            processed_dirs: set[Path] = set()
            for relative in selected:
                directory = (root_path / relative).resolve()
                if not directory.exists():
                    continue
                container = self._ensure_tree_path(root_item, root_path, relative)
                if directory.is_dir() and directory not in processed_dirs:
                    self._populate_directory_contents(container, directory, processed_dirs)
        self._source_tree.expandItem(root_item)

        if self._feature_flags.summary_groups_enabled:
            self._populate_group_source_tree()

    def _ensure_tree_path(self, root_item: QTreeWidgetItem, root_path: Path, relative_path: str) -> QTreeWidgetItem:
        current_item = root_item
        cumulative = Path()
        for part in Path(relative_path).parts:
            cumulative = cumulative / part
            child = self._find_child(current_item, part)
            if child is None:
                child = QTreeWidgetItem([part])
                child.setData(0, Qt.UserRole, (root_path / cumulative).resolve().as_posix())
                current_item.addChild(child)
            current_item = child
        return current_item

    def _populate_directory_contents(
        self,
        parent_item: QTreeWidgetItem,
        directory: Path,
        processed: set[Path],
    ) -> None:
        directory = directory.resolve()
        if directory in processed:
            return
        processed.add(directory)

        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda entry: (not entry.is_dir(), entry.name.lower()),
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.debug("Failed to enumerate %s: %s", directory, exc)
            return

        for entry in entries:
            child = self._find_child(parent_item, entry.name)
            if child is None:
                child = QTreeWidgetItem([entry.name])
                child.setData(0, Qt.UserRole, entry.resolve().as_posix())
                parent_item.addChild(child)
            if entry.is_dir():
                self._populate_directory_contents(child, entry, processed)

    def _iter_directories(self, root_path: Path) -> List[str]:
        results: List[str] = []
        for path in root_path.rglob("*"):
            if path.is_dir():
                try:
                    rel = path.relative_to(root_path).as_posix()
                except ValueError:
                    continue
                results.append(rel)
        return results

    def _populate_group_source_tree(self) -> None:
        if not self._feature_flags.summary_groups_enabled or self._group_source_tree is None:
            return
        self._group_source_tree.clear()

        if not self._project_manager:
            placeholder = QTreeWidgetItem(["Open a project to view folders."])
            placeholder.setFlags(Qt.NoItemFlags)
            self._group_source_tree.addTopLevelItem(placeholder)
            return

        root_path = self._resolve_source_root()
        if not root_path or not root_path.exists():
            placeholder = QTreeWidgetItem(["Source folder not set."])
            placeholder.setFlags(Qt.NoItemFlags)
            self._group_source_tree.addTopLevelItem(placeholder)
            return

        directories = sorted(self._iter_directories(root_path))
        if not directories:
            placeholder = QTreeWidgetItem(["No subfolders available."])
            placeholder.setFlags(Qt.NoItemFlags)
            self._group_source_tree.addTopLevelItem(placeholder)
            return

        self._group_source_tree.setUpdatesEnabled(False)
        for relative_path in directories:
            parts = relative_path.split("/")
            parent = self._group_source_tree.invisibleRootItem()
            path_so_far: List[str] = []
            for part in parts:
                path_so_far.append(part)
                rel_key = "/".join(path_so_far)
                child = self._find_child(parent, part)
                if child is None:
                    child = QTreeWidgetItem([part])
                    parent.addChild(child)
                parent = child
        self._group_source_tree.expandAll()
        self._group_source_tree.setUpdatesEnabled(True)

    def _find_child(self, parent: QTreeWidgetItem, name: str) -> Optional[QTreeWidgetItem]:
        for index in range(parent.childCount()):
            child = parent.child(index)
            if child.text(0) == name:
                return child
        return None

    def _collect_selected_folders(self) -> List[str]:
        selected: List[str] = []
        root = self._source_tree.invisibleRootItem()
        stack = [root]
        while stack:
            current = stack.pop()
            for index in range(current.childCount()):
                child = current.child(index)
                stack.append(child)
                if child.checkState(0) == Qt.Checked:
                    rel = child.data(0, Qt.UserRole)
                    if rel:
                        selected.append(str(rel))
        selected.sort()
        return selected

    def _collect_conversion_jobs(self) -> List[ConversionJob]:
        if not self._project_manager:
            return []
        jobs = build_conversion_jobs(self._project_manager)
        if not jobs:
            return []
        return [job for job in jobs if job.source_path not in self._inflight_sources]

    def _set_root_warning(self, warnings: List[str]) -> None:
        if warnings:
            self._root_warning_label.setText("\n".join(warnings))
            self._root_warning_label.show()
        else:
            self._root_warning_label.clear()
            self._root_warning_label.hide()

    def _compute_root_warnings(self, root_path: Path) -> List[str]:
        warnings: List[str] = []
        has_root_files = any(child.is_file() for child in root_path.iterdir())
        if has_root_files:
            warnings.append(
                "Files in the source root will be skipped. Move them into subfolders so they can be processed."
            )
        selected = self._project_manager.source_state.selected_folders if self._project_manager else []
        if not selected:
            warnings.append("Select at least one folder to include in scanning.")
        return warnings

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
        if self._extract_highlights_button:
            self._extract_highlights_button.setEnabled(False)

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
        self._project_manager.update_source_state(last_scan=timestamp, warnings=self._current_warnings)
        self._update_last_scan_label()

        self._conversion_running = False
        self._rescan_button.setEnabled(True)
        if self._extract_highlights_button and not self._highlight_running:
            self._extract_highlights_button.setEnabled(True)

        self._refresh_file_tracker()
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
    def _highlight_key(self) -> str:
        return "highlights:run"

    def _trigger_highlight_extraction(self) -> None:
        if not self._project_manager:
            return
        if self._highlight_running:
            QMessageBox.information(
                self,
                "Highlights",
                "Highlight extraction is already in progress.",
            )
            return

        jobs = self._project_manager.build_highlight_jobs()
        if not jobs:
            QMessageBox.information(
                self,
                "Highlights",
                "No converted PDFs are ready for highlight extraction.",
            )
            return

        self._start_highlight_worker(jobs)

    def _start_highlight_worker(self, jobs) -> None:
        self._highlight_running = True
        self._highlight_total = len(jobs)
        self._highlight_errors = []
        self._counts_label.setText(f"Extracting highlights (0/{self._highlight_total})…")
        if self._extract_highlights_button:
            self._extract_highlights_button.setEnabled(False)
        worker = HighlightWorker(jobs)
        worker.progress.connect(self._on_highlight_progress)
        worker.file_failed.connect(self._on_highlight_failed)
        worker.finished.connect(
            lambda success, failed, w=worker: self._on_highlight_finished(w, success, failed)
        )
        self._workers.start(self._highlight_key(), worker)

    def _on_highlight_progress(self, processed: int, total: int, relative_path: str) -> None:
        self._counts_label.setText(
            f"Extracting highlights ({processed}/{total})… {relative_path}"
        )

    def _on_highlight_failed(self, source_path: str, error: str) -> None:
        self._highlight_errors.append(f"{Path(source_path).name}: {error}")

    def _on_highlight_finished(self, worker: HighlightWorker, successes: int, failures: int) -> None:
        stored = self._workers.pop(self._highlight_key())
        # Always attempt to delete the actual worker and any stored reference safely
        if worker and isValid(worker):
            worker.deleteLater()
        if stored and stored is not worker and isValid(stored):
            stored.deleteLater()

        self._highlight_running = False
        if self._extract_highlights_button and not self._conversion_running:
            self._extract_highlights_button.setEnabled(True)

        self._refresh_file_tracker()

        if failures:
            message = "\n".join(self._highlight_errors) or "Unknown errors"
            QMessageBox.warning(
                self,
                "Highlight Extraction Issues",
                "Some highlights could not be extracted:\n\n" + message,
            )

    def _refresh_summary_groups(self) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if not self._summary_table or not self._summary_empty_label or not self._summary_info_label:
            return
        if not self._project_manager:
            self._summary_table.setRowCount(0)
            self._summary_empty_label.show()
            return

        groups = self._project_manager.list_summary_groups()
        total_docs = 0
        group_metrics_map: Dict[str, WorkspaceGroupMetrics] = {}
        if self._workspace_metrics:
            total_docs = self._workspace_metrics.dashboard.imported_total
            group_metrics_map = self._workspace_metrics.groups
        self._prune_running_groups({group.group_id for group in groups})

        self._summary_table.setRowCount(0)
        if not groups:
            self._summary_empty_label.show()
            self._summary_info_label.setText("No bulk analysis groups yet.")
            return

        self._summary_empty_label.hide()
        self._summary_info_label.setText(f"{len(groups)} bulk analysis group(s)")

        self._summary_table.setRowCount(len(groups))
        for row, group in enumerate(groups):
            group_metrics = group_metrics_map.get(group.group_id)
            self._populate_group_row(row, group, total_docs, group_metrics)

    def _populate_group_row(
        self,
        row: int,
        group: SummaryGroup,
        total_docs: int,
        metrics: WorkspaceGroupMetrics | None,
    ) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if not self._summary_table:
            return
        description = group.description or ""
        name_item = QTableWidgetItem(group.name)
        name_item.setData(Qt.UserRole, group.group_id)
        name_item.setToolTip(description)
        self._summary_table.setItem(row, 0, name_item)

        op_type = getattr(metrics, "operation", "per_document") if metrics else "per_document"
        converted_count = metrics.converted_count if metrics else 0
        if op_type == "combined":
            input_count = getattr(metrics, "combined_input_count", 0)
            coverage_text = f"Combined – Inputs: {input_count}"
        else:
            coverage_text = f"{converted_count} of {total_docs}" if total_docs else str(converted_count)
        files_item = QTableWidgetItem(coverage_text)
        files_item.setTextAlignment(Qt.AlignCenter)
        self._summary_table.setItem(row, 1, files_item)

        updated_text = group.updated_at.strftime("%Y-%m-%d %H:%M")
        updated_item = QTableWidgetItem(updated_text)
        updated_item.setTextAlignment(Qt.AlignCenter)
        self._summary_table.setItem(row, 2, updated_item)

        if group.group_id in self._running_groups:
            if group.group_id in self._cancelling_groups:
                status_text = "Cancelling…"
            else:
                progress = self._bulk_progress.get(group.group_id)
                if progress and progress[1]:
                    status_text = f"Running ({progress[0]}/{progress[1]})"
                else:
                    status_text = "Running…"
        else:
            if op_type == "combined":
                if metrics and getattr(metrics, "combined_input_count", 0) == 0:
                    status_text = "No inputs"
                elif metrics and getattr(metrics, "combined_is_stale", False):
                    status_text = "Stale"
                else:
                    status_text = "Ready"
            else:
                if not converted_count:
                    status_text = "No converted files"
                elif metrics and metrics.pending_bulk_analysis:
                    status_text = f"Pending bulk ({metrics.pending_bulk_analysis})"
                else:
                    status_text = "Ready"
        status_item = QTableWidgetItem(status_text)
        status_item.setTextAlignment(Qt.AlignCenter)
        self._summary_table.setItem(row, 3, status_item)

        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)

        if op_type == "combined":
            run_button = QPushButton("Run Combined")
            run_enabled = (metrics and getattr(metrics, "combined_input_count", 0) > 0) and group.group_id not in self._running_groups
            run_button.setEnabled(bool(run_enabled))
            run_button.clicked.connect(lambda _, g=group: self._start_combined_run(g))
        else:
            run_button = QPushButton("Run")
            run_button.setEnabled(converted_count > 0 and group.group_id not in self._running_groups)
            run_button.clicked.connect(lambda _, g=group: self._start_group_run(g))
        action_layout.addWidget(run_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.setEnabled(group.group_id in self._running_groups)
        cancel_button.clicked.connect(lambda _, g=group: self._cancel_group_run(g))
        action_layout.addWidget(cancel_button)

        if op_type == "combined":
            open_latest = QPushButton("Open Latest")
            open_latest.clicked.connect(lambda _, g=group: self._open_latest_combined(g))
            action_layout.addWidget(open_latest)
            open_button = QPushButton("Open Folder")
            open_button.clicked.connect(lambda _, g=group: self._open_group_folder(g))
            action_layout.addWidget(open_button)
        else:
            open_button = QPushButton("Open Folder")
            open_button.clicked.connect(lambda _, g=group: self._open_group_folder(g))
            action_layout.addWidget(open_button)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(lambda _, g=group: self._confirm_delete_group(g))
        action_layout.addWidget(delete_button)

        self._summary_table.setCellWidget(row, 4, action_widget)

        tooltip_parts = []
        if description:
            tooltip_parts.append(description)
        if group.directories:
            tooltip_parts.append("Directories: " + ", ".join(group.directories))
        extra_files = sorted(set(group.files))
        if extra_files:
            tooltip_parts.append("Files: " + ", ".join(extra_files))
        if metrics and metrics.converted_files:
            tooltip_parts.append(
                "Converted files (" + str(metrics.converted_count) + "): " + ", ".join(metrics.converted_files)
            )
        if tooltip_parts:
            name_item.setToolTip("\n".join(tooltip_parts))
            files_item.setToolTip("\n".join(tooltip_parts))
            status_item.setToolTip("\n".join(tooltip_parts))

    def _show_create_group_dialog(self) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if not self._project_manager or not self._project_manager.project_dir:
            return
        dialog = SummaryGroupDialog(self._project_manager.project_dir, self)
        if dialog.exec() == QDialog.Accepted:
            group = dialog.build_group()
            try:
                self._project_manager.save_summary_group(group)
            except Exception as exc:
                QMessageBox.critical(self, "Create Bulk Analysis Group Failed", str(exc))
            else:
                self.refresh()

    def _confirm_delete_group(self, group: SummaryGroup) -> None:
        if not self._feature_flags.summary_groups_enabled:
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
            if not self._project_manager.delete_summary_group(group.group_id):
                QMessageBox.warning(self, "Delete Failed", "Could not delete the bulk analysis group.")
            else:
                self._cancel_group_run(group)
                self.refresh()

    def _open_group_folder(self, group: SummaryGroup) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if not self._project_manager or not self._project_manager.project_dir:
            return
        folder = self._project_manager.project_dir / "bulk_analysis" / group.folder_name
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _open_latest_combined(self, group: SummaryGroup) -> None:
        if not self._feature_flags.summary_groups_enabled:
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

    def _start_group_run(self, group: SummaryGroup) -> None:
        if not self._feature_flags.summary_groups_enabled:
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

        files = sorted(group_metrics.converted_files) if group_metrics else []
        if not files:
            QMessageBox.warning(
                self,
                "No Converted Documents",
                "This group does not have any converted documents yet. Run conversion first.",
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
        )
        worker.progress.connect(lambda done, total, path, gid=group.group_id: self._on_bulk_progress(gid, done, total, path))
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
        if self._summary_info_label:
            self._summary_info_label.setText("Running bulk analysis…")
        self._refresh_summary_groups()
        self._workers.start(key, worker)

    def _start_combined_run(self, group: SummaryGroup) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if group.group_id in self._running_groups:
            QMessageBox.information(self, "Already Running", f"Combined operation for '{group.name}' is already in progress.")
            return
        if not self._project_manager or not self._project_manager.project_dir:
            QMessageBox.warning(self, "Missing Project", "The project directory is not available.")
            return
        worker = BulkReduceWorker(
            project_dir=self._project_manager.project_dir,
            group=group,
            metadata=self._project_manager.metadata,
        )
        gid = group.group_id
        key = f"combine:{gid}"
        self._running_groups.add(gid)
        self._bulk_progress[gid] = (0, 1)
        self._bulk_failures[gid] = []
        self._cancelling_groups.discard(gid)
        if self._summary_info_label:
            self._summary_info_label.setText("Running combined operation…")
        worker.progress.connect(lambda done, total, msg, g=gid: self._on_bulk_progress(g, done, total, msg))
        worker.file_failed.connect(lambda rel, err, g=gid: self._on_bulk_failed(g, rel, err))
        worker.log_message.connect(lambda message, g=gid: self._on_bulk_log(g, message))
        worker.finished.connect(lambda success, failed, w=worker, g=gid: self._on_bulk_finished(g, w, success, failed))
        self._workers.start(key, worker)

    def _cancel_group_run(self, group: SummaryGroup) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        key = self._bulk_key(group.group_id)
        worker = self._workers.get(key)
        if worker:
            worker.cancel()
            self._cancelling_groups.add(group.group_id)
            if self._summary_info_label:
                self._summary_info_label.setText("Cancelling bulk analysis…")
        else:
            self._bulk_progress.pop(group.group_id, None)
            self._bulk_failures.pop(group.group_id, None)
            self._cancelling_groups.discard(group.group_id)
            if self._summary_info_label:
                self._summary_info_label.setText("Bulk analysis cancelled.")
        self._refresh_summary_groups()

    def _on_bulk_progress(self, group_id: str, completed: int, total: int, relative_path: str) -> None:
        if group_id in self._cancelling_groups:
            return
        self._bulk_progress[group_id] = (completed, total)
        if self._summary_info_label:
            self._summary_info_label.setText(
                f"Running bulk analysis ({completed}/{total})… {relative_path}"
            )
        self._refresh_summary_groups()

    def _on_bulk_failed(self, group_id: str, relative_path: str, error: str) -> None:
        LOGGER.error("Bulk analysis failed for %s: %s", relative_path, error)
        self._bulk_failures.setdefault(group_id, []).append(f"{relative_path}: {error}")

    def _on_bulk_log(self, group_id: str, message: str) -> None:  # noqa: ARG002 - future use
        LOGGER.info("[BulkAnalysis][%s] %s", group_id, message)

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

        if self._summary_info_label:
            if was_cancelled:
                self._summary_info_label.setText("Bulk analysis cancelled.")
            elif failures:
                self._summary_info_label.setText(
                    f"Bulk analysis completed with {failures} error(s)."
                )
            else:
                self._summary_info_label.setText("Bulk analysis completed.")

        if errors:
            QMessageBox.warning(
                self,
                "Bulk Analysis Issues",
                "Some documents failed during bulk analysis:\n" + "\n".join(errors),
            )

        self._refresh_file_tracker()
        self._refresh_summary_groups()

    def _prune_running_groups(self, valid_ids: Optional[set[str]] = None) -> None:
        if not self._feature_flags.summary_groups_enabled:
            return
        if valid_ids is None:
            valid_ids = set()
            if self._project_manager:
                try:
                    valid_ids = {
                        group.group_id for group in self._project_manager.list_summary_groups()
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
