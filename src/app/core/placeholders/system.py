"""System placeholder helpers (project metadata, source files, aggregates)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Mapping


SYSTEM_PLACEHOLDERS = {
    "project_name",
    "timestamp",
    "source_pdf_filename",
    "source_pdf_relative_path",
    "source_pdf_absolute_path",
    "reduce_source_list",
    "reduce_source_table",
    "reduce_source_count",
}


@dataclass(slots=True)
class SourceFileContext:
    """Describe a converted source file for placeholder substitution."""

    absolute_path: Path
    relative_path: str

    @property
    def filename(self) -> str:
        return self.absolute_path.name

    def as_dict(self) -> dict[str, str]:
        return {
            "filename": self.filename,
            "relative_path": self.relative_path,
            "absolute_path": self.absolute_path.as_posix(),
        }


def system_placeholder_map(
    *,
    project_name: str | None = None,
    timestamp: datetime | None = None,
    source: SourceFileContext | None = None,
    reduce_sources: Iterable[SourceFileContext] | None = None,
) -> dict[str, str]:
    """Build system placeholder values for current execution context."""

    ts = timestamp or datetime.now(timezone.utc)
    reduce_sources = list(reduce_sources or [])

    source_values = {
        "source_pdf_filename": source.filename if source else "",
        "source_pdf_relative_path": source.relative_path if source else "",
        "source_pdf_absolute_path": source.absolute_path.as_posix() if source else "",
    }

    reduce_values = _build_reduce_placeholders(reduce_sources)

    payload = {
        "project_name": project_name or "",
        "timestamp": ts.astimezone(timezone.utc).isoformat(),
        **source_values,
        **reduce_values,
    }

    return {key: payload.get(key, "") for key in SYSTEM_PLACEHOLDERS}


def _build_reduce_placeholders(sources: List[SourceFileContext]) -> dict[str, str]:
    if not sources:
        return {
            "reduce_source_list": "",
            "reduce_source_table": "",
            "reduce_source_count": "",
        }

    list_entries = "\n".join(f"- {src.relative_path}" for src in sources)

    table_lines = ["| Filename | Relative Path | Absolute Path |", "| --- | --- | --- |"]
    for src in sources:
        table_lines.append(
            f"| {src.filename} | {src.relative_path} | {src.absolute_path.as_posix()} |"
        )
    table = "\n".join(table_lines)

    return {
        "reduce_source_list": list_entries,
        "reduce_source_table": table,
        "reduce_source_count": str(len(sources)),
    }


__all__ = ["SYSTEM_PLACEHOLDERS", "SourceFileContext", "system_placeholder_map"]
