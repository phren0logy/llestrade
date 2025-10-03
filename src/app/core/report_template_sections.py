"""Utilities for splitting report templates into sections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from langchain_text_splitters import MarkdownHeaderTextSplitter


@dataclass(frozen=True)
class TemplateSection:
    """Represents a top-level section extracted from a report template."""

    title: str
    body: str


def load_template_sections(template_path: Path) -> List[TemplateSection]:
    """Split a markdown template into top-level sections.

    The legacy workflow generated one LLM call per top-level header. We replicate
    that behaviour by splitting on ``#`` headers and preserving the header text
    inside each section's body.
    """

    if not template_path.is_file():
        raise FileNotFoundError(f"Template not found: {template_path}")

    text = template_path.read_text(encoding="utf-8")

    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "Header 1")],
        strip_headers=False,
    )
    documents = splitter.split_text(text)

    sections: List[TemplateSection] = []
    for index, document in enumerate(documents, start=1):
        metadata = getattr(document, "metadata", {}) or {}
        title = metadata.get("Header 1") or f"Section {index}"
        body = (getattr(document, "page_content", None) or str(document)).strip()
        if not body:
            continue
        sections.append(TemplateSection(title=title, body=body))

    if not sections:
        # Fallback: treat the entire template as a single section.
        cleaned = text.strip()
        if cleaned:
            sections.append(TemplateSection(title="Section 1", body=cleaned))

    return sections


__all__ = ["TemplateSection", "load_template_sections"]
