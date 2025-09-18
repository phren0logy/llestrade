"""Dashboard workspace for the new UI."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Sequence

from PySide6.QtCore import Qt, QThreadPool, QUrl
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

from src.new.core.conversion_manager import ConversionJob, build_conversion_jobs
from src.new.core.project_manager import ProjectManager
from src.new.core.summary_groups import SummaryGroup
from src.new.dialogs.summary_group_dialog import SummaryGroupDialog
from src.new.workers import ConversionWorker


class ProjectWorkspace(QWidget):
    """Dashboard workspace showing documents and summary groups."""

    def __init__(self, project_manager: Optional[ProjectManager] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._project_manager: Optional[ProjectManager] = None
        self._project_path_label = QLabel()
        self._processed_total = 0
        self._imported_total = 0
        self._latest_snapshot = None
        self._updating_tree = False
        self._current_warnings: List[str] = []
        self._thread_pool = QThreadPool.globalInstance()
        self._active_workers: List[ConversionWorker] = []
        self._inflight_sources: set[Path] = set()
        self._conversion_running = False
        self._conversion_total = 0

        self._build_ui()
        if project_manager:
            self.set_project(project_manager)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_documents_tab(), "Documents")
        self._tabs.addTab(self._build_summary_groups_tab(), "Summary Groups")
        self._tabs.addTab(self._build_placeholder_tab("Progress"), "Progress")

        layout.addWidget(self._project_path_label)
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
        select_button = QPushButton("Choose Folder…")
        select_button.clicked.connect(self._select_source_root)
        root_layout.addWidget(select_button)
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
        self._rescan_button = QPushButton("Re-scan")
        self._rescan_button.clicked.connect(lambda: self._trigger_conversion(auto_run=False))
        header_layout.addWidget(self._rescan_button)
        tab_layout.addLayout(header_layout)

        # Tree view for folder selection
        self._source_tree = QTreeWidget()
        self._source_tree.setHeaderHidden(True)
        self._source_tree.setSelectionMode(QAbstractItemView.NoSelection)
        self._source_tree.itemChanged.connect(self._on_tree_item_changed)
        tab_layout.addWidget(self._source_tree)

        self._root_warning_label = QLabel("")
        self._root_warning_label.setWordWrap(True)
        self._root_warning_label.setStyleSheet("color: #b26a00;")
        tab_layout.addWidget(self._root_warning_label)
        self._root_warning_label.hide()

        self._missing_processed_label = QLabel("Processed missing: —")
        self._missing_summaries_label = QLabel("Summaries missing: —")

        for label in (self._missing_processed_label, self._missing_summaries_label):
            label.setWordWrap(True)
            tab_layout.addWidget(label)

        tab_layout.addStretch()
        return widget

    def _build_summary_groups_tab(self) -> QWidget:
        self._summary_tab = QWidget()
        layout = QVBoxLayout(self._summary_tab)
        layout.setSpacing(8)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(QLabel("Manage summary groups to organise processed documents."))
        header_layout.addStretch()
        create_button = QPushButton("Create Group…")
        create_button.clicked.connect(self._show_create_group_dialog)
        header_layout.addWidget(create_button)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh_summary_groups)
        header_layout.addWidget(refresh_button)
        layout.addLayout(header_layout)

        self._summary_info_label = QLabel("No summary groups yet.")
        layout.addWidget(self._summary_info_label)

        self._summary_table = QTableWidget(0, 4)
        self._summary_table.setHorizontalHeaderLabels(["Group", "Files", "Updated", "Actions"])
        self._summary_table.verticalHeader().setVisible(False)
        self._summary_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._summary_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._summary_table.setSelectionMode(QAbstractItemView.NoSelection)
        header = self._summary_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addWidget(self._summary_table)

        self._summary_empty_label = QLabel("No summary groups created yet.")
        self._summary_empty_label.setAlignment(Qt.AlignCenter)
        self._summary_empty_label.setStyleSheet("color: #666; padding: 20px;")
        layout.addWidget(self._summary_empty_label)
        self._summary_empty_label.hide()

        return self._summary_tab

    def _build_placeholder_tab(self, title: str) -> QWidget:
        widget = QWidget()
        tab_layout = QVBoxLayout(widget)
        tab_layout.addWidget(QLabel(f"{title} dashboard is under construction."))
        tab_layout.addStretch()
        return widget

    def set_project(self, project_manager: ProjectManager) -> None:
        """Attach the workspace to a project manager."""
        self._project_manager = project_manager
        project_dir = project_manager.project_dir
        project_path = Path(project_dir).resolve() if project_dir else None
        self._project_path_label.setText(
            f"Active project: {project_path}" if project_path else "Active project: (unsaved)"
        )
        self._populate_source_tree()
        self._update_source_root_label()
        self._update_last_scan_label()
        self.refresh()

    def project_manager(self) -> Optional[ProjectManager]:
        return self._project_manager

    def refresh(self) -> None:
        self._populate_source_tree()
        self._update_source_root_label()
        self._update_last_scan_label()
        self._refresh_file_tracker()
        self._refresh_summary_groups()

    def begin_initial_conversion(self) -> None:
        """Trigger an initial scan/conversion after project creation."""
        self._trigger_conversion(auto_run=True)

    def _refresh_file_tracker(self) -> None:
        if not self._project_manager:
            return
        try:
            tracker = self._project_manager.get_file_tracker()
            snapshot = tracker.scan()
            self._latest_snapshot = snapshot
            self._imported_total = snapshot.imported_count
            self._processed_total = snapshot.processed_count
        except Exception as exc:
            self._counts_label.setText("Scan failed")
            self._missing_processed_label.setText(str(exc))
            self._missing_summaries_label.setText("")
            return

        imported = snapshot.imported_count
        processed = snapshot.processed_count
        summaries = snapshot.summaries_count

        if imported:
            counts_text = (
                f"Imported: {imported} | "
                f"Processed: {processed} of {imported} | "
                f"Summaries: {summaries} of {imported}"
            )
        else:
            counts_text = (
                f"Imported: {imported} | "
                f"Processed: {processed} | "
                f"Summaries: {summaries}"
            )
        self._counts_label.setText(counts_text)

        processed_missing = snapshot.missing.get("processed_missing", [])
        summaries_missing = snapshot.missing.get("summaries_missing", [])

        self._missing_processed_label.setText(
            "Processed missing: " + (", ".join(processed_missing) if processed_missing else "None")
        )
        self._missing_summaries_label.setText(
            "Summaries missing: " + (", ".join(summaries_missing) if summaries_missing else "None")
        )

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
        self._project_manager.update_source_state(root=relative, selected_folders=[], warnings=[])
        self._populate_source_tree()
        self._update_source_root_label()
        self._update_last_scan_label()

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
        last_scan = self._project_manager.source_state.last_scan
        if not last_scan:
            self._last_scan_label.setText("Last scan: never")
            return
        try:
            parsed = datetime.fromisoformat(last_scan)
            display = parsed.strftime("Last scan: %Y-%m-%d %H:%M")
        except ValueError:
            display = f"Last scan: {last_scan}"
        self._last_scan_label.setText(display)

    def _populate_source_tree(self) -> None:
        if not hasattr(self, "_source_tree"):
            return
        self._updating_tree = True
        self._source_tree.clear()
        self._updating_tree = False

        if not self._project_manager:
            self._source_tree.setDisabled(True)
            self._set_root_warning([])
            return

        root_path = self._resolve_source_root()
        if not root_path or not root_path.exists():
            self._source_tree.setDisabled(True)
            warning = ["Select a source folder to begin tracking documents."]
            self._set_root_warning(warning)
            if self._project_manager:
                self._project_manager.update_source_state(warnings=warning)
            return

        self._source_tree.setDisabled(False)
        state = self._project_manager.source_state
        selected = set(state.selected_folders or [])
        auto_select = not selected

        directories = sorted(self._iter_directories(root_path))
        self._updating_tree = True
        for relative_path in directories:
            parts = relative_path.split("/")
            parent = self._source_tree.invisibleRootItem()
            path_so_far = []
            for index, part in enumerate(parts):
                path_so_far.append(part)
                rel_key = "/".join(path_so_far)
                child = self._find_child(parent, part)
                if child is None:
                    child = QTreeWidgetItem([part])
                    child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                    child.setData(0, Qt.UserRole, rel_key)
                    if auto_select or rel_key in selected:
                        child.setCheckState(0, Qt.Checked)
                    else:
                        child.setCheckState(0, Qt.Unchecked)
                    parent.addChild(child)
                parent = child
            if not auto_select:
                parent.setCheckState(0, Qt.Checked if relative_path in selected else Qt.Unchecked)
        if not auto_select:
            for idx in range(self._source_tree.topLevelItemCount()):
                self._update_parent_checkstate(self._source_tree.topLevelItem(idx))
        self._updating_tree = False

        if auto_select:
            selected_list = self._collect_selected_folders()
            self._project_manager.update_source_state(selected_folders=selected_list)

        self._current_warnings = self._compute_root_warnings(root_path)
        self._set_root_warning(self._current_warnings)
        if self._project_manager:
            self._project_manager.update_source_state(warnings=self._current_warnings)
        self._update_source_root_label()

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

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating_tree or column != 0:
            return
        self._updating_tree = True
        state = item.checkState(0)
        # Propagate to children
        def cascade(target: QTreeWidgetItem, value: Qt.CheckState) -> None:
            for idx in range(target.childCount()):
                child = target.child(idx)
                child.setCheckState(0, value)
                cascade(child, value)

        cascade(item, state)
        self._update_parent_checkstate(item.parent())
        self._updating_tree = False

        selected = self._collect_selected_folders()
        if self._project_manager:
            self._project_manager.update_source_state(selected_folders=selected)
        root_path = self._resolve_source_root()
        if root_path:
            self._current_warnings = self._compute_root_warnings(root_path)
            self._set_root_warning(self._current_warnings)

    def _update_parent_checkstate(self, parent: Optional[QTreeWidgetItem]) -> None:
        while parent is not None and parent is not self._source_tree.invisibleRootItem():
            checked = 0
            unchecked = 0
            for idx in range(parent.childCount()):
                state = parent.child(idx).checkState(0)
                if state == Qt.Checked:
                    checked += 1
                elif state == Qt.Unchecked:
                    unchecked += 1
            if checked and unchecked:
                parent.setCheckState(0, Qt.PartiallyChecked)
            elif checked and not unchecked:
                parent.setCheckState(0, Qt.Checked)
            else:
                parent.setCheckState(0, Qt.Unchecked)
            parent = parent.parent()

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
        if not self._collect_selected_folders():
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

        self._inflight_sources.update(job.source_path for job in jobs)

        worker = ConversionWorker(jobs, helper=self._project_manager.conversion_settings.helper)
        worker.progress.connect(self._on_conversion_progress)
        worker.file_failed.connect(self._on_conversion_failed)
        worker.finished.connect(lambda success, failed, w=worker, js=jobs: self._on_conversion_finished(w, js, success, failed))

        self._active_workers.append(worker)
        self._thread_pool.start(worker)

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
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        for job in jobs:
            self._inflight_sources.discard(job.source_path)

        timestamp = datetime.utcnow().isoformat()
        self._project_manager.update_source_state(last_scan=timestamp, warnings=self._current_warnings)
        self._update_last_scan_label()

        self._conversion_running = False
        self._rescan_button.setEnabled(True)

        self._refresh_file_tracker()
        if failures:
            error_text = "\n".join(self._conversion_errors) or "Unknown errors"
            QMessageBox.warning(
                self,
                "Conversion Issues",
                "Some documents failed to convert:\n\n" + error_text,
            )

    def _refresh_summary_groups(self) -> None:
        if not self._project_manager:
            self._summary_table.setRowCount(0)
            self._summary_empty_label.show()
            return

        groups = self._project_manager.list_summary_groups()
        total_docs = self._processed_total or self._imported_total or 0

        self._summary_table.setRowCount(0)
        if not groups:
            self._summary_empty_label.show()
            self._summary_info_label.setText("No summary groups yet.")
            return

        self._summary_empty_label.hide()
        self._summary_info_label.setText(f"{len(groups)} summary group(s)")

        self._summary_table.setRowCount(len(groups))
        for row, group in enumerate(groups):
            self._populate_group_row(row, group, total_docs)

    def _populate_group_row(self, row: int, group: SummaryGroup, total_docs: int) -> None:
        description = group.description or ""
        name_item = QTableWidgetItem(group.name)
        name_item.setToolTip(description)
        self._summary_table.setItem(row, 0, name_item)

        resolved_files = self._resolve_group_files(group)
        files_count = len(resolved_files)
        total = total_docs if total_docs else max(files_count, 1)
        files_item = QTableWidgetItem(f"{files_count} of {total}")
        files_item.setTextAlignment(Qt.AlignCenter)
        self._summary_table.setItem(row, 1, files_item)

        updated_text = group.updated_at.strftime("%Y-%m-%d %H:%M")
        updated_item = QTableWidgetItem(updated_text)
        updated_item.setTextAlignment(Qt.AlignCenter)
        self._summary_table.setItem(row, 2, updated_item)

        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)

        open_button = QPushButton("Open Folder")
        open_button.clicked.connect(lambda _, g=group: self._open_group_folder(g))
        action_layout.addWidget(open_button)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(lambda _, g=group: self._confirm_delete_group(g))
        action_layout.addWidget(delete_button)

        self._summary_table.setCellWidget(row, 3, action_widget)

        tooltip_parts = []
        if description:
            tooltip_parts.append(description)
        if group.directories:
            tooltip_parts.append("Directories: " + ", ".join(group.directories))
        extra_files = sorted(set(group.files))
        if extra_files:
            tooltip_parts.append("Files: " + ", ".join(extra_files))
        if tooltip_parts:
            name_item.setToolTip("\n".join(tooltip_parts))
            files_item.setToolTip("\n".join(tooltip_parts))

    def _show_create_group_dialog(self) -> None:
        if not self._project_manager or not self._project_manager.project_dir:
            return
        dialog = SummaryGroupDialog(self._project_manager.project_dir, self)
        if dialog.exec() == QDialog.Accepted:
            group = dialog.build_group()
            try:
                self._project_manager.save_summary_group(group)
            except Exception as exc:
                QMessageBox.critical(self, "Create Summary Group Failed", str(exc))
            else:
                self.refresh()

    def _confirm_delete_group(self, group: SummaryGroup) -> None:
        if not self._project_manager:
            return
        message = (
            f"Delete summary group '{group.name}'?\n\n"
            "All generated summaries stored in this group will be deleted."
        )
        reply = QMessageBox.question(
            self,
            "Delete Summary Group",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if not self._project_manager.delete_summary_group(group.group_id):
                QMessageBox.warning(self, "Delete Failed", "Could not delete the summary group.")
            else:
                self.refresh()

    def _open_group_folder(self, group: SummaryGroup) -> None:
        if not self._project_manager or not self._project_manager.project_dir:
            return
        folder = self._project_manager.project_dir / "summaries" / group.folder_name
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _resolve_group_files(self, group: SummaryGroup) -> set[str]:
        processed = set()
        if self._latest_snapshot:
            processed = set(self._latest_snapshot.files.get("processed", []))

        selected = {path for path in group.files if path in processed or not processed}

        for directory in group.directories:
            normalised = directory.strip("/")
            if not normalised:
                selected.update(processed)
                continue
            prefix = normalised + "/"
            for path in processed:
                if path == normalised or path.startswith(prefix):
                    selected.add(path)
        return selected
