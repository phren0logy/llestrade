"""Registry for document conversion helpers used by the dashboard pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class HelperOption:
    """Metadata describing a configurable option for a conversion helper."""

    key: str
    label: str
    option_type: str  # e.g. "checkbox", "select"
    default: Any = False
    tooltip: str = ""
    choices: Optional[List[str]] = None  # used for select options


@dataclass(frozen=True)
class ConversionHelper:
    """Represents a conversion helper implementation."""

    helper_id: str
    name: str
    description: str
    supported_extensions: Iterable[str]
    options: Iterable[HelperOption] = field(default_factory=list)
    executor: Optional[Callable[..., None]] = None  # injected later by workers


class HelperRegistry:
    """In-memory registry of available conversion helpers."""

    def __init__(self) -> None:
        self._helpers: Dict[str, ConversionHelper] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(self, helper: ConversionHelper) -> None:
        self._helpers[helper.helper_id] = helper

    def get(self, helper_id: str) -> Optional[ConversionHelper]:
        return self._helpers.get(helper_id)

    def list_helpers(self) -> List[ConversionHelper]:
        return list(self._helpers.values())

    def default_helper(self) -> ConversionHelper:
        helper = self.get("default")
        if helper is None:
            raise KeyError("Default conversion helper is not registered")
        return helper


# ----------------------------------------------------------------------
# Default registry instance with built-in helpers
# ----------------------------------------------------------------------

_registry = HelperRegistry()

_registry.register(
    ConversionHelper(
        helper_id="default",
        name="Local extractor (recommended)",
        description=(
            "Uses built-in converters for PDFs, Word documents, text, and markdown files. "
            "Generates Markdown with YAML front matter for PDFs."
        ),
        supported_extensions=[".pdf", ".doc", ".docx", ".txt", ".md", ".markdown"],
        options=[
            HelperOption(
                key="include_pdf_front_matter",
                label="Include PDF metadata header",
                option_type="checkbox",
                default=True,
                tooltip="Keeps title/source metadata in converted PDFs.",
            ),
        ],
    )
)

_registry.register(
    ConversionHelper(
        helper_id="text_only",
        name="Text-only output",
        description= (
            "Produces plain markdown without YAML headers. Useful when downstream workflows "
            "expect raw text only."
        ),
        supported_extensions=[".pdf", ".doc", ".docx", ".txt"],
        options=[
            HelperOption(
                key="preserve_page_markers",
                label="Preserve PDF page markers",
                option_type="checkbox",
                default=False,
                tooltip="Adds simple page markers (--- Page N ---) when converting PDFs.",
            ),
        ],
    )
)


def registry() -> HelperRegistry:
    """Return the global helper registry instance."""
    return _registry


def find_helper(helper_id: str) -> ConversionHelper:
    helper = _registry.get(helper_id)
    if helper is None:
        raise KeyError(f"Unknown conversion helper: {helper_id}")
    return helper


__all__ = [
    "HelperOption",
    "ConversionHelper",
    "HelperRegistry",
    "registry",
    "find_helper",
]
