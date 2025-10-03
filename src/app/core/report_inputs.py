"""Shared constants for report generation inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

REPORT_CATEGORY_CONVERTED = "converted_documents"
REPORT_CATEGORY_BULK_MAP = "bulk_analysis_per_document"
REPORT_CATEGORY_BULK_COMBINED = "bulk_analysis_combined"
REPORT_CATEGORY_HIGHLIGHT_DOCUMENT = "highlight_document"
REPORT_CATEGORY_HIGHLIGHT_COLOR = "highlight_color"

CATEGORY_DISPLAY_NAMES = {
    REPORT_CATEGORY_CONVERTED: "Converted Documents",
    REPORT_CATEGORY_BULK_MAP: "Bulk Analysis Outputs",
    REPORT_CATEGORY_BULK_COMBINED: "Combined Outputs",
    REPORT_CATEGORY_HIGHLIGHT_DOCUMENT: "Highlights (By Document)",
    REPORT_CATEGORY_HIGHLIGHT_COLOR: "Highlights (By Color)",
}


@dataclass(slots=True)
class ReportInputDescriptor:
    """Description of a selectable report input."""

    category: str
    relative_path: str  # relative to project directory
    label: str
    description: Optional[str] = None

    def key(self) -> str:
        """Return a stable key for preference storage."""
        return f"{self.category}:{self.relative_path}"


def category_display_name(category: str) -> str:
    """Return a human-friendly display name for a category."""

    return CATEGORY_DISPLAY_NAMES.get(category, category.replace("_", " ").title())


__all__ = [
    "REPORT_CATEGORY_CONVERTED",
    "REPORT_CATEGORY_BULK_MAP",
    "REPORT_CATEGORY_BULK_COMBINED",
    "REPORT_CATEGORY_HIGHLIGHT_DOCUMENT",
    "REPORT_CATEGORY_HIGHLIGHT_COLOR",
    "ReportInputDescriptor",
    "category_display_name",
]
