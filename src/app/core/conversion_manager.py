"""Build conversion jobs for the dashboard pipeline."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from .project_manager import ProjectManager

LOGGER = logging.getLogger(__name__)

SUPPORTED_TEXT_EXTENSIONS = {".txt", ".text"}
SUPPORTED_MARKDOWN_EXTENSIONS = {".md", ".markdown"}
SUPPORTED_DOC_EXTENSIONS = {".doc", ".docx"}
SUPPORTED_PDF_EXTENSIONS = {".pdf"}


@dataclass(frozen=True)
class ConversionJob:
    source_path: Path
    relative_path: str
    destination_path: Path
    conversion_type: str  # copy|text|docx|pdf

    @property
    def display_name(self) -> str:
        return self.relative_path or self.source_path.name


def build_conversion_jobs(project_manager: ProjectManager) -> List[ConversionJob]:
    """Return jobs required to bring selected folders into converted_documents."""
    project_dir = project_manager.project_dir
    if not project_dir:
        return []

    state = project_manager.source_state
    if not state.root:
        return []

    root_path = _resolve_root(project_dir, state.root)
    if not root_path or not root_path.exists():
        LOGGER.warning("Source root %s is not accessible", state.root)
        return []

    selected = state.selected_folders or []
    if not selected:
        return []

    jobs: List[ConversionJob] = []
    seen_sources: set[Path] = set()
    for folder in selected:
        folder_path = root_path / folder
        if not folder_path.exists() or not folder_path.is_dir():
            LOGGER.debug("Selected folder %s missing under %s", folder, root_path)
            continue
        for source_file in _iter_files(folder_path):
            if source_file in seen_sources:
                continue
            seen_sources.add(source_file)
            relative = source_file.relative_to(root_path).as_posix()
            conversion_type = _classify_conversion(source_file)
            if conversion_type is None:
                continue
            destination = _destination_for(project_dir, relative, conversion_type)
            if not _needs_conversion(source_file, destination):
                continue
            jobs.append(
                ConversionJob(
                    source_path=source_file,
                    relative_path=relative,
                    destination_path=destination,
                    conversion_type=conversion_type,
                )
            )
    return jobs


def _resolve_root(project_dir: Path, root_spec: str) -> Path | None:
    path = Path(root_spec)
    if not path.is_absolute():
        path = (project_dir / root_spec).resolve()
    return path


def _iter_files(folder: Path) -> Iterable[Path]:
    for path in folder.rglob("*"):
        if path.is_file() and not path.name.startswith("."):
            yield path


def _classify_conversion(source_file: Path) -> str | None:
    suffix = source_file.suffix.lower()
    if suffix in SUPPORTED_MARKDOWN_EXTENSIONS:
        return "copy"
    if suffix in SUPPORTED_TEXT_EXTENSIONS:
        return "copy"
    if suffix in SUPPORTED_DOC_EXTENSIONS:
        return "docx"
    if suffix in SUPPORTED_PDF_EXTENSIONS:
        return "pdf"
    return None


def _destination_for(project_dir: Path, relative: str, conversion_type: str) -> Path:
    converted_root = project_dir / "converted_documents"
    converted_root.mkdir(parents=True, exist_ok=True)

    destination = converted_root / relative
    if conversion_type == "copy":
        return destination

    # For conversions to markdown ensure .md suffix
    destination = destination.with_suffix(".md")
    return destination


def _needs_conversion(source: Path, destination: Path) -> bool:
    if not destination.exists():
        return True
    try:
        return source.stat().st_mtime > destination.stat().st_mtime
    except OSError:
        return True


def copy_existing_markdown(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
