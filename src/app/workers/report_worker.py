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
from src.app.core.prompt_manager import PromptManager
from src.app.core.report_template_sections import (
    TemplateSection,
    load_template_sections,
)
from src.app.core.secure_settings import SecureSettings
from src.common.llm.factory import create_provider
from src.common.llm.tokens import TokenCounter
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
        instructions: str,
        template_path: Optional[Path],
        transcript_path: Optional[Path],
        refinement_prompt_name: str,
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
        self._instructions = instructions.strip()
        self._template_path = Path(template_path) if template_path else None
        self._transcript_path = Path(transcript_path) if transcript_path else None
        self._refinement_prompt_name = refinement_prompt_name
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
            if not self._inputs and not self._transcript_path:
                raise RuntimeError(
                    "Select at least one input or provide a transcript before generating a report"
                )
            if self._transcript_path and not self._transcript_path.exists():
                raise FileNotFoundError(f"Transcript not found: {self._transcript_path}")
            if not self._instructions:
                raise RuntimeError("Refinement instructions must not be empty")

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
            inputs_path.write_text(combined_content, encoding="utf-8")
            self.log_message.emit(f"Combined inputs written to {inputs_path.name}.")

            prompt_manager = PromptManager()
            sections = load_template_sections(self._template_path)
            if not sections:
                raise RuntimeError("Template does not contain any sections to process")

            transcript_text = ""
            if self._transcript_path:
                transcript_text = self._transcript_path.read_text(encoding="utf-8").strip()

            self.log_message.emit(
                f"Generating draft content across {len(sections)} template section(s)…"
            )
            try:
                section_instructions = prompt_manager.get_template(
                    "report_generation_instructions"
                )
            except KeyError as err:
                raise RuntimeError("Missing report_generation_instructions prompt") from err

            section_outputs = self._generate_section_outputs(
                sections=sections,
                instructions=section_instructions,
                document_content=combined_content.strip(),
                transcript_text=transcript_text,
            )

            draft_content = self._combine_section_outputs(section_outputs)
            if not draft_content.strip():
                raise RuntimeError("Section generation produced empty draft content")

            draft_path.write_text(self._format_draft_header(draft_content), encoding="utf-8")
            self.log_message.emit(f"Draft saved to {draft_path.name}.")

            self.log_message.emit("Refining draft report…")
            self.progress.emit(65, "Refining draft…")
            refined_content, reasoning_content = self._run_refinement(
                prompt_manager, draft_content
            )
            refined_path.write_text(refined_content, encoding="utf-8")
            self.log_message.emit(f"Refined report saved to {refined_path.name}.")
            reasoning_written: Optional[Path] = None
            if reasoning_content:
                reasoning_path.write_text(reasoning_content, encoding="utf-8")
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
                "refinement_prompt": self._refinement_prompt_name,
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
        instructions: str,
        document_content: str,
        transcript_text: str,
    ) -> List[dict]:
        system_prompt = PromptManager().get_system_prompt()
        provider = self._create_provider(system_prompt)
        outputs: List[dict] = []

        total = len(sections)
        for index, section in enumerate(sections, start=1):
            prompt = self._render_section_prompt(
                section=section,
                instructions=instructions,
                document_content=document_content,
                transcript_text=transcript_text,
            )

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

    def _render_section_prompt(
        self,
        *,
        section: TemplateSection,
        instructions: str,
        document_content: str,
        transcript_text: str,
    ) -> str:
        parts: List[str] = []
        parts.append("<template>\n" + section.body.strip() + "\n</template>")
        if document_content:
            parts.append("<documents>\n" + document_content + "\n</documents>")
        if transcript_text:
            parts.append("<transcript>\n" + transcript_text + "\n</transcript>")
        parts.append(instructions.strip())
        return "\n\n".join(part for part in parts if part.strip()) + "\n"

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
        prompt_manager: PromptManager,
        draft_content: str,
    ) -> tuple[str, Optional[str]]:
        refinement_template = prompt_manager.get_template(self._refinement_prompt_name)
        template_section = ""
        if self._template_path and self._template_path.exists():
            template_content = self._template_path.read_text(encoding="utf-8")
            template_section = f"<template>\n{template_content}\n</template>"
        transcript_section = ""
        if self._transcript_path and self._transcript_path.exists():
            transcript_content = self._transcript_path.read_text(encoding="utf-8")
            transcript_section = f"<transcript>\n{transcript_content}\n</transcript>"

        refine_prompt = refinement_template.format(
            instructions=self._instructions,
            report_content=draft_content,
            template_section=template_section,
            transcript_section=transcript_section,
        )
        system_prompt = PromptManager().get_system_prompt()
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

    def _count_tokens(self, system_prompt: str, user_prompt: str) -> Optional[int]:
        token_info = TokenCounter.count(
            text=f"{system_prompt}\n{user_prompt}",
            provider=self._provider_id,
            model=self._custom_model or self._model,
        )
        if token_info.get("success"):
            return int(token_info.get("token_count", 0))
        return None

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
            "refinement_prompt": self._refinement_prompt_name,
            "instructions": self._instructions,
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


__all__ = ["ReportWorker"]
