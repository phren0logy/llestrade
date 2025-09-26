"""Highlight domain models and helpers for dashboard workflows."""

from __future__ import annotations

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


def highlight_markdown_content(collection: HighlightCollection) -> str:
    """Return markdown content representing `collection` grouped by color/page."""

    if not collection.highlights:
        return ""

    lines: List[str] = []
    lines.append(f"# Highlights from {collection.source_file.name}\n")

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


def save_highlights_markdown(collection: HighlightCollection, output_path: Path) -> None:
    """Write markdown representation of `collection` to `output_path`."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = highlight_markdown_content(collection)
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
