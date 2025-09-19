"""Top-level package for the dashboard application."""

from .core.secure_settings import SecureSettings
from .core.project_manager import ProjectManager, ProjectMetadata, ProjectCosts, WorkflowState
from .core.workspace_controller import WorkspaceController
from .core.summary_groups import SummaryGroup
from .core.feature_flags import FeatureFlags
from .core.file_tracker import DashboardMetrics, WorkspaceMetrics, WorkspaceGroupMetrics
from .main_window import SimplifiedMainWindow, main as run

__all__ = [
    "SecureSettings",
    "ProjectManager",
    "ProjectMetadata",
    "ProjectCosts",
    "WorkflowState",
    "WorkspaceController",
    "SummaryGroup",
    "FeatureFlags",
    "DashboardMetrics",
    "WorkspaceMetrics",
    "WorkspaceGroupMetrics",
    "SimplifiedMainWindow",
    "run",
]
