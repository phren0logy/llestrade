"""Shared placeholder helpers for bulk analysis prompts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, Mapping, Optional

from src.app.core.placeholders.system import SourceFileContext, system_placeholder_map


def build_bulk_placeholders(
    *,
    base_placeholders: Mapping[str, str],
    project_name: Optional[str],
    timestamp: Optional[datetime] = None,
    source: Optional[SourceFileContext] = None,
    reduce_sources: Optional[Iterable[SourceFileContext]] = None,
) -> Dict[str, str]:
    """Return placeholder values matching the runtime worker behaviour."""

    ts = timestamp or datetime.now(timezone.utc)

    values: Dict[str, str] = dict(base_placeholders)
    values.update(
        system_placeholder_map(
            project_name=project_name or "",
            timestamp=ts,
            source=source,
            reduce_sources=reduce_sources,
        )
    )
    return values


__all__ = ["build_bulk_placeholders"]
