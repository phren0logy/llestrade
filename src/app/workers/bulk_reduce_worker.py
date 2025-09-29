"""Worker that builds a combined document and runs a single prompt."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence, Tuple

from PySide6.QtCore import Signal

from src.common.llm.base import BaseLLMProvider
from src.common.llm.factory import create_provider
from src.app.core.bulk_analysis_runner import (
    BulkAnalysisCancelled,
    PromptBundle,
    combine_chunk_summaries,
    generate_chunks,
    load_prompts,
    render_system_prompt,
    render_user_prompt,
    should_chunk,
)
from src.app.core.project_manager import ProjectMetadata
from src.app.core.summary_groups import SummaryGroup
from src.app.core.secure_settings import SecureSettings
from .base import DashboardWorker

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    model: Optional[str]
    temperature: float


class BulkReduceWorker(DashboardWorker):
    """Combine selected inputs and run a single LLM prompt to produce one output."""

    progress = Signal(int, int, str)  # completed, total, status text
    file_failed = Signal(str, str)  # path, error
    finished = Signal(int, int)  # successes, failures
    log_message = Signal(str)

    def __init__(
        self,
        *,
        project_dir: Path,
        group: SummaryGroup,
        metadata: Optional[ProjectMetadata],
    ) -> None:
        super().__init__(worker_name="bulk_reduce")
        self._project_dir = project_dir
        self._group = group
        self._metadata = metadata

    # ------------------------------------------------------------------
    # QRunnable API
    # ------------------------------------------------------------------
    def _run(self) -> None:  # pragma: no cover - executed in worker thread
        try:
            provider_cfg = self._resolve_provider()
            bundle = load_prompts(self._project_dir, self._group, self._metadata)
            system_prompt = render_system_prompt(bundle, self._metadata)

            provider = self._create_provider(provider_cfg, system_prompt)
            if provider is None:
                raise RuntimeError("Reduce provider failed to initialise")

            inputs = self._resolve_inputs()
            total = len(inputs)
            if total == 0:
                self.log_message.emit("No inputs selected for combined operation.")
                self.finished.emit(0, 0)
                return

            self.progress.emit(0, total, "Reading inputs…")
            combined_content = self._assemble_combined_content(inputs)

            if self.is_cancelled():
                raise BulkAnalysisCancelled

            # Chunk if needed
            needs_chunking, token_count, max_tokens = should_chunk(
                combined_content, provider_cfg.provider_id, provider_cfg.model
            )
            self.log_message.emit(
                f"Combined content tokens={token_count}, chunking={'yes' if needs_chunking else 'no'}"
            )

            if not needs_chunking:
                prompt = render_user_prompt(
                    bundle,
                    self._metadata,
                    self._group.name,
                    combined_content,
                )
                result = self._invoke_provider(provider, provider_cfg, prompt, system_prompt)
            else:
                chunks = generate_chunks(combined_content, max_tokens)
                if not chunks:
                    prompt = render_user_prompt(
                        bundle,
                        self._metadata,
                        self._group.name,
                        combined_content,
                    )
                    result = self._invoke_provider(provider, provider_cfg, prompt, system_prompt)
                else:
                    chunk_summaries = []
                    total_chunks = len(chunks)
                    for idx, chunk in enumerate(chunks, start=1):
                        if self.is_cancelled():
                            raise BulkAnalysisCancelled
                        prompt = render_user_prompt(
                            bundle,
                            self._metadata,
                            self._group.name,
                            chunk,
                            chunk_index=idx,
                            chunk_total=total_chunks,
                        )
                        summary = self._invoke_provider(provider, provider_cfg, prompt, system_prompt)
                        chunk_summaries.append(summary)
                    combine_prompt, _ = combine_chunk_summaries(
                        chunk_summaries,
                        document_name=self._group.name,
                        metadata=self._metadata,
                    )
                    result = self._invoke_provider(provider, provider_cfg, combine_prompt, system_prompt)

            # Persist
            output_path, manifest_path = self._output_paths()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(result, encoding="utf-8")
            manifest = self._build_manifest(inputs, provider_cfg)
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            self.progress.emit(total, total, "Completed")
            self.finished.emit(1, 0)

        except BulkAnalysisCancelled:
            self.log_message.emit("Combined operation cancelled.")
            self.finished.emit(0, 0)
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.exception("BulkReduceWorker crashed: %s", exc)
            self.log_message.emit(f"Combined operation error: {exc}")
            self.finished.emit(0, 1)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_inputs(self) -> list[tuple[str, Path, str]]:
        """Return list of (kind, abs_path, rel_key) where kind in {'converted','map'}.

        rel_key is used in the manifest:
          - converted:  "converted/<relative>"
          - map:        "map/<slug>/<relative>"
        """
        items: list[tuple[str, Path, str]] = []

        # Converted documents
        conv_root = self._project_dir / "converted_documents"
        for rel in (self._group.combine_converted_files or []):
            rel = rel.strip("/")
            if not rel:
                continue
            items.append(("converted", conv_root / rel, f"converted/{rel}"))
        for rel_dir in (self._group.combine_converted_directories or []):
            rel_dir = rel_dir.strip("/")
            base = conv_root / rel_dir
            if base.exists():
                for f in base.rglob("*.md"):
                    items.append(("converted", f, f"converted/{f.relative_to(conv_root).as_posix()}"))

        # Map outputs under bulk_analysis
        ba_root = self._project_dir / "bulk_analysis"
        for slug in (self._group.combine_map_groups or []):
            outputs = ba_root / slug / "outputs"
            if outputs.exists():
                for f in outputs.rglob("*.md"):
                    rel = f.relative_to(outputs).as_posix()
                    items.append(("map", f, f"map/{slug}/{rel}"))
        for rel_dir in (self._group.combine_map_directories or []):
            rel_dir = rel_dir.strip("/")
            parts = rel_dir.split("/", 1)
            if len(parts) != 2:
                continue
            slug, remainder = parts
            base = ba_root / slug / "outputs" / remainder
            if base.exists():
                for f in base.rglob("*.md"):
                    rel = f.relative_to(ba_root / slug / "outputs").as_posix()
                    items.append(("map", f, f"map/{slug}/{rel}"))
        for rel in (self._group.combine_map_files or []):
            rel = rel.strip("/")
            if not rel:
                continue
            parts = rel.split("/", 1)
            if len(parts) != 2:
                continue
            slug, remainder = parts
            f = ba_root / slug / "outputs" / remainder
            items.append(("map", f, f"map/{slug}/{remainder}"))

        # De-duplicate exact same files (by abs path) but keep list order stable
        seen: set[Path] = set()
        deduped: list[tuple[str, Path, str]] = []
        for kind, path, key in items:
            if path in seen:
                continue
            seen.add(path)
            deduped.append((kind, path, key))

        # Apply ordering
        order = (self._group.combine_order or "path").lower()
        if order == "mtime":
            deduped.sort(key=lambda it: it[1].stat().st_mtime if it[1].exists() else 0)
        else:
            deduped.sort(key=lambda it: it[1].as_posix())

        return deduped

    def _assemble_combined_content(self, inputs: Sequence[tuple[str, Path, str]]) -> str:
        parts: list[str] = []
        for _, abs_path, rel_key in inputs:
            if self.is_cancelled():
                raise BulkAnalysisCancelled
            try:
                text = abs_path.read_text(encoding="utf-8")
            except Exception as exc:
                self.file_failed.emit(rel_key, str(exc))
                text = ""
            # HTML comments to avoid altering markdown structure
            parts.append(f"<!--- section-begin: {rel_key} --->\n")
            parts.append(text.rstrip() + "\n")
            parts.append("<!--- section-end --->\n\n")
        return "".join(parts).rstrip() + "\n"

    def _resolve_provider(self) -> ProviderConfig:
        provider_id = self._group.provider_id or "anthropic"
        model = self._group.model or None
        temperature = 0.1
        if getattr(self._group, "use_reasoning", False):
            # crude detection for thinking models; can be refined as needed
            name = (model or "").lower()
            if "think" in name or "reason" in name:
                temperature = 1.0
        return ProviderConfig(provider_id=provider_id, model=model, temperature=temperature)

    def _create_provider(self, config: ProviderConfig, system_prompt: str) -> Optional[BaseLLMProvider]:
        settings = SecureSettings()
        api_key = settings.get_api_key(config.provider_id)
        kwargs = {
            "provider": config.provider_id,
            "default_system_prompt": system_prompt,
            "api_key": api_key,
        }
        if config.provider_id == "azure_openai":
            azure_settings = settings.get("azure_openai_settings", {}) or {}
            kwargs["azure_endpoint"] = azure_settings.get("endpoint")
            kwargs["api_version"] = azure_settings.get("api_version")
        provider = create_provider(**kwargs)
        if provider is None or not getattr(provider, "initialized", False):
            raise RuntimeError(
                f"Unable to initialise provider '{config.provider_id}'. Check API keys and model configuration in Settings."
            )
        return provider

    def _invoke_provider(
        self,
        provider: BaseLLMProvider,
        provider_cfg: ProviderConfig,
        prompt: str,
        system_prompt: str,
        *,
        max_tokens: int = 32_000,
    ) -> str:
        if self._cancel_event.is_set():
            raise BulkAnalysisCancelled
        response = provider.generate(
            prompt=prompt,
            model=provider_cfg.model,
            system_prompt=system_prompt,
            temperature=provider_cfg.temperature,
            max_tokens=max_tokens,
        )
        if not response.get("success"):
            raise RuntimeError(response.get("error", "Unknown LLM error"))
        content = (response.get("content") or "").strip()
        if not content:
            raise RuntimeError("LLM returned empty response")
        return content

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y%m%d-%H%M")

    def _output_paths(self) -> tuple[Path, Path]:
        slug = getattr(self._group, "slug", None) or self._group.folder_name
        out_dir = self._project_dir / "bulk_analysis" / slug / "reduce"
        name = (self._group.combine_output_template or "combined_{timestamp}.md").replace(
            "{timestamp}", self._timestamp()
        )
        if not name.endswith(".md"):
            name = name + ".md"
        out_md = out_dir / name
        out_manifest = out_md.with_suffix(".manifest.json")
        return out_md, out_manifest

    def _build_manifest(self, inputs: Sequence[tuple[str, Path, str]], provider_cfg: ProviderConfig) -> dict:
        manifest_inputs = []
        for _, path, key in inputs:
            try:
                mtime = int(path.stat().st_mtime)
            except OSError:
                mtime = 0
            manifest_inputs.append({"path": key, "mtime": mtime})

        return {
            "version": 1,
            "group_id": self._group.group_id,
            "group_slug": getattr(self._group, "slug", None) or self._group.folder_name,
            "timestamp": datetime.now().isoformat(),
            "inputs": manifest_inputs,
            "provider": provider_cfg.provider_id,
            "model": provider_cfg.model,
            "temperature": provider_cfg.temperature,
            "system_prompt_path": self._group.system_prompt_path,
            "user_prompt_path": self._group.user_prompt_path,
        }

