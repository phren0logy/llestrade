"""Controllers for workspace tab business logic."""

from .bulk import BulkAnalysisController
from .documents import DocumentsController
from .highlights import HighlightsController
from .reports import ReportsController

__all__ = [
    "BulkAnalysisController",
    "DocumentsController",
    "HighlightsController",
    "ReportsController",
]
