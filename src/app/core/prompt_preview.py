"""Utilities for generating bulk-analysis prompt previews."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from src.app.core.bulk_analysis_runner import (
    load_prompts,
)
from src.app.core.bulk_analysis_runner import _metadata_context  # type: ignore[attr-defined]
from src.app.core.project_manager import ProjectMetadata
from src.app.core.bulk_analysis_groups import BulkAnalysisGroup
from src.app.core.prompt_placeholders import get_prompt_spec, format_prompt


class PromptPreviewError(RuntimeError):
    """Raised when a prompt preview cannot be generated."""


@dataclass(slots=True)
class PromptPreview:
    system_template: str
    user_template: str
    system_rendered: str
    user_rendered: str
    values: dict[str, str]
    required: set[str]
    optional: set[str]


def generate_prompt_preview(
    project_dir: Path,
    group: BulkAnalysisGroup,
    *,
    metadata: Optional[ProjectMetadata] = None,
    max_content_lines: int = 10,
    placeholder_values: Optional[Mapping[str, str]] = None,
) -> PromptPreview:
    """Return a preview of the system/user prompts for the supplied group."""

    project_dir = Path(project_dir)
    if not project_dir.exists():
        raise PromptPreviewError("Project directory is not available.")

    bundle = load_prompts(project_dir, group, metadata)
    metadata_context = _metadata_context(metadata)

    base_values: dict[str, str] = dict(placeholder_values or {})
    for key, value in metadata_context.items():
        base_values.setdefault(key, value)

    system_values = dict(base_values)
    system_rendered = format_prompt(bundle.system_template, system_values)

    operation = getattr(group, "operation", "per_document") or "per_document"
    if operation == "combined":
        preview_path = _resolve_first_combined_input(project_dir, group)
        document_name = group.name or "Combined"
    else:
        preview_path, document_name = _resolve_first_per_document_input(project_dir, group)

    if preview_path is None:
        raise PromptPreviewError("No converted files are available for this group.")

    try:
        content = preview_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - filesystem race
        raise PromptPreviewError(f"Preview source missing: {preview_path}") from exc

    truncated_content = _truncate_markdown(content, max_content_lines)
    user_context = dict(base_values)
    user_context.update(
        {
            "document_name": document_name,
            "document_content": truncated_content,
        }
    )
    user_rendered = format_prompt(bundle.user_template, user_context)

    required: set[str] = set()
    optional: set[str] = set()
    system_spec = get_prompt_spec("document_analysis_system_prompt")
    if system_spec:
        required.update(system_spec.required)
        optional.update(system_spec.optional)
    user_spec = get_prompt_spec("document_bulk_analysis_prompt")
    if user_spec:
        required.update(user_spec.required)
        optional.update(user_spec.optional)

    values = {**system_values, **user_context}

    return PromptPreview(
        system_template=bundle.system_template,
        user_template=bundle.user_template,
        system_rendered=system_rendered,
        user_rendered=user_rendered,
        values=values,
        required=required,
        optional=optional,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_first_per_document_input(
    project_dir: Path,
    group: BulkAnalysisGroup,
) -> tuple[Optional[Path], str]:
    converted_root = project_dir / "converted_documents"
    if not converted_root.exists():
        return None, group.files[0] if group.files else group.name

    file_map = {}
    for path in converted_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
            relative = path.relative_to(converted_root).as_posix().strip("/")
            file_map[relative] = path

    if not file_map:
        return None, group.files[0] if group.files else group.name

    ordered: list[str] = []
    for entry in group.files or []:
        candidate = entry.strip("/")
        if candidate in file_map:
            ordered.append(candidate)

    for directory in group.directories or []:
        directory = directory.strip("/")
        if not directory:
            continue
        for relative in sorted(file_map):
            if relative == directory or relative.startswith(directory + "/"):
                ordered.append(relative)

    if not ordered:
        ordered = sorted(file_map)

    if not ordered:
        return None, group.files[0] if group.files else group.name

    first_relative = ordered[0]
    return file_map[first_relative], first_relative


def _resolve_first_combined_input(project_dir: Path, group: BulkAnalysisGroup) -> Optional[Path]:
    conv_root = project_dir / "converted_documents"
    ba_root = project_dir / "bulk_analysis"

    # Explicit converted files
    for rel in group.combine_converted_files or []:
        rel = rel.strip("/")
        if not rel:
            continue
        candidate = conv_root / rel
        if candidate.exists():
            return candidate

    # Converted directories
    for rel_dir in group.combine_converted_directories or []:
        rel_dir = rel_dir.strip("/")
        if not rel_dir:
            continue
        base = conv_root / rel_dir
        if not base.exists():
            continue
        candidates = sorted(p for p in base.rglob("*.md") if p.is_file())
        if candidates:
            return candidates[0]

    # Entire groups under bulk_analysis/<slug>/outputs
    for slug in group.combine_map_groups or []:
        slug = slug.strip()
        if not slug:
            continue
        outputs = ba_root / slug / "outputs"
        candidates = sorted(p for p in outputs.rglob("*.md") if p.is_file())
        if candidates:
            return candidates[0]

    # Specific directories under map outputs
    for rel_dir in group.combine_map_directories or []:
        rel_dir = rel_dir.strip("/")
        if not rel_dir:
            continue
        parts = rel_dir.split("/", 1)
        if len(parts) != 2:
            continue
        slug, remainder = parts
        base = ba_root / slug / "outputs" / remainder
        candidates = sorted(p for p in base.rglob("*.md") if p.is_file())
        if candidates:
            return candidates[0]

    # Explicit map files
    for rel in group.combine_map_files or []:
        rel = rel.strip("/")
        if not rel:
            continue
        parts = rel.split("/", 1)
        if len(parts) != 2:
            continue
        slug, remainder = parts
        candidate = ba_root / slug / "outputs" / remainder
        if candidate.exists():
            return candidate

    # Fallback to first converted document
    path, _ = _resolve_first_per_document_input(project_dir, group)
    return path


def _truncate_markdown(content: str, max_lines: int) -> str:
    lines = content.splitlines()
    if len(lines) <= max_lines:
        return content
    truncated = lines[:max_lines]
    truncated.append("…")
    return "\n".join(truncated)


__all__ = [
    "PromptPreview",
    "PromptPreviewError",
    "generate_prompt_preview",
]
