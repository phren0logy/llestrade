from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.app.core.bulk_prompt_context import build_bulk_placeholders
from src.app.core.placeholders.system import SourceFileContext


def test_build_bulk_placeholders_includes_source_context(tmp_path: Path) -> None:
    base = {"client": "ACME"}
    timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc)

    source_path = tmp_path / "converted" / "sample.md"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("content", encoding="utf-8")
    context = SourceFileContext(absolute_path=source_path, relative_path="sample.md")

    placeholders = build_bulk_placeholders(
        base_placeholders=base,
        project_name="Case Name",
        timestamp=timestamp,
        source=context,
    )

    assert placeholders["client"] == "ACME"
    assert placeholders["project_name"] == "Case Name"
    assert placeholders["timestamp"] == timestamp.isoformat()
    assert placeholders["source_pdf_filename"] == "sample.md"
