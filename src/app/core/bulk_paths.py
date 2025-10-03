"""Helpers for locating bulk-analysis output files."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, Tuple

_EXCLUDED_PREFIXES = ("reduce",)


def normalize_map_relative(relative: str) -> str:
    """Return a normalised per-document output path without leading prefixes."""

    if not relative:
        return ""
    rel = relative.strip().strip("/")
    if rel.startswith("outputs/"):
        rel = rel[len("outputs/") :]
    return rel


def get_group_dir(project_dir: Path, slug: str) -> Path:
    """Return the bulk-analysis folder for the supplied group slug."""

    return project_dir / "bulk_analysis" / slug


def _outputs_root(group_dir: Path) -> Path:
    outputs = group_dir / "outputs"
    return outputs if outputs.exists() else group_dir


def _is_excluded(rel_path: str) -> bool:
    for prefix in _EXCLUDED_PREFIXES:
        if rel_path == prefix or rel_path.startswith(prefix + "/"):
            return True
    return False


def iter_map_outputs(project_dir: Path, slug: str) -> Iterator[Tuple[Path, str]]:
    """Yield (absolute_path, relative_key) for per-document outputs in a group."""

    group_dir = get_group_dir(project_dir, slug)
    root = _outputs_root(group_dir)
    if not root.exists():  # No outputs yet
        return
    for path in root.rglob("*.md"):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if _is_excluded(rel):
            continue
        yield path, rel


def iter_map_outputs_under(project_dir: Path, slug: str, relative_dir: str) -> Iterator[Tuple[Path, str]]:
    """Yield outputs under a specific directory selection."""

    normalized = normalize_map_relative(relative_dir)
    if not normalized:
        yield from iter_map_outputs(project_dir, slug)
        return

    prefix = normalized.rstrip("/")
    for path, rel in iter_map_outputs(project_dir, slug):
        if rel == prefix or rel.startswith(prefix + "/"):
            yield path, rel


def resolve_map_output_path(project_dir: Path, slug: str, relative_file: str) -> Path:
    """Return the absolute path for a stored per-document output selection."""

    group_dir = get_group_dir(project_dir, slug)
    root = _outputs_root(group_dir)
    normalized = normalize_map_relative(relative_file)
    return root / normalized


__all__ = [
    "iter_map_outputs",
    "iter_map_outputs_under",
    "normalize_map_relative",
    "resolve_map_output_path",
]

