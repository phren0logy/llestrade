"""Highlight domain models and helpers for dashboard workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


@dataclass(slots=True)
class Highlight:
    """Single highlight annotation captured from a PDF document."""

    text: str
    page_number: int
    color: str
    position_x: float
    position_y: float


@dataclass(slots=True)
class HighlightCollection:
    """Container for highlights extracted from a single source file."""

    highlights: Sequence[Highlight]
    source_file: Path
    extracted_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def by_color(self) -> Dict[str, List[Highlight]]:
        grouped: Dict[str, List[Highlight]] = {}
        for item in self.highlights:
            grouped.setdefault(item.color, []).append(item)
        return grouped

    def by_page(self) -> Dict[int, List[Highlight]]:
        grouped: Dict[int, List[Highlight]] = {}
        for item in self.highlights:
            grouped.setdefault(item.page_number, []).append(item)
        return grouped

    def is_empty(self) -> bool:
        return len(self.highlights) == 0


def highlight_markdown_content(
    collection: HighlightCollection,
    *,
    source_relative: str | None = None,
) -> str:
    """Return markdown content representing `collection` grouped by color/page."""

    if not collection.highlights:
        return ""

    lines: List[str] = []
    lines.append(f"# Highlights from {collection.source_file.name}\n")
    if source_relative:
        lines.append(f"Source: `{source_relative}`\n")

    highlights_by_color = collection.by_color()
    total_highlights = len(collection.highlights)
    num_colors = len(highlights_by_color)

    lines.append(
        f"Total: {total_highlights} highlight{'s' if total_highlights != 1 else ''} in {num_colors} "
        f"color{'s' if num_colors != 1 else ''}\n"
    )

    for color, color_highlights in sorted(
        highlights_by_color.items(),
        key=lambda item: len(item[1]),
        reverse=True,
    ):
        color_heading = color.split(" (")[0] if " (" in color else color
        lines.append(f"## {color_heading.capitalize()} ({len(color_highlights)})\n")

        highlights_by_page = _group_by_page_ordered(color_highlights)
        for page_num, page_highlights in highlights_by_page.items():
            lines.append(f"**Page {page_num}**")
            for highlight in page_highlights:
                lines.append(f"- {highlight.text}")
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def save_highlights_markdown(
    collection: HighlightCollection,
    output_path: Path,
    *,
    source_relative: str | None = None,
) -> None:
    """Write markdown representation of `collection` to `output_path`."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = highlight_markdown_content(collection, source_relative=source_relative)
    output_path.write_text(content, encoding="utf-8")


def placeholder_markdown(*, processed_at: datetime | None = None) -> str:
    """Return placeholder markdown content when no highlights were found."""

    timestamp = (processed_at or datetime.now(timezone.utc)).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    return (
        "# Highlights\n\n"
        "No highlights found in this document.\n\n"
        f"Processed: {timestamp}\n"
    )


def save_placeholder_markdown(output_path: Path, *, processed_at: datetime | None = None) -> None:
    """Persist placeholder markdown when highlight extraction yields no results."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(placeholder_markdown(processed_at=processed_at), encoding="utf-8")


def expected_highlight_relatives(converted_relatives: Iterable[str]) -> Dict[str, str]:
    """Map converted document paths to expected highlight relative paths."""

    mapping: Dict[str, str] = {}
    for relative in converted_relatives:
        normalized = relative.strip("/")
        if not normalized:
            continue
        base = Path(normalized)
        if base.suffix:
            highlight_path = base.with_suffix(".highlights.md")
        else:
            highlight_path = base.with_name(base.name + ".highlights.md")
        highlight_relative = highlight_path.as_posix()
        mapping[normalized] = highlight_relative
    return mapping


def _group_by_page_ordered(highlights: Sequence[Highlight]) -> Dict[int, List[Highlight]]:
    grouped = {}
    for highlight in highlights:
        grouped.setdefault(highlight.page_number, []).append(highlight)
    for page_highlights in grouped.values():
        page_highlights.sort(key=lambda item: (item.position_y, item.position_x))
    return dict(sorted(grouped.items()))


@dataclass(slots=True)
class ColorEntry:
    """Single highlight entry grouped for color aggregate outputs."""

    source_relative: str
    page_number: int
    text: str


def aggregate_highlights_by_color(
    collections: Sequence[tuple[str, HighlightCollection]]
) -> Dict[str, List[ColorEntry]]:
    """Group highlights by color with their source metadata."""

    aggregates: Dict[str, List[ColorEntry]] = {}
    for source_relative, collection in collections:
        if collection.is_empty():
            continue
        for highlight in collection.highlights:
            aggregates.setdefault(highlight.color, []).append(
                ColorEntry(
                    source_relative=source_relative,
                    page_number=highlight.page_number,
                    text=highlight.text,
                )
            )

    for entries in aggregates.values():
        entries.sort(key=lambda entry: (entry.source_relative, entry.page_number, entry.text))
    return aggregates


def _color_slug(color: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", color.lower()).strip("-")
    return slug or "color"


def _color_markdown(color: str, entries: Sequence[ColorEntry], generated_at: datetime) -> str:
    lines: List[str] = []
    lines.append(f"# {color.title()} Highlights\n")
    lines.append(
        f"Generated: {generated_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}"
    )
    lines.append(f"Total entries: {len(entries)}\n")

    current_source = None
    for entry in entries:
        if entry.source_relative != current_source:
            current_source = entry.source_relative
            lines.append(f"## {entry.source_relative}")
        lines.append(f"- Page {entry.page_number}: {entry.text}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def save_color_aggregates(
    aggregates: Dict[str, List[ColorEntry]],
    output_dir: Path,
    *,
    generated_at: datetime,
) -> Dict[str, Path]:
    """Persist per-color markdown files summarising highlight entries.

    Returns a mapping of color display name to written file path.
    """

    output_dir.mkdir(parents=True, exist_ok=True)

    for existing in output_dir.glob("*.md"):
        existing.unlink()

    written: Dict[str, Path] = {}
    for color, entries in aggregates.items():
        if not entries:
            continue
        slug = _color_slug(color)
        path = output_dir / f"{slug}.md"
        content = _color_markdown(color, entries, generated_at)
        path.write_text(content, encoding="utf-8")
        written[color] = path
    return written


__all__ = [
    "HighlightCollection",
    "Highlight",
    "highlight_markdown_content",
    "save_highlights_markdown",
    "placeholder_markdown",
    "save_placeholder_markdown",
    "expected_highlight_relatives",
    "aggregate_highlights_by_color",
    "save_color_aggregates",
    "ColorEntry",
]
