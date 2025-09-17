"""Summary group persistence helpers."""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

LOGGER = logging.getLogger(__name__)

CONFIG_FILENAME = "config.json"
SUMMARY_FOLDER = "summaries"
SUMMARY_GROUP_VERSION = "1"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    slug = slug.strip("-")
    return slug or "group"


def _ensure_unique_slug(base_dir: Path, candidate: str, existing_slug: Optional[str] = None) -> str:
    if existing_slug:
        return existing_slug
    slug = candidate
    index = 2
    while (base_dir / slug).exists():
        slug = f"{candidate}-{index}"
        index += 1
    return slug


def _groups_root(project_dir: Path) -> Path:
    root = project_dir / SUMMARY_FOLDER
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class SummaryGroup:
    group_id: str
    name: str
    description: str = ""
    files: List[str] = field(default_factory=list)
    prompt_template: str = ""
    model: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    slug: Optional[str] = None
    version: str = SUMMARY_GROUP_VERSION

    @classmethod
    def create(
        cls,
        name: str,
        *,
        description: str = "",
        files: Optional[Iterable[str]] = None,
        prompt_template: str = "",
        model: str = "",
    ) -> "SummaryGroup":
        return cls(
            group_id=str(uuid.uuid4()),
            name=name,
            description=description,
            files=list(files or []),
            prompt_template=prompt_template,
            model=model,
        )

    def touch(self) -> None:
        self.updated_at = _utcnow()

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.group_id,
            "name": self.name,
            "description": self.description,
            "files": self.files,
            "prompt_template": self.prompt_template,
            "model": self.model,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "slug": self.slug,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "SummaryGroup":
        return cls(
            group_id=str(payload.get("id")),
            name=str(payload.get("name", "Untitled Group")),
            description=str(payload.get("description", "")),
            files=list(payload.get("files", [])),
            prompt_template=str(payload.get("prompt_template", "")),
            model=str(payload.get("model", "")),
            created_at=_parse_datetime(payload.get("created_at")),
            updated_at=_parse_datetime(payload.get("updated_at")),
            slug=payload.get("slug"),
            version=str(payload.get("version", SUMMARY_GROUP_VERSION)),
        )

    # Convenience properties
    @property
    def folder_name(self) -> str:
        return self.slug or _slugify(self.name)


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return _utcnow()


# ----------------------------------------------------------------------
# Persistence helpers
# ----------------------------------------------------------------------

def load_summary_groups(project_dir: Path) -> List[SummaryGroup]:
    root = _groups_root(project_dir)
    groups: List[SummaryGroup] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        config_path = child / CONFIG_FILENAME
        if not config_path.exists():
            continue
        try:
            data = json.loads(config_path.read_text())
            group = SummaryGroup.from_dict(data)
            if not group.slug:
                group.slug = child.name
            groups.append(group)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Failed to load summary group from %s: %s", config_path, exc)
    return groups


def save_summary_group(project_dir: Path, group: SummaryGroup) -> SummaryGroup:
    root = _groups_root(project_dir)
    slug = _ensure_unique_slug(root, _slugify(group.name), group.slug)
    group.slug = slug
    group.touch()

    group_dir = root / slug
    group_dir.mkdir(parents=True, exist_ok=True)

    config_path = group_dir / CONFIG_FILENAME
    config_path.write_text(json.dumps(group.to_dict(), indent=2))
    return group


def delete_summary_group(project_dir: Path, group: SummaryGroup) -> None:
    if not group.slug:
        return
    group_dir = _groups_root(project_dir) / group.slug
    if group_dir.exists():
        for path in group_dir.glob("*"):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        group_dir.rmdir()


__all__ = [
    "SummaryGroup",
    "load_summary_groups",
    "save_summary_group",
    "delete_summary_group",
]
