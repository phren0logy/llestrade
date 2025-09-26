"""Highlight extraction utilities built on top of PyMuPDF."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Iterable, List, Optional

import fitz  # PyMuPDF

from .highlights import Highlight, HighlightCollection

LOGGER = logging.getLogger(__name__)


COLOR_NAMES = {
    (1.0, 1.0, 0.0): ("yellow", "#ffff00"),
    (1.0, 0.0, 0.0): ("red", "#ff0000"),
    (0.0, 1.0, 0.0): ("green", "#00ff00"),
    (0.0, 0.0, 1.0): ("blue", "#0000ff"),
    (1.0, 0.5, 0.0): ("orange", "#ff8000"),
    (1.0, 0.0, 1.0): ("magenta", "#ff00ff"),
    (0.0, 1.0, 1.0): ("cyan", "#00ffff"),
    (0.5, 0.5, 0.5): ("gray", "#808080"),
    (1.0, 0.75, 0.8): ("pink", "#ffbfcc"),
    (0.5, 0.0, 0.5): ("purple", "#800080"),
}


def rgb_to_color_name(rgb: Iterable[float]) -> str:
    """Return a friendly name for `rgb`, falling back to raw values."""

    rgb_tuple = tuple(rgb)
    if len(rgb_tuple) < 3:
        return "unknown"

    r, g, b = rgb_tuple[:3]
    min_distance = float("inf")
    closest_color = "unknown"
    closest_hex = ""
    for color_rgb, (name, hex_value) in COLOR_NAMES.items():
        distance = sum((component - reference) ** 2 for component, reference in zip((r, g, b), color_rgb))
        if distance < min_distance:
            min_distance = distance
            closest_color = name
            closest_hex = hex_value

    if min_distance > 0.3:
        hex_code = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
        return f"rgb({r:.2f},{g:.2f},{b:.2f}) {hex_code}"

    return f"{closest_color} ({closest_hex})"


class HighlightExtractor:
    """Extract highlight annotations from PDF files."""

    def extract(self, file_path: Path) -> Optional[HighlightCollection]:
        """Synchronously extract highlights from `file_path`."""

        if not file_path.exists():
            raise FileNotFoundError(file_path)
        if file_path.suffix.lower() != ".pdf":
            raise ValueError(f"Highlight extraction requires a PDF file: {file_path}")

        try:
            return self._extract_sync(file_path)
        except Exception:
            LOGGER.exception("Failed to extract highlights from %s", file_path)
            return None

    async def extract_async(self, file_path: Path) -> Optional[HighlightCollection]:
        """Async wrapper around :meth:`extract` for GUI workflows."""

        return await asyncio.to_thread(self.extract, file_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _extract_sync(self, file_path: Path) -> Optional[HighlightCollection]:
        highlights: List[Highlight] = []

        with fitz.open(str(file_path)) as pdf_document:  # type: ignore[call-arg]
            for page_number, page in enumerate(pdf_document, start=1):
                annotations = page.annots()
                if not annotations:
                    continue

                for annotation in annotations:
                    if annotation.type[0] != 8:  # type 8 is highlight
                        continue

                    try:
                        color = rgb_to_color_name(
                            annotation.colors.get("stroke", (1.0, 1.0, 0.0))
                        )
                        text = self._annotation_text(annotation, page)
                        if not text:
                            continue
                        rect = annotation.rect
                        highlights.append(
                            Highlight(
                                text=text,
                                page_number=page_number,
                                color=color,
                                position_x=float(rect.x0),
                                position_y=float(rect.y0),
                            )
                        )
                    except Exception:  # pragma: no cover - defensive guard
                        LOGGER.debug(
                            "Skipping annotation on page %s for %s", page_number, file_path,
                            exc_info=True,
                        )
                        continue

        if highlights:
            LOGGER.info("Extracted %s highlight(s) from %s", len(highlights), file_path)
            return HighlightCollection(highlights=tuple(highlights), source_file=file_path)

        LOGGER.info("No highlights found in %s", file_path)
        return HighlightCollection(highlights=tuple(), source_file=file_path)

    def _annotation_text(self, annotation, page) -> str:
        """Attempt to extract reliable text for a highlight annotation."""

        text = ""

        if hasattr(annotation, "get_text"):
            try:
                text = (annotation.get_text() or "").strip()
            except Exception:
                text = ""

        if not text:
            vertices = getattr(annotation, "vertices", None)
            if vertices:
                quads = [vertices[i : i + 4] for i in range(0, len(vertices), 4)]
                for quad in quads:
                    if len(quad) != 4:
                        continue
                    rect = fitz.Quad(quad).rect
                    extracted = page.get_text("text", clip=rect).strip()
                    if extracted:
                        text += extracted + " "
                text = text.strip()

        if not text:
            try:
                rect = annotation.rect
                text = page.get_text("text", clip=rect).strip()
            except Exception:
                text = ""

        return text


__all__ = [
    "HighlightExtractor",
    "rgb_to_color_name",
]

