"""Placeholder set utilities for project configuration and prompt execution."""

from .models import PlaceholderEntry, ProjectPlaceholders
from .parser import parse_placeholder_markdown, parse_placeholder_file
from .registry import PlaceholderSetDescriptor, PlaceholderSetRegistry
from .system import SYSTEM_PLACEHOLDERS, system_placeholder_map
from .analyzer import (
    PlaceholderAnalysis,
    PlaceholderUsage,
    analyse_prompts,
    build_preview_styles,
    highlight_placeholders_raw,
    render_preview_html,
)

__all__ = [
    "PlaceholderEntry",
    "ProjectPlaceholders",
    "PlaceholderSetDescriptor",
    "PlaceholderSetRegistry",
    "parse_placeholder_markdown",
    "parse_placeholder_file",
    "SYSTEM_PLACEHOLDERS",
    "system_placeholder_map",
    "PlaceholderAnalysis",
    "PlaceholderUsage",
    "analyse_prompts",
    "build_preview_styles",
    "highlight_placeholders_raw",
    "render_preview_html",
]
