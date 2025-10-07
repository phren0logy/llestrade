"""Business-logic controller scaffold for the workspace Documents tab."""

from __future__ import annotations

from typing import Optional

from src.app.core.project_manager import ProjectManager


class DocumentsController:
    """Placeholder controller exposing hooks for future refactors."""

    def __init__(self) -> None:
        self._project_manager: Optional[ProjectManager] = None

    def set_project(self, project_manager: Optional[ProjectManager]) -> None:
        """Record the current project manager reference."""

        self._project_manager = project_manager

    def shutdown(self) -> None:
        """Release references when the workspace is torn down."""

        self._project_manager = None

