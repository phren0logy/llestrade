from __future__ import annotations

from datetime import datetime
from pathlib import Path

import fitz

from src.app.core.highlight_extractor import HighlightExtractor
from src.app.core.highlights import (
    HighlightCollection,
    highlight_markdown_content,
    save_highlights_markdown,
    save_placeholder_markdown,
)


def _create_pdf_with_highlight(path: Path, *, text: str = "Highlighted text") -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), text, fontsize=12)
    rects = page.search_for(text)
    for rect in rects:
        annot = page.add_highlight_annot(rect)
        annot.set_colors(stroke=(1.0, 1.0, 0.0))
        annot.update()
    doc.save(path)
    doc.close()


def _create_pdf_without_highlight(path: Path, *, text: str = "Plain text") -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), text, fontsize=12)
    doc.save(path)
    doc.close()


def test_highlight_extractor_returns_collection(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _create_pdf_with_highlight(pdf_path)

    extractor = HighlightExtractor()
    collection = extractor.extract(pdf_path)

    assert collection is not None
    assert not collection.is_empty()
    highlights = list(collection.highlights)
    assert highlights[0].text.startswith("Highlighted text")
    assert highlights[0].page_number == 1


def test_markdown_helpers(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _create_pdf_with_highlight(pdf_path, text="Important finding")

    extractor = HighlightExtractor()
    collection = extractor.extract(pdf_path)
    assert collection is not None

    markdown = highlight_markdown_content(collection)
    assert "Highlights from sample.pdf" in markdown
    assert "Important finding" in markdown

    output_path = tmp_path / "out.md"
    save_highlights_markdown(collection, output_path)
    content = output_path.read_text(encoding="utf-8")
    assert "Important finding" in content

    placeholder_path = tmp_path / "placeholder.md"
    save_placeholder_markdown(placeholder_path, processed_at=datetime(2024, 1, 1))
    placeholder_content = placeholder_path.read_text(encoding="utf-8")
    assert "No highlights found" in placeholder_content


def test_highlight_extractor_returns_empty_collection(tmp_path: Path) -> None:
    pdf_path = tmp_path / "plain.pdf"
    _create_pdf_without_highlight(pdf_path)

    extractor = HighlightExtractor()
    collection = extractor.extract(pdf_path)

    assert collection is not None
    assert collection.is_empty()
    assert list(collection.highlights) == []
