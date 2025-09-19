"""Minimal workspace controller for the dashboard scaffold."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .feature_flags import FeatureFlags
from .project_manager import ProjectManager
from src.app.ui.stages.project_workspace import ProjectWorkspace


class WorkspaceController(QObject):
    """Create and manage the dashboard workspace view."""

    workspace_created = Signal(ProjectWorkspace)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        feature_flags: FeatureFlags | None = None,
    ) -> None:
        super().__init__(parent)
        self._workspace: ProjectWorkspace | None = None
        self._feature_flags = feature_flags or FeatureFlags()

    def create_workspace(self, project_manager: ProjectManager) -> ProjectWorkspace:
        """Instantiate a workspace for the provided project manager."""
        self._workspace = ProjectWorkspace(project_manager, feature_flags=self._feature_flags)
        self.workspace_created.emit(self._workspace)
        return self._workspace

    def current_workspace(self) -> ProjectWorkspace | None:
        """Return the currently active workspace widget, if any."""
        return self._workspace
