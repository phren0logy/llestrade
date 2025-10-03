"""Utilities for generating bulk-analysis prompt previews."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.app.core.bulk_analysis_runner import (
    load_prompts,
    render_system_prompt,
    render_user_prompt,
)
from src.app.core.project_manager import ProjectMetadata
from src.app.core.summary_groups import SummaryGroup


class PromptPreviewError(RuntimeError):
    """Raised when a prompt preview cannot be generated."""


@dataclass(slots=True)
class PromptPreview:
    system_prompt: str
    user_prompt: str


def generate_prompt_preview(
    project_dir: Path,
    group: SummaryGroup,
    *,
    metadata: Optional[ProjectMetadata] = None,
    max_content_lines: int = 10,
) -> PromptPreview:
    """Return a preview of the system/user prompts for the supplied group."""

    project_dir = Path(project_dir)
    if not project_dir.exists():
        raise PromptPreviewError("Project directory is not available.")

    bundle = load_prompts(project_dir, group, metadata)
    system_prompt = render_system_prompt(bundle, metadata)

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
    user_prompt = render_user_prompt(
        bundle,
        metadata,
        document_name,
        truncated_content,
    )

    return PromptPreview(system_prompt=system_prompt, user_prompt=user_prompt)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_first_per_document_input(
    project_dir: Path,
    group: SummaryGroup,
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


def _resolve_first_combined_input(project_dir: Path, group: SummaryGroup) -> Optional[Path]:
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
