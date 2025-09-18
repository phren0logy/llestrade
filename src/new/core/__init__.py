"""
Core components for the new simplified UI.
"""

from .secure_settings import SecureSettings
from .project_manager import ProjectManager, ProjectMetadata, ProjectCosts, WorkflowState
from .workspace_controller import WorkspaceController
from .summary_groups import SummaryGroup
from .feature_flags import FeatureFlags
from .file_tracker import DashboardMetrics

__all__ = [
    'SecureSettings',
    'ProjectManager',
    'ProjectMetadata', 
    'ProjectCosts',
    'WorkflowState',
    'WorkspaceController',
    'SummaryGroup',
    'FeatureFlags',
    'DashboardMetrics'
]
