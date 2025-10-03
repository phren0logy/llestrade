"""Worker for executing bulk-analysis runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import Signal

from src.common.llm.base import BaseLLMProvider
from src.common.llm.factory import create_provider
from src.app.core.bulk_analysis_runner import (
    BulkAnalysisCancelled,
    BulkAnalysisDocument,
    PromptBundle,
    combine_chunk_summaries,
    generate_chunks,
    load_prompts,
    prepare_documents,
    render_system_prompt,
    render_user_prompt,
    should_chunk,
)
from src.app.core.project_manager import ProjectMetadata
from src.app.core.secure_settings import SecureSettings
from src.app.core.summary_groups import SummaryGroup
from .base import DashboardWorker


@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    model: Optional[str]


class BulkAnalysisWorker(DashboardWorker):
    """Run bulk analysis summaries on the thread pool."""

    progress = Signal(int, int, str)  # completed, total, relative path
    file_failed = Signal(str, str)  # relative path, error message
    finished = Signal(int, int)  # successes, failures
    log_message = Signal(str)

    def __init__(
        self,
        *,
        project_dir: Path,
        group: SummaryGroup,
        files: Sequence[str],
        metadata: Optional[ProjectMetadata],
        default_provider: Tuple[str, Optional[str]] = ("anthropic", None),
    ) -> None:
        super().__init__(worker_name="bulk_analysis")

        self._project_dir = project_dir
        self._group = group
        self._files = list(files)
        self._metadata = metadata
        self._default_provider = default_provider

    # ------------------------------------------------------------------
    # QRunnable API
    # ------------------------------------------------------------------
    def _run(self) -> None:  # pragma: no cover - executed in worker thread
        provider: Optional[BaseLLMProvider] = None
        successes = 0
        failures = 0

        try:
            documents = prepare_documents(self._project_dir, self._group, self._files)
            total = len(documents)
            if total == 0:
                self.log_message.emit("No documents resolved for bulk analysis run.")
                self.logger.info("%s no documents to process", self.job_tag)
                self.finished.emit(0, 0)
                return

            self.logger.info("%s starting bulk analysis (docs=%s)", self.job_tag, total)
            provider_config = self._resolve_provider()
            bundle = load_prompts(self._project_dir, self._group, self._metadata)
            system_prompt = render_system_prompt(bundle, self._metadata)
            provider = self._create_provider(provider_config, system_prompt)
            if provider is None:
                raise RuntimeError("Bulk analysis provider failed to initialise")

            for index, document in enumerate(documents, start=1):
                if self.is_cancelled():
                    raise BulkAnalysisCancelled

                try:
                    summary = self._process_document(
                        provider,
                        provider_config,
                        bundle,
                        system_prompt,
                        document,
                    )
                except BulkAnalysisCancelled:
                    raise
                except Exception as exc:  # noqa: BLE001 - propagate via signal
                    failures += 1
                    self.logger.exception("%s failed %s", self.job_tag, document.source_path)
                    self.file_failed.emit(document.relative_path, str(exc))
                else:
                    try:
                        document.output_path.parent.mkdir(parents=True, exist_ok=True)
                        document.output_path.write_text(summary, encoding="utf-8")
                    except Exception as exc:  # noqa: BLE001 - propagate via signal
                        failures += 1
                        self.logger.exception("%s write failed %s", self.job_tag, document.output_path)
                        self.file_failed.emit(document.relative_path, str(exc))
                    else:
                        successes += 1

                self.logger.debug(
                    "%s progress %s/%s %s",
                    self.job_tag,
                    successes + failures,
                    total,
                    document.relative_path,
                )
                self.progress.emit(successes + failures, total, document.relative_path)

        except BulkAnalysisCancelled:
            self.log_message.emit("Bulk analysis run cancelled.")
            self.logger.info("%s cancelled", self.job_tag)
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.exception("%s worker crashed: %s", self.job_tag, exc)
            self.log_message.emit(f"Bulk analysis worker encountered an error: {exc}")
            failures = max(failures, 1)
        finally:
            if provider and isinstance(provider, BaseLLMProvider) and hasattr(provider, "deleteLater"):
                provider.deleteLater()
            self.logger.info("%s finished: successes=%s failures=%s", self.job_tag, successes, failures)
            self.finished.emit(successes, failures)

    def cancel(self) -> None:
        super().cancel()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _process_document(
        self,
        provider: BaseLLMProvider,
        provider_config: ProviderConfig,
        bundle: PromptBundle,
        system_prompt: str,
        document: BulkAnalysisDocument,
    ) -> str:
        if self.is_cancelled():
            raise BulkAnalysisCancelled

        content = document.source_path.read_text(encoding="utf-8")
        # Allow custom context window override when set on the group
        override_window = getattr(self._group, "model_context_window", None)
        if isinstance(override_window, int) and override_window > 0:
            from src.common.llm.tokens import TokenCounter
            token_info = TokenCounter.count(
                text=content,
                provider=provider_config.provider_id,
                model=provider_config.model or "",
            )
            token_count = token_info.get("token_count") if token_info.get("success") else len(content) // 4
            max_tokens = max(int(override_window * 0.5), 4000)
            needs_chunking = token_count > max_tokens
        else:
            needs_chunking, token_count, max_tokens = should_chunk(
                content,
                provider_config.provider_id,
                provider_config.model,
            )

        self.log_message.emit(
            f"Processing {document.relative_path} ({token_count} tokens, "
            f"chunking={'yes' if needs_chunking else 'no'})"
        )
        self.logger.debug("%s processing %s tokens=%s chunking=%s", self.job_tag, document.relative_path, token_count, 'yes' if needs_chunking else 'no')

        if not needs_chunking:
            prompt = render_user_prompt(
                bundle,
                self._metadata,
                document.relative_path,
                content,
            )
            return self._invoke_provider(provider, provider_config, prompt, system_prompt)

        chunks = generate_chunks(content, max_tokens)
        if not chunks:
            prompt = render_user_prompt(
                bundle,
                self._metadata,
                document.relative_path,
                content,
            )
            return self._invoke_provider(provider, provider_config, prompt, system_prompt)

        chunk_summaries: List[str] = []
        total_chunks = len(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            if self.is_cancelled():
                raise BulkAnalysisCancelled
            chunk_prompt = render_user_prompt(
                bundle,
                self._metadata,
                document.relative_path,
                chunk,
                chunk_index=idx,
                chunk_total=total_chunks,
            )
            summary = self._invoke_provider(
                provider,
                provider_config,
                chunk_prompt,
                system_prompt,
            )
            chunk_summaries.append(summary)

        combine_prompt, _ = combine_chunk_summaries(
            chunk_summaries,
            document_name=document.relative_path,
            metadata=self._metadata,
        )
        return self._invoke_provider(provider, provider_config, combine_prompt, system_prompt)

    def _invoke_provider(
        self,
        provider: BaseLLMProvider,
        provider_config: ProviderConfig,
        prompt: str,
        system_prompt: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 32_000,
    ) -> str:
        if self._cancel_event.is_set():
            raise BulkAnalysisCancelled

        response = provider.generate(
            prompt=prompt,
            model=provider_config.model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not response.get("success"):
            raise RuntimeError(response.get("error", "Unknown LLM error"))
        content = (response.get("content") or "").strip()
        if not content:
            raise RuntimeError("LLM returned empty response")
        return content

    def _resolve_provider(self) -> ProviderConfig:
        provider_id = self._group.provider_id or self._default_provider[0] or "anthropic"
        model = self._group.model or self._default_provider[1]
        return ProviderConfig(provider_id=provider_id, model=model)

    def _create_provider(
        self,
        config: ProviderConfig,
        system_prompt: str,
    ) -> Optional[BaseLLMProvider]:
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
                f"Unable to initialise provider '{config.provider_id}'. "
                "Check API keys and model configuration in Settings."
            )
        return provider
