"""Helpers for deriving report prompt placeholders for previews."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple

from src.app.core.project_manager import ProjectManager, ProjectMetadata
from src.app.core.report_inputs import ReportInputDescriptor
from src.app.core.report_template_sections import load_template_sections
from src.app.core.placeholders.system import system_placeholder_map


def _read_text(path: Optional[Path]) -> str:
    if not path:
        return ""
    try:
        return Path(path).expanduser().read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _load_sample_section(template_path: Optional[Path]) -> Tuple[str, str]:
    if not template_path:
        return "", ""
    try:
        sections = load_template_sections(template_path)
    except Exception:
        return "", ""
    if not sections:
        return "", ""
    first = sections[0]
    return first.body.strip(), first.title or ""


def _read_selected_inputs(project_dir: Path, descriptors: Iterable[ReportInputDescriptor]) -> str:
    lines: list[str] = []
    for descriptor in descriptors:
        absolute = (project_dir / descriptor.relative_path).resolve()
        if not absolute.exists() or not absolute.is_file():
            continue
        if absolute.suffix.lower() not in {".md", ".txt"}:
            continue
        try:
            content = absolute.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        header = f"# {descriptor.label} ({descriptor.category})"
        lines.extend(["<!-- preview: report-input -->", header, content, ""])
    return "\n".join(lines).strip()


def build_report_preview_placeholders(
    *,
    project_manager: ProjectManager,
    metadata: ProjectMetadata | None,
    template_path: Optional[Path],
    transcript_path: Optional[Path],
    draft_path: Optional[Path],
    selected_inputs: Sequence[ReportInputDescriptor],
) -> Dict[str, str]:
    """Return placeholder values mirroring the runtime worker behaviour."""

    project_dir = Path(project_manager.project_dir or "")
    effective_project_name = (
        project_manager.project_name
        or (metadata.case_name if metadata else "")
        or (project_dir.name if project_dir.exists() else "")
    )

    placeholder_values = dict(project_manager.placeholder_mapping())
    placeholder_values.update(
        system_placeholder_map(
            project_name=effective_project_name,
        )
    )

    template_section_body, template_section_title = _load_sample_section(template_path)
    transcript_text = _read_text(transcript_path)
    draft_text = _read_text(draft_path)
    additional_documents = (
        _read_selected_inputs(project_dir, selected_inputs) if project_dir.exists() else ""
    )

    placeholder_values.setdefault("template_section", template_section_body)
    placeholder_values.setdefault("section_title", template_section_title)
    placeholder_values.setdefault("transcript", transcript_text)
    placeholder_values.setdefault("additional_documents", additional_documents)
    placeholder_values.setdefault("draft_report", draft_text)
    placeholder_values.setdefault("template", _read_text(template_path))

    return placeholder_values


__all__ = ["build_report_preview_placeholders"]
