"""Business-logic controller for the workspace Documents tab (scaffolding)."""

from __future__ import annotations

from typing import Optional

from src.app.core.project_manager import ProjectManager


class DocumentsController:
    """Placeholder controller exposing the methods the tab expects."""

    def __init__(self) -> None:
        self._project_manager: Optional[ProjectManager] = None

    def set_project(self, project_manager: Optional[ProjectManager]) -> None:
        """Store the active project manager."""

        self._project_manager = project_manager

    def shutdown(self) -> None:
        """Hook for releasing resources (none yet)."""

        self._project_manager = None

