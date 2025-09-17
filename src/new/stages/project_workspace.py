"""Placeholder dashboard workspace for the new UI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from src.new.core.project_manager import ProjectManager


class ProjectWorkspace(QWidget):
    """Minimal tabbed workspace used during the dashboard refactor."""

    def __init__(self, project_manager: Optional[ProjectManager] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._project_manager: Optional[ProjectManager] = None
        self._project_path_label = QLabel()
        self._build_ui()
        if project_manager:
            self.set_project(project_manager)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_documents_tab(), "Documents")
        self._tabs.addTab(self._build_placeholder_tab("Summary Groups"), "Summary Groups")
        self._tabs.addTab(self._build_placeholder_tab("Progress"), "Progress")

        layout.addWidget(self._project_path_label)
        layout.addWidget(self._tabs)

    def _build_documents_tab(self) -> QWidget:
        widget = QWidget()
        tab_layout = QVBoxLayout(widget)
        tab_layout.setSpacing(8)

        self._counts_label = QLabel("Scan pending…")
        self._counts_label.setStyleSheet("font-weight: bold;")
        tab_layout.addWidget(self._counts_label)

        self._missing_processed_label = QLabel("Processed missing: —")
        self._missing_summaries_label = QLabel("Summaries missing: —")

        for label in (self._missing_processed_label, self._missing_summaries_label):
            label.setWordWrap(True)
            tab_layout.addWidget(label)

        tab_layout.addStretch()
        return widget

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
        self._refresh_file_tracker()

    def project_manager(self) -> Optional[ProjectManager]:
        """Return the current project manager if one has been set."""
        return self._project_manager

    def refresh(self) -> None:
        """Manual refresh hook for future toolbar integrations."""
        self._refresh_file_tracker()

    def _refresh_file_tracker(self) -> None:
        if not self._project_manager:
            return
        try:
            tracker = self._project_manager.get_file_tracker()
            snapshot = tracker.scan()
        except Exception as exc:
            self._counts_label.setText("Scan failed")
            self._missing_processed_label.setText(str(exc))
            self._missing_summaries_label.setText("")
            return

        self._counts_label.setText(
            (
                f"Imported: {snapshot.imported_count} | "
                f"Processed: {snapshot.processed_count} | "
                f"Summaries: {snapshot.summaries_count}"
            )
        )

        processed_missing = snapshot.missing.get("processed_missing", [])
        summaries_missing = snapshot.missing.get("summaries_missing", [])

        self._missing_processed_label.setText(
            "Processed missing: " + (", ".join(processed_missing) if processed_missing else "None")
        )
        self._missing_summaries_label.setText(
            "Summaries missing: " + (", ".join(summaries_missing) if summaries_missing else "None")
        )
