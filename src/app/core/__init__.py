"""
Core components for the new simplified UI.
"""

from .secure_settings import SecureSettings
from .project_manager import ProjectManager, ProjectMetadata, ProjectCosts, WorkflowState
from .workspace_controller import WorkspaceController
from .bulk_analysis_groups import BulkAnalysisGroup
from .feature_flags import FeatureFlags
from .file_tracker import DashboardMetrics, WorkspaceMetrics, WorkspaceGroupMetrics, build_workspace_metrics

__all__ = [
    'SecureSettings',
    'ProjectManager',
    'ProjectMetadata', 
    'ProjectCosts',
    'WorkflowState',
    'WorkspaceController',
    'BulkAnalysisGroup',
    'FeatureFlags',
    'DashboardMetrics',
    'WorkspaceMetrics',
    'WorkspaceGroupMetrics',
    'build_workspace_metrics',
]
