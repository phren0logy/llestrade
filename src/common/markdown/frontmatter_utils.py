"""Utilities for producing consistent Markdown front matter."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping

import frontmatter

# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Describe an input file that contributed to a Markdown output."""

    path: Path | str
    relative: str | None = None
    kind: str | None = None
    role: str | None = None
    checksum: str | None = None

    def to_dict(self) -> Dict[str, str]:
        payload: Dict[str, str] = {}
        path_str = _normalize_path(self.path)
        if path_str:
            payload["path"] = path_str
        if self.relative:
            payload["relative"] = self.relative
        if self.kind:
            payload["kind"] = self.kind
        if self.role:
            payload["role"] = self.role
        if self.checksum:
            payload["checksum"] = self.checksum
        return payload


@dataclass(frozen=True, slots=True)
class PromptReference:
    """Describe a prompt file or identifier used to generate an output."""

    path: Path | str | None = None
    identifier: str | None = None
    role: str | None = None

    def to_dict(self) -> Dict[str, str]:
        payload: Dict[str, str] = {}
        if self.path:
            payload["path"] = _normalize_path(self.path)
        if self.identifier:
            payload["id"] = self.identifier
        if self.role:
            payload["role"] = self.role
        return payload


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def build_document_metadata(
    *,
    project_path: Path | None,
    generator: str,
    created_at: datetime | None = None,
    sources: Iterable[SourceReference] | None = None,
    prompts: Iterable[PromptReference] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return canonical metadata payload for Markdown documents."""

    metadata: Dict[str, Any] = {}

    if project_path:
        metadata["project_path"] = _normalize_path(project_path)

    created = created_at or datetime.now(timezone.utc)
    metadata["created_at"] = created.astimezone(timezone.utc).isoformat()
    metadata["generator"] = generator

    source_payload = [
        item.to_dict() for item in (sources or []) if item.to_dict()
    ]
    if source_payload:
        metadata["sources"] = source_payload

    prompt_payload = [
        item.to_dict() for item in (prompts or []) if item.to_dict()
    ]
    if prompt_payload:
        metadata["prompts"] = prompt_payload

    if extra:
        for key, value in extra.items():
            if value is None:
                continue
            metadata[key] = value

    return metadata


def apply_frontmatter(
    content: str,
    metadata: Mapping[str, Any],
    *,
    merge_existing: bool = True,
) -> str:
    """Attach metadata to Markdown content via YAML front matter."""

    document = frontmatter.loads(content)

    if merge_existing and isinstance(document.metadata, MutableMapping):
        merged: Dict[str, Any] = dict(document.metadata)
        merged.update(metadata)
        document.metadata = _prune_empty(merged)
    else:
        document.metadata = _prune_empty(dict(metadata))

    return frontmatter.dumps(document)


def compute_file_checksum(path: Path, *, algorithm: str = "sha256") -> str | None:
    """Return hexadecimal digest for ``path`` or ``None`` if not accessible."""

    try:
        hasher = hashlib.new(algorithm)
    except ValueError:
        raise ValueError(f"Unsupported digest algorithm: {algorithm}") from None

    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                if not chunk:
                    break
                hasher.update(chunk)
    except OSError:
        return None
    return hasher.hexdigest()


def infer_project_path(
    path: Path,
    *,
    markers: Iterable[str] = ("converted_documents", "highlights", "bulk_analysis", "reports", "templates"),
) -> Path | None:
    """Return the parent directory considered the project root, if identifiable."""

    resolved = path.resolve()
    parts = resolved.parts
    for marker in markers:
        if marker in parts:
            idx = parts.index(marker)
            if idx > 0:
                return Path(*parts[:idx])
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    if isinstance(path, Path):
        return path.resolve().as_posix()
    return Path(path).expanduser().resolve().as_posix()


def _prune_empty(payload: Mapping[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in payload.items():
        if value in (None, "", [], {}, ()):
            continue
        clean[key] = value
    return clean


__all__ = [
    "PromptReference",
    "SourceReference",
    "apply_frontmatter",
    "build_document_metadata",
    "compute_file_checksum",
    "infer_project_path",
]
