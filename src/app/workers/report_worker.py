"""Worker that generates and refines reports in a single run."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from PySide6.QtCore import Signal

from src.app.core.project_manager import ProjectMetadata
from src.app.core.report_inputs import (
    REPORT_CATEGORY_BULK_COMBINED,
    REPORT_CATEGORY_BULK_MAP,
    REPORT_CATEGORY_CONVERTED,
    REPORT_CATEGORY_HIGHLIGHT_COLOR,
    REPORT_CATEGORY_HIGHLIGHT_DOCUMENT,
    category_display_name,
)
from src.app.core.refinement_prompt import (
    read_generation_prompt,
    read_refinement_prompt,
    validate_generation_prompt,
    validate_refinement_prompt,
)
from src.app.core.prompt_placeholders import format_prompt
from src.app.core.report_template_sections import (
    TemplateSection,
    load_template_sections,
)
from src.app.core.secure_settings import SecureSettings
from src.common.llm.factory import create_provider
from src.common.llm.tokens import TokenCounter
from src.common.markdown import (
    PromptReference,
    SourceReference,
    apply_frontmatter,
    build_document_metadata,
    compute_file_checksum,
)
from .base import DashboardWorker


class ReportWorker(DashboardWorker):
    """Combine selected inputs, generate a draft, and immediately refine it."""

    progress = Signal(int, str)
    log_message = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        *,
        project_dir: Path,
        inputs: Sequence[tuple[str, str]],
        provider_id: str,
        model: str,
        custom_model: Optional[str],
        context_window: Optional[int],
        template_path: Optional[Path],
        transcript_path: Optional[Path],
        generation_user_prompt_path: Path,
        refinement_user_prompt_path: Path,
        generation_system_prompt_path: Path,
        refinement_system_prompt_path: Path,
        metadata: ProjectMetadata,
        max_report_tokens: int = 60_000,
    ) -> None:
        super().__init__(worker_name="report")
        self._project_dir = project_dir
        self._inputs = list(inputs)
        self._provider_id = provider_id
        self._model = model
        self._custom_model = custom_model.strip() if custom_model else None
        self._context_window = context_window
        self._template_path = Path(template_path) if template_path else None
        self._transcript_path = Path(transcript_path) if transcript_path else None
        self._generation_user_prompt_path = Path(generation_user_prompt_path).expanduser()
        self._refinement_user_prompt_path = Path(refinement_user_prompt_path).expanduser()
        self._generation_system_prompt_path = Path(generation_system_prompt_path).expanduser()
        self._refinement_system_prompt_path = Path(refinement_system_prompt_path).expanduser()
        self._refinement_prompt_content: str = ""
        self._metadata = metadata
        self._max_report_tokens = max_report_tokens
        self._refine_usage: Optional[int] = None

    # ------------------------------------------------------------------
    # QRunnable implementation
    # ------------------------------------------------------------------
    def _run(self) -> None:  # pragma: no cover - exercised via tests
        try:
            if self._template_path is None:
                raise RuntimeError("A report template must be provided before generating a report")
            if not self._template_path.exists():
                raise FileNotFoundError(f"Report template not found: {self._template_path}")
            if not self._generation_user_prompt_path.exists():
                raise FileNotFoundError(
                    f"Generation user prompt not found: {self._generation_user_prompt_path}"
                )
            if not self._refinement_user_prompt_path.exists():
                raise FileNotFoundError(
                    f"Refinement user prompt not found: {self._refinement_user_prompt_path}"
                )
            if not self._generation_system_prompt_path.exists():
                raise FileNotFoundError(
                    f"Generation system prompt not found: {self._generation_system_prompt_path}"
                )
            if not self._refinement_system_prompt_path.exists():
                raise FileNotFoundError(
                    f"Refinement system prompt not found: {self._refinement_system_prompt_path}"
                )
            if not self._inputs and not self._transcript_path:
                raise RuntimeError(
                    "Select at least one input or provide a transcript before generating a report"
                )
            if self._transcript_path and not self._transcript_path.exists():
                raise FileNotFoundError(f"Transcript not found: {self._transcript_path}")

            timestamp = datetime.now(timezone.utc)
            report_dir = self._project_dir / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            base_name = timestamp.strftime("report-%Y%m%d-%H%M%S")
            draft_path = report_dir / f"{base_name}-draft.md"
            refined_path = report_dir / f"{base_name}-refined.md"
            reasoning_path = report_dir / f"{base_name}-reasoning.md"
            manifest_path = report_dir / f"{base_name}.manifest.json"
            inputs_path = report_dir / f"{base_name}-inputs.md"

            transcript_note = " and transcript" if self._transcript_path else ""
            self.log_message.emit(
                f"Preparing report run with {len(self._inputs)} input(s){transcript_note}."
            )
            self.progress.emit(5, "Reading inputs…")
            combined_content, inputs_metadata = self._combine_inputs()
            inputs_metadata = list(inputs_metadata)
            input_sources = self._input_sources(inputs_metadata)
            inputs_payload = build_document_metadata(
                project_path=self._project_dir,
                generator="report_worker",
                created_at=timestamp,
                sources=input_sources,
                extra={
                    "document_type": "report-inputs",
                    "input_count": len(input_sources),
                    "categories": sorted(
                        {ref.role for ref in input_sources if ref.role}
                    ),
                },
            )
            inputs_content = apply_frontmatter(combined_content, inputs_payload, merge_existing=True)
            inputs_path.write_text(inputs_content, encoding="utf-8")
            inputs_checksum = compute_file_checksum(inputs_path)
            self.log_message.emit(f"Combined inputs written to {inputs_path.name}.")

            generation_user_prompt = read_generation_prompt(self._generation_user_prompt_path)
            validate_generation_prompt(generation_user_prompt)
            refinement_user_prompt = read_refinement_prompt(self._refinement_user_prompt_path)
            validate_refinement_prompt(refinement_user_prompt)
            self._refinement_prompt_content = refinement_user_prompt

            generation_system_prompt = self._generation_system_prompt_path.read_text(
                encoding="utf-8"
            ).strip()
            refinement_system_prompt = self._refinement_system_prompt_path.read_text(
                encoding="utf-8"
            ).strip()
            if not generation_system_prompt:
                raise RuntimeError(
                    "Generation system prompt cannot be empty. Update the selected file."
                )
            if not refinement_system_prompt:
                raise RuntimeError(
                    "Refinement system prompt cannot be empty. Update the selected file."
                )

            sections = load_template_sections(self._template_path)
            if not sections:
                raise RuntimeError("Template does not contain any sections to process")

            transcript_text = ""
            if self._transcript_path:
                transcript_text = self._transcript_path.read_text(encoding="utf-8").strip()
            additional_documents = combined_content.strip()

            self.log_message.emit(
                f"Generating draft content across {len(sections)} template section(s)…"
            )

            section_outputs = self._generate_section_outputs(
                sections=sections,
                user_prompt_template=generation_user_prompt,
                additional_documents=additional_documents,
                transcript_text=transcript_text,
                system_prompt=generation_system_prompt,
            )

            draft_content = self._combine_section_outputs(section_outputs)
            if not draft_content.strip():
                raise RuntimeError("Section generation produced empty draft content")

            draft_body = self._format_draft_header(draft_content)
            draft_sources = list(input_sources)
            combined_inputs_ref = self._file_source(
                inputs_path, role="combined-inputs", checksum=inputs_checksum
            )
            if combined_inputs_ref:
                draft_sources.append(combined_inputs_ref)
            template_ref = self._optional_source(self._template_path, role="template")
            if template_ref:
                draft_sources.append(template_ref)
            transcript_ref = self._optional_source(self._transcript_path, role="transcript")
            if transcript_ref:
                draft_sources.append(transcript_ref)
            generation_prompts = [
                self._prompt_reference(self._generation_user_prompt_path, role="generation-user"),
                self._prompt_reference(self._generation_system_prompt_path, role="generation-system"),
            ]
            draft_payload = build_document_metadata(
                project_path=self._project_dir,
                generator="report_worker",
                created_at=datetime.now(timezone.utc),
                sources=draft_sources,
                prompts=[ref for ref in generation_prompts if ref.to_dict()],
                extra={
                    "document_type": "report-draft",
                    "section_count": len(section_outputs),
                },
            )
            draft_content_prepared = apply_frontmatter(draft_body, draft_payload, merge_existing=True)
            draft_path.write_text(draft_content_prepared, encoding="utf-8")
            draft_checksum = compute_file_checksum(draft_path)
            self.log_message.emit(f"Draft saved to {draft_path.name}.")

            self.log_message.emit("Refining draft report…")
            self.progress.emit(65, "Refining draft…")
            refined_content, reasoning_content = self._run_refinement(
                refinement_template=self._refinement_prompt_content,
                draft_content=draft_content,
                system_prompt=refinement_system_prompt,
            )
            refinement_prompts = [
                self._prompt_reference(self._refinement_user_prompt_path, role="refinement-user"),
                self._prompt_reference(self._refinement_system_prompt_path, role="refinement-system"),
            ]
            all_prompts = [
                ref for ref in (*generation_prompts, *refinement_prompts) if ref.to_dict()
            ]
            refined_sources = list(draft_sources)
            draft_ref = self._file_source(draft_path, role="draft", checksum=draft_checksum)
            if draft_ref:
                refined_sources.append(draft_ref)
            refined_payload = build_document_metadata(
                project_path=self._project_dir,
                generator="report_worker",
                created_at=datetime.now(timezone.utc),
                sources=refined_sources,
                prompts=all_prompts,
                extra={
                    "document_type": "report-refined",
                    "section_count": len(section_outputs),
                    "refinement_tokens": self._refine_usage,
                },
            )
            refined_content_prepared = apply_frontmatter(refined_content, refined_payload, merge_existing=True)
            refined_path.write_text(refined_content_prepared, encoding="utf-8")
            refined_checksum = compute_file_checksum(refined_path)
            self.log_message.emit(f"Refined report saved to {refined_path.name}.")
            reasoning_written: Optional[Path] = None
            if reasoning_content:
                reasoning_sources = list(refined_sources)
                refined_ref = self._file_source(refined_path, role="refined", checksum=refined_checksum)
                if refined_ref:
                    reasoning_sources.append(refined_ref)
                reasoning_payload = build_document_metadata(
                    project_path=self._project_dir,
                    generator="report_worker",
                    created_at=datetime.now(timezone.utc),
                    sources=reasoning_sources,
                    prompts=[ref for ref in refinement_prompts if ref.to_dict()],
                    extra={"document_type": "report-reasoning"},
                )
                reasoning_prepared = apply_frontmatter(reasoning_content, reasoning_payload, merge_existing=True)
                reasoning_path.write_text(reasoning_prepared, encoding="utf-8")
                reasoning_written = reasoning_path
                self.log_message.emit(f"Reasoning output saved to {reasoning_path.name}.")

            manifest = self._build_manifest(
                timestamp=timestamp,
                draft_path=draft_path,
                refined_path=refined_path,
                reasoning_path=reasoning_written,
                inputs_path=inputs_path,
                inputs_metadata=inputs_metadata,
                draft_tokens=None,
                refined_tokens=self._refine_usage,
                sections=section_outputs,
            )
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            self.log_message.emit(f"Manifest written to {manifest_path.name}.")

            result = {
                "timestamp": timestamp.isoformat(),
                "draft_path": str(draft_path),
                "refined_path": str(refined_path),
                "reasoning_path": str(reasoning_written) if reasoning_written else None,
                "manifest_path": str(manifest_path),
                "inputs_path": str(inputs_path),
                "provider": self._provider_id,
                "model": self._custom_model or self._model,
                "custom_model": self._custom_model,
                "context_window": self._context_window,
                "inputs": [item[1] for item in self._inputs],
                "generation_user_prompt": str(self._generation_user_prompt_path),
                "refinement_user_prompt": str(self._refinement_user_prompt_path),
                "generation_system_prompt": str(self._generation_system_prompt_path),
                "refinement_system_prompt": str(self._refinement_system_prompt_path),
                "instructions": self._refinement_prompt_content,
            }
            self.progress.emit(100, "Report generated")
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(str(exc))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _combine_inputs(self) -> tuple[str, List[dict]]:
        lines: List[str] = []
        metadata: List[dict] = []
        for category, relative in self._inputs:
            absolute = (self._project_dir / relative).resolve()
            if not absolute.exists():
                raise FileNotFoundError(f"Selected input missing: {relative}")
            if absolute.suffix.lower() not in {".md", ".txt"}:
                raise RuntimeError(f"Unsupported input type: {relative}")
            content = absolute.read_text(encoding="utf-8")
            section_header = self._render_section_header(category, relative)
            lines.append(f"<!--- report-input: {category} | {relative} --->")
            lines.append(section_header)
            lines.append(content.strip())
            lines.append("")
            token_info = TokenCounter.count(
                text=content,
                provider=self._provider_id,
                model=self._custom_model or self._model,
            )
            token_count = (
                int(token_info.get("token_count"))
                if token_info.get("success") and token_info.get("token_count") is not None
                else max(len(content) // 4, 1)
            )
            metadata.append(
                {
                    "category": category,
                    "relative_path": relative,
                    "absolute_path": str(absolute),
                    "token_count": token_count,
                }
            )
        if not lines:
            return "", metadata
        combined = "\n".join(lines).strip() + "\n"
        return combined, metadata

    def _render_section_header(self, category: str, relative: str) -> str:
        title = category_display_name(category)
        return f"# {title}: {relative}\n"

    def _generate_section_outputs(
        self,
        *,
        sections: Sequence[TemplateSection],
        user_prompt_template: str,
        additional_documents: str,
        transcript_text: str,
        system_prompt: str,
    ) -> List[dict]:
        provider = self._create_provider(system_prompt)
        outputs: List[dict] = []

        total = len(sections)
        for index, section in enumerate(sections, start=1):
            context = {
                "template_section": section.body.strip(),
                "transcript": transcript_text,
                "additional_documents": additional_documents,
                "document_content": additional_documents,
                "section_title": section.title,
            }
            prompt = format_prompt(user_prompt_template, context)

            pct = 5 + int(40 * index / max(total, 1))
            self.progress.emit(pct, f"Generating section {index} of {total}: {section.title}")
            response = provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                model=self._custom_model or self._model,
                temperature=0.2,
                max_tokens=self._max_report_tokens,
            )
            if not response.get("success"):
                raise RuntimeError(
                    response.get("error", f"Failed to generate section: {section.title}")
                )
            content = (response.get("content") or "").strip()
            if not content:
                raise RuntimeError(f"Generated section is empty: {section.title}")
            outputs.append(
                {
                    "title": section.title,
                    "prompt": prompt,
                    "content": content,
                }
            )
            self.log_message.emit(f"Section generated: {section.title}")

        return outputs

    def _combine_section_outputs(self, outputs: Sequence[dict]) -> str:
        combined_sections = []
        for payload in outputs:
            content = payload.get("content", "").strip()
            if content:
                combined_sections.append(content)
        return "\n\n".join(combined_sections)

    def _format_draft_header(self, content: str) -> str:
        metadata = self._metadata or ProjectMetadata(case_name="")
        subject = metadata.subject_name or metadata.case_name or "Unknown"
        dob = metadata.date_of_birth or "Unknown"
        generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
        header = (
            "# Integrated Report\n\n"
            f"**Subject**: {subject}\n\n"
            f"**Date of Birth**: {dob}\n\n"
            f"**Generated**: {generated}\n\n"
        )
        return header + content.strip() + "\n"

    def _invoke_provider(
        self,
        *,
        prompt: str,
        system_prompt: str,
        max_tokens: int,
    ) -> dict:
        provider = self._create_provider(system_prompt)
        model = self._custom_model or self._model
        response = provider.generate(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=max_tokens,
        )
        if not response.get("success"):
            raise RuntimeError(response.get("error", "Unknown error generating draft"))
        return response

    def _create_provider(self, system_prompt: str):
        settings = SecureSettings()
        api_key = settings.get_api_key(self._provider_id)
        kwargs = {
            "provider": self._provider_id,
            "default_system_prompt": system_prompt,
            "api_key": api_key,
        }
        if self._provider_id == "azure_openai":
            azure_settings = settings.get("azure_openai_settings", {}) or {}
            kwargs["azure_endpoint"] = azure_settings.get("endpoint")
            kwargs["api_version"] = azure_settings.get("api_version")
        provider = create_provider(**kwargs)
        if provider is None or not getattr(provider, "initialized", False):
            raise RuntimeError(
                f"Unable to initialise provider '{self._provider_id}'. Check API keys and configuration."
            )
        return provider

    def _run_refinement(
        self,
        *,
        refinement_template: str,
        draft_content: str,
        system_prompt: str,
    ) -> tuple[str, Optional[str]]:
        template_raw = ""
        if self._template_path and self._template_path.exists():
            template_raw = self._template_path.read_text(encoding="utf-8")
        transcript_raw = ""
        if self._transcript_path and self._transcript_path.exists():
            transcript_raw = self._transcript_path.read_text(encoding="utf-8")

        refine_prompt = format_prompt(
            refinement_template,
            {
                "draft_report": draft_content,
                "template": template_raw,
                "transcript": transcript_raw,
            },
        )
        provider = self._create_provider(system_prompt)
        model = self._custom_model or self._model
        response = provider.generate(
            prompt=refine_prompt,
            model=model,
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=self._max_report_tokens,
        )
        if not response.get("success"):
            raise RuntimeError(response.get("error", "Unknown error during refinement"))
        content = (response.get("content") or "").strip()
        if not content:
            raise RuntimeError("Refinement step returned empty content")
        reasoning = response.get("reasoning") or response.get("thinking")
        self._refine_usage = response.get("usage", {}).get("output_tokens")
        return content + "\n", reasoning

    def _build_manifest(
        self,
        *,
        timestamp: datetime,
        draft_path: Path,
        refined_path: Path,
        reasoning_path: Optional[Path],
        inputs_path: Path,
        inputs_metadata: Iterable[dict],
        draft_tokens: Optional[int],
        refined_tokens: Optional[int],
        sections: Sequence[dict],
    ) -> dict:
        return {
            "version": 1,
            "timestamp": timestamp.isoformat(),
            "provider": self._provider_id,
            "model": self._model,
            "custom_model": self._custom_model,
            "context_window": self._context_window,
            "draft_path": str(draft_path),
            "refined_path": str(refined_path),
            "reasoning_path": str(reasoning_path) if reasoning_path else None,
            "inputs_path": str(inputs_path),
            "template_path": str(self._template_path) if self._template_path else None,
            "transcript_path": str(self._transcript_path) if self._transcript_path else None,
            "generation_user_prompt": str(self._generation_user_prompt_path),
            "refinement_user_prompt": str(self._refinement_user_prompt_path),
            "generation_system_prompt": str(self._generation_system_prompt_path),
            "refinement_system_prompt": str(self._refinement_system_prompt_path),
            "instructions": self._refinement_prompt_content,
            "inputs": list(inputs_metadata),
            "sections": [
                {
                    "title": payload.get("title"),
                    "content": payload.get("content"),
                }
                for payload in sections
            ],
            "usage": {
                "draft_tokens": draft_tokens,
                "refined_tokens": refined_tokens,
            },
        }

    def _input_sources(self, items: Sequence[dict]) -> List[SourceReference]:
        sources: List[SourceReference] = []
        for item in items:
            absolute_raw = item.get("absolute_path")
            if not absolute_raw:
                continue
            abs_path = Path(absolute_raw).expanduser()
            relative = item.get("relative_path") or self._relative_to_project(abs_path)
            category = item.get("category") or "input"
            sources.append(
                SourceReference(
                    path=abs_path,
                    relative=relative,
                    kind=(abs_path.suffix.lstrip(".") or "file"),
                    role=category,
                    checksum=compute_file_checksum(abs_path),
                )
            )
        return sources

    def _optional_source(self, path: Optional[Path], *, role: str) -> Optional[SourceReference]:
        if path is None:
            return None
        return self._file_source(path, role=role)

    def _file_source(
        self,
        path: Optional[Path],
        *,
        role: str,
        checksum: Optional[str] = None,
    ) -> Optional[SourceReference]:
        if path is None:
            return None
        return SourceReference(
            path=path,
            relative=self._relative_to_project(path),
            kind=(path.suffix.lstrip(".") or "file"),
            role=role,
            checksum=checksum or compute_file_checksum(path),
        )

    def _prompt_reference(self, path: Path, *, role: str) -> PromptReference:
        return PromptReference(path=path, role=role)

    def _relative_to_project(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self._project_dir.resolve()).as_posix()
        except Exception:
            return path.name


__all__ = ["ReportWorker"]
