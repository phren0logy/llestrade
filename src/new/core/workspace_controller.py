"""Minimal workspace controller for the dashboard scaffold."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .project_manager import ProjectManager
from src.new.stages.project_workspace import ProjectWorkspace


class WorkspaceController(QObject):
    """Create and manage the dashboard workspace view."""

    workspace_created = Signal(ProjectWorkspace)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._workspace: ProjectWorkspace | None = None

    def create_workspace(self, project_manager: ProjectManager) -> ProjectWorkspace:
        """Instantiate a workspace for the provided project manager."""
        self._workspace = ProjectWorkspace(project_manager)
        self.workspace_created.emit(self._workspace)
        return self._workspace

    def current_workspace(self) -> ProjectWorkspace | None:
        """Return the currently active workspace widget, if any."""
        return self._workspace
