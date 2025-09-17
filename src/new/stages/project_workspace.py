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
        self._tabs.addTab(self._build_info_tab(), "Documents")
        self._tabs.addTab(self._build_placeholder_tab("Summary Groups"), "Summary Groups")
        self._tabs.addTab(self._build_placeholder_tab("Progress"), "Progress")

        layout.addWidget(self._project_path_label)
        layout.addWidget(self._tabs)

    def _build_info_tab(self) -> QWidget:
        widget = QWidget()
        tab_layout = QVBoxLayout(widget)
        tab_layout.addWidget(QLabel("Document management tools are coming soon."))
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

    def project_manager(self) -> Optional[ProjectManager]:
        """Return the current project manager if one has been set."""
        return self._project_manager
