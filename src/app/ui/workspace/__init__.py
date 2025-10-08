"""Workspace UI package for decomposed dashboard tabs."""

from .shell import WorkspaceShell
from .documents_tab import DocumentsTab
from .bulk_tab import BulkAnalysisTab

__all__ = ["WorkspaceShell", "DocumentsTab", "BulkAnalysisTab"]
