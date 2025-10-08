"""Workspace UI package for decomposed dashboard tabs."""

from .bulk_tab import BulkAnalysisTab
from .documents_tab import DocumentsTab
from .highlights_tab import HighlightsTab
from .reports_tab import ReportsTab
from .shell import WorkspaceShell

__all__ = ["BulkAnalysisTab", "DocumentsTab", "HighlightsTab", "ReportsTab", "WorkspaceShell"]
