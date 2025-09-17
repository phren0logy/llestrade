"""Dashboard workspace for the new UI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWidgets import QHeaderView

from src.new.core.project_manager import ProjectManager
from src.new.core.summary_groups import SummaryGroup
from src.new.dialogs.summary_group_dialog import SummaryGroupDialog


class ProjectWorkspace(QWidget):
    """Dashboard workspace showing documents and summary groups."""

    def __init__(self, project_manager: Optional[ProjectManager] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._project_manager: Optional[ProjectManager] = None
        self._project_path_label = QLabel()
        self._processed_total = 0
        self._imported_total = 0
        self._latest_snapshot = None

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

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        self._counts_label = QLabel("Scan pending…")
        self._counts_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(self._counts_label)
        header_layout.addStretch()
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        header_layout.addWidget(refresh_button)
        tab_layout.addLayout(header_layout)

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
        self.refresh()

    def project_manager(self) -> Optional[ProjectManager]:
        return self._project_manager

    def refresh(self) -> None:
        self._refresh_file_tracker()
        self._refresh_summary_groups()

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

        files_count = len(group.files)
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
