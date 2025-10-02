"""Shared helpers for the bulk-analysis worker."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from src.common.llm.chunking import ChunkingStrategy
from src.common.llm.tokens import TokenCounter
from .prompt_manager import PromptManager
from .project_manager import ProjectMetadata
from .summary_groups import SummaryGroup

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptBundle:
    """Resolved prompts for a bulk analysis run."""

    system_template: str
    user_template: str


@dataclass(frozen=True)
class BulkAnalysisDocument:
    """Represents a single document to analyse."""

    source_path: Path
    relative_path: str
    output_path: Path


class BulkAnalysisCancelled(Exception):
    """Raised when cancellation is requested during processing."""


def prepare_documents(
    project_dir: Path,
    group: SummaryGroup,
    selected_files: Sequence[str],
) -> List[BulkAnalysisDocument]:
    """Resolve bulk-analysis documents and their output paths."""

    converted_root = project_dir / "converted_documents"
    group_root = project_dir / "bulk_analysis" / group.folder_name
    documents: List[BulkAnalysisDocument] = []

    for relative in selected_files:
        source_path = converted_root / relative
        if not source_path.exists():
            LOGGER.warning("Converted file missing for bulk analysis: %s", source_path)
            continue

        # Only process markdown or text files produced by conversion
        if source_path.suffix.lower() not in {".md", ".txt"}:
            LOGGER.warning("Skipping non-markdown file for bulk analysis: %s", source_path)
            continue

        output_relative = Path(relative).with_suffix("")
        output_filename = f"{output_relative.name}_analysis.md"
        output_path = group_root / output_relative.parent / output_filename
        documents.append(
            BulkAnalysisDocument(
                source_path=source_path,
                relative_path=relative,
                output_path=output_path,
            )
        )

    return documents


def load_prompts(
    project_dir: Path,
    group: SummaryGroup,
    metadata: Optional[ProjectMetadata],
) -> PromptBundle:
    """Return the prompt bundle for the supplied group."""

    prompt_manager = PromptManager()
    system_template = _read_prompt_file(project_dir, group.system_prompt_path)
    if not system_template:
        try:
            system_template = prompt_manager.get_template("document_analysis_system_prompt")
        except KeyError:
            system_template = "You are a forensic assistant."

    user_template = _read_prompt_file(project_dir, group.user_prompt_path)
    if not user_template:
        try:
            user_template = prompt_manager.get_template("document_summary_prompt")
        except KeyError:
            user_template = (
                "Summarise the provided document content focusing on key facts, timelines, "
                "and clinical details.\n\n{document_content}"
            )

    return PromptBundle(system_template=system_template, user_template=user_template)


def render_system_prompt(bundle: PromptBundle, metadata: Optional[ProjectMetadata]) -> str:
    """Format the system prompt with available metadata."""

    context = _metadata_context(metadata)
    return _safe_format(bundle.system_template, context)


def render_user_prompt(
    bundle: PromptBundle,
    metadata: Optional[ProjectMetadata],
    document_name: str,
    document_content: str,
    *,
    chunk_index: Optional[int] = None,
    chunk_total: Optional[int] = None,
) -> str:
    """Format the user prompt for a document or chunk."""

    context = _metadata_context(metadata)
    context.update(
        {
            "document_name": document_name,
            "document_content": document_content,
        }
    )
    if chunk_index is not None and chunk_total is not None:
        context.update(
            {
                "chunk_index": chunk_index,
                "chunk_total": chunk_total,
            }
        )
    prompt = _safe_format(bundle.user_template, context)
    if chunk_index is not None and chunk_total is not None:
        prefix = (
            f"You are analysing chunk {chunk_index} of {chunk_total} from {document_name}.\n\n"
        )
        prompt = prefix + prompt
    return prompt


def should_chunk(
    content: str,
    provider_id: str,
    model_name: Optional[str],
) -> tuple[bool, int, int]:
    """Return whether chunking is required and the relevant token counts."""

    token_info = TokenCounter.count(text=content, provider=provider_id, model=model_name or "")
    tokens = token_info.get("token_count") if token_info.get("success") else len(content) // 4
    context_window = TokenCounter.get_model_context_window(model_name or provider_id)
    max_tokens_per_chunk = max(int(context_window * 0.5), 4000)
    return tokens > max_tokens_per_chunk, tokens, max_tokens_per_chunk


def generate_chunks(content: str, max_tokens: int) -> List[str]:
    """Split the document into manageable chunks."""

    return ChunkingStrategy.markdown_headers(
        text=content,
        max_tokens=max_tokens,
        overlap=2000,
    )


def combine_chunk_summaries(
    summaries: Iterable[str],
    *,
    document_name: str,
    metadata: Optional[ProjectMetadata],
) -> tuple[str, Dict[str, str]]:
    """Prepare the final prompt for combining chunk summaries."""

    combined = "\n\n---\n\n".join(summary.strip() for summary in summaries if summary.strip())
    context = _metadata_context(metadata)
    context.update(
        {
            "document_name": document_name,
            "chunk_summaries": combined,
        }
    )
    prompt = _safe_format(
        (
            "Create a unified bulk analysis by combining these partial results of document: {document_name}\n\n"
            "## Partial Results:\n{chunk_summaries}\n\n"
            "Please create a single, coherent deliverable that captures all key information from the document."
        ),
        context,
    )
    return prompt, context


def _safe_format(template: str, context: Dict[str, object]) -> str:
    class _SafeDict(dict):
        def __missing__(self, key: str) -> str:  # noqa: D401 - simple placeholder helper
            return "{" + key + "}"

    safe_context = _SafeDict({k: v for k, v in context.items() if v is not None})
    return template.format_map(safe_context)


def _read_prompt_file(project_dir: Path, path_str: str | None) -> str:
    if not path_str:
        return ""
    candidate = Path(path_str).expanduser()
    search_paths: List[Path] = []
    if candidate.is_absolute():
        search_paths.append(candidate)
    else:
        if project_dir:
            search_paths.append((project_dir / candidate).resolve())
        repo_root = Path(__file__).resolve().parents[3]
        search_paths.append((repo_root / candidate).resolve())
        # Also support resources shipped under src/app/resources when a relative path like
        # "resources/prompts/..." is provided.
        search_paths.append((repo_root / "src" / "app" / candidate).resolve())

    seen: set[Path] = set()
    for path in search_paths:
        if path in seen:
            continue
        seen.add(path)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.warning("Failed to load prompt file %s: %s", path, exc)
            return ""

    LOGGER.warning("Prompt file %s not found in project or application templates", path_str)
    return ""


def _metadata_context(metadata: Optional[ProjectMetadata]) -> Dict[str, str]:
    if not metadata:
        return {
            "subject_name": "",
            "subject_dob": "",
            "case_info": "",
            "case_name": "",
        }
    return {
        "subject_name": metadata.subject_name or metadata.case_name or "",
        "subject_dob": metadata.date_of_birth or "",
        "case_info": metadata.case_description or "",
        "case_name": metadata.case_name or "",
    }


__all__ = [
    "BulkAnalysisCancelled",
    "BulkAnalysisDocument",
    "PromptBundle",
    "combine_chunk_summaries",
    "generate_chunks",
    "load_prompts",
    "prepare_documents",
    "render_system_prompt",
    "render_user_prompt",
    "should_chunk",
]
