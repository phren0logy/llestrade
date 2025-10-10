"""Worker that builds a combined document and runs a single prompt."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import frontmatter

from PySide6.QtCore import Signal

from src.common.llm.base import BaseLLMProvider
from src.common.llm.factory import create_provider
from src.common.markdown import (
    PromptReference,
    SourceReference,
    apply_frontmatter,
    build_document_metadata,
    compute_file_checksum,
    infer_project_path,
)
from src.app.core.bulk_paths import (
    iter_map_outputs,
    iter_map_outputs_under,
    normalize_map_relative,
    resolve_map_output_path,
)
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
from src.app.core.bulk_analysis_groups import BulkAnalysisGroup
from src.app.core.secure_settings import SecureSettings
from src.app.core.placeholders.system import SourceFileContext, system_placeholder_map
from .base import DashboardWorker

LOGGER = logging.getLogger(__name__)


_MANIFEST_VERSION = 1

_DYNAMIC_REDUCE_KEYS: frozenset[str] = frozenset(
    {
        "document_content",
        "chunk_index",
        "chunk_total",
    }
)


def _manifest_path(project_dir: Path, group: BulkAnalysisGroup) -> Path:
    slug = getattr(group, "slug", None) or group.folder_name
    return project_dir / "bulk_analysis" / slug / "reduce" / "manifest.json"


def _default_manifest() -> Dict[str, object]:
    return {"version": _MANIFEST_VERSION, "signature": None}


def _load_manifest(path: Path) -> Dict[str, object]:
    if not path.exists():
        return _default_manifest()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_manifest()
    if not isinstance(data, dict):
        return _default_manifest()
    return {
        "version": data.get("version", _MANIFEST_VERSION),
        "signature": data.get("signature"),
        "placeholders": data.get("placeholders"),
    }


def _save_manifest(path: Path, manifest: Dict[str, object]) -> None:
    payload = {
        "version": _MANIFEST_VERSION,
        "signature": manifest.get("signature"),
        "placeholders": manifest.get("placeholders"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _compute_prompt_hash(
    bundle: PromptBundle,
    provider_cfg: ProviderConfig,
    group: BulkAnalysisGroup,
    metadata: Optional[ProjectMetadata],
    placeholder_values: Mapping[str, str] | None = None,
) -> str:
    metadata_summary: Dict[str, str] = {}
    if metadata:
        metadata_summary = {
            "case_name": metadata.case_name,
            "subject_name": metadata.subject_name,
            "date_of_birth": metadata.date_of_birth,
            "case_description": metadata.case_description,
        }
    payload = {
        "system_template": bundle.system_template,
        "user_template": bundle.user_template,
        "provider_id": provider_cfg.provider_id,
        "model": provider_cfg.model,
        "temperature": provider_cfg.temperature,
        "group_operation": group.operation,
        "use_reasoning": group.use_reasoning,
        "model_context_window": group.model_context_window,
        "system_prompt_path": group.system_prompt_path,
        "user_prompt_path": group.user_prompt_path,
        "metadata": metadata_summary,
        "placeholder_requirements": group.placeholder_requirements,
    }
    if placeholder_values:
        payload["placeholders"] = {k: placeholder_values.get(k, "") for k in sorted(placeholder_values)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _inputs_signature(inputs: Sequence[tuple[str, Path, str]]) -> list[dict[str, object]]:
    signature: list[dict[str, object]] = []
    for kind, path, rel in inputs:
        try:
            stat_result = path.stat()
            mtime = float(stat_result.st_mtime)
            mtime_ns = getattr(stat_result, "st_mtime_ns", None)
        except OSError:
            mtime = 0.0
            mtime_ns = None
        entry: dict[str, object] = {"kind": kind, "path": rel, "mtime": round(mtime, 6)}
        if mtime_ns is not None:
            try:
                entry["mtime_ns"] = int(mtime_ns)
            except (TypeError, ValueError):
                pass
        signature.append(entry)
    signature.sort(key=lambda item: (item["kind"], item["path"]))
    return signature


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
        group: BulkAnalysisGroup,
        metadata: Optional[ProjectMetadata],
        force_rerun: bool = False,
        placeholder_values: Mapping[str, str] | None = None,
        project_name: str = "",
    ) -> None:
        super().__init__(worker_name="bulk_reduce")
        self._project_dir = project_dir
        self._group = group
        self._metadata = metadata
        self._force_rerun = force_rerun
        self._base_placeholders = dict(placeholder_values or {})
        self._project_name = project_name
        self._run_timestamp = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # QRunnable API
    # ------------------------------------------------------------------
    def _build_placeholder_map(
        self,
        *,
        source: Optional[SourceFileContext] = None,
        reduce_sources: Optional[Sequence[SourceFileContext]] = None,
    ) -> Dict[str, str]:
        placeholders = dict(self._base_placeholders)
        system_values = system_placeholder_map(
            project_name=self._project_name,
            timestamp=self._run_timestamp,
            source=source,
            reduce_sources=reduce_sources,
        )
        placeholders.update(system_values)
        return placeholders

    def _enforce_placeholder_requirements(
        self,
        placeholders: Mapping[str, str],
        *,
        context: str,
        dynamic_keys: Iterable[str],
    ) -> None:
        requirements = getattr(self._group, "placeholder_requirements", None) or {}
        if not requirements:
            return

        missing_required: list[str] = []
        missing_optional: list[str] = []
        dynamic = set(dynamic_keys)

        for key, required in requirements.items():
            if key in dynamic:
                continue
            value = (placeholders.get(key) or "").strip()
            if value:
                continue
            if required:
                missing_required.append(key)
            else:
                missing_optional.append(key)

        if missing_optional:
            self.log_message.emit(
                f"{context}: optional placeholders without values: "
                + ", ".join(f"{{{name}}}" for name in sorted(missing_optional))
            )

        if missing_required:
            formatted = ", ".join(f"{{{name}}}" for name in sorted(missing_required))
            raise RuntimeError(f"{context}: required placeholders missing values: {formatted}")

    def _serialise_placeholders(self, placeholders: Mapping[str, str]) -> Dict[str, str]:
        return {key: placeholders.get(key, "") for key in sorted(placeholders)}

    def _resolve_source_context(
        self,
        *,
        relative_hint: Optional[str],
        path_hint: Optional[str],
        fallback_relative: str,
    ) -> SourceFileContext:
        rel_raw = (relative_hint or "").strip()
        path_raw = (path_hint or "").strip()

        absolute: Path
        if path_raw:
            candidate = Path(path_raw).expanduser()
            if not candidate.is_absolute():
                candidate = (self._project_dir / candidate).resolve()
            absolute = candidate
        else:
            absolute = (self._project_dir / fallback_relative).resolve()

        if not rel_raw:
            try:
                rel_raw = absolute.relative_to(self._project_dir).as_posix()
            except Exception:
                rel_raw = absolute.name

        return SourceFileContext(absolute_path=absolute, relative_path=rel_raw)

    def _extract_source_contexts(self, path: Path) -> List[SourceFileContext]:
        try:
            raw = path.read_text(encoding="utf-8")
            post = frontmatter.loads(raw)
            metadata = dict(post.metadata or {})
        except Exception:
            metadata = {}

        contexts: List[SourceFileContext] = []
        try:
            fallback_relative = path.relative_to(self._project_dir).as_posix()
        except Exception:
            fallback_relative = path.name
        sources = metadata.get("sources")
        if not sources and isinstance(metadata.get("metadata"), dict):
            sources = metadata["metadata"].get("sources")
        if isinstance(sources, list):
            for entry in sources:
                if not isinstance(entry, dict):
                    continue
                context = self._resolve_source_context(
                    relative_hint=entry.get("relative") if isinstance(entry.get("relative"), str) else None,
                    path_hint=entry.get("path") if isinstance(entry.get("path"), str) else None,
                    fallback_relative=fallback_relative,
                )
                contexts.append(context)
        if not contexts:
            rel_path = fallback_relative
            contexts.append(SourceFileContext(absolute_path=path.resolve(), relative_path=rel_path))
        unique: Dict[str, SourceFileContext] = {}
        for ctx in contexts:
            unique[ctx.relative_path] = ctx
        return list(unique.values())

    def _run(self) -> None:  # pragma: no cover - executed in worker thread
        try:
            provider_cfg = self._resolve_provider()
            bundle = load_prompts(self._project_dir, self._group, self._metadata)

            inputs = self._resolve_inputs()
            total = len(inputs)
            if total == 0:
                self.log_message.emit("No inputs selected for combined operation.")
                self.finished.emit(0, 0)
                return

            aggregate_contexts_map: Dict[str, SourceFileContext] = {}
            for _, path, _ in inputs:
                for ctx in self._extract_source_contexts(path):
                    aggregate_contexts_map[ctx.relative_path] = ctx
            aggregate_contexts = list(aggregate_contexts_map.values())

            placeholders_global = self._build_placeholder_map(reduce_sources=aggregate_contexts)

            self._enforce_placeholder_requirements(
                placeholders_global,
                context=f"combined analysis '{self._group.name}'",
                dynamic_keys=_DYNAMIC_REDUCE_KEYS,
            )

            system_prompt = render_system_prompt(
                bundle,
                self._metadata,
                placeholder_values=placeholders_global,
            )
            prompt_hash = _compute_prompt_hash(
                bundle,
                provider_cfg,
                self._group,
                self._metadata,
                placeholder_values=self._base_placeholders,
            )

            provider = self._create_provider(provider_cfg, system_prompt)
            if provider is None:
                raise RuntimeError("Reduce provider failed to initialise")

            signature_inputs = _inputs_signature(inputs)
            state_manifest_path = _manifest_path(self._project_dir, self._group)
            previous = _load_manifest(state_manifest_path)
            current_signature = {"prompt_hash": prompt_hash, "inputs": signature_inputs}

            if not self._force_rerun and previous.get("signature") == current_signature:
                self.log_message.emit("Combined inputs unchanged; skipping run.")
                self.finished.emit(0, 0)
                return

            self.log_message.emit(
                f"Starting combined bulk analysis for '{self._group.name}' ({total} input file(s))."
            )

            if total == 1:
                status_message = "Reading 1 input file…"
            else:
                status_message = f"Reading {total} input files…"
            self.progress.emit(0, 1, status_message)
            combined_content = self._assemble_combined_content(inputs)

            if self.is_cancelled():
                raise BulkAnalysisCancelled

            override_window = getattr(self._group, "model_context_window", None)
            if isinstance(override_window, int) and override_window > 0:
                from src.common.llm.tokens import TokenCounter

                token_info = TokenCounter.count(
                    text=combined_content,
                    provider=provider_cfg.provider_id,
                    model=provider_cfg.model or "",
                )
                token_count = token_info.get("token_count") if token_info.get("success") else len(combined_content) // 4
                max_tokens = max(int(override_window * 0.5), 4000)
                needs_chunking = token_count > max_tokens
            else:
                needs_chunking, token_count, max_tokens = should_chunk(
                    combined_content, provider_cfg.provider_id, provider_cfg.model
                )
            self.log_message.emit(
                f"Combined content tokens={token_count}, chunking={'yes' if needs_chunking else 'no'}"
            )

            run_details: Dict[str, object] = {
                "token_count": token_count,
                "max_tokens": max_tokens,
                "chunking": bool(needs_chunking),
            }

            if not needs_chunking:
                prompt = render_user_prompt(
                    bundle,
                    self._metadata,
                    self._group.name,
                    combined_content,
                    placeholder_values=placeholders_global,
                )
                result = self._invoke_provider(provider, provider_cfg, prompt, system_prompt)
                run_details["chunk_count"] = 1
            else:
                chunks = generate_chunks(combined_content, max_tokens)
                if not chunks:
                    prompt = render_user_prompt(
                        bundle,
                        self._metadata,
                        self._group.name,
                        combined_content,
                        placeholder_values=placeholders_global,
                    )
                    result = self._invoke_provider(provider, provider_cfg, prompt, system_prompt)
                    run_details["chunk_count"] = 1
                    run_details["chunking"] = False
                else:
                    chunk_summaries = []
                    total_chunks = len(chunks)
                    run_details["chunk_count"] = total_chunks
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
                            placeholder_values=placeholders_global,
                        )
                        summary = self._invoke_provider(provider, provider_cfg, prompt, system_prompt)
                        chunk_summaries.append(summary)
                    combine_prompt, _ = combine_chunk_summaries(
                        chunk_summaries,
                        document_name=self._group.name,
                        metadata=self._metadata,
                        placeholder_values=placeholders_global,
                    )
                    result = self._invoke_provider(provider, provider_cfg, combine_prompt, system_prompt)

            # Persist
            output_path, run_manifest_path = self._output_paths()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            written_at = datetime.now(timezone.utc)
            metadata = self._build_reduce_metadata(
                output_path=output_path,
                inputs=inputs,
                provider_cfg=provider_cfg,
                prompt_hash=prompt_hash,
                run_details=run_details,
                placeholders=placeholders_global,
                created_at=written_at,
            )
            updated = apply_frontmatter(result, metadata, merge_existing=True)
            output_path.write_text(updated, encoding="utf-8")
            run_manifest = self._build_run_manifest(inputs, provider_cfg, placeholders_global)
            run_manifest_path.write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")
            state_manifest = self._build_state_manifest(current_signature, placeholders_global)
            _save_manifest(state_manifest_path, state_manifest)

            self.progress.emit(1, 1, "Completed")
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
    def _build_reduce_metadata(
        self,
        *,
        output_path: Path,
        inputs: Sequence[tuple[str, Path, str]],
        provider_cfg: ProviderConfig,
        prompt_hash: str,
        run_details: Dict[str, object],
        placeholders: Mapping[str, str],
        created_at: datetime,
    ) -> Dict[str, object]:
        project_path = infer_project_path(output_path)
        sources = self._source_references(inputs)
        prompts = self._prompt_references()
        extra: Dict[str, object] = {
            "group_id": self._group.group_id,
            "group_name": self._group.name,
            "group_operation": self._group.operation,
            "prompt_hash": prompt_hash,
            "provider_id": provider_cfg.provider_id,
            "model": provider_cfg.model,
            "input_count": len(inputs),
        }
        extra.update(run_details)
        extra["placeholders"] = self._serialise_placeholders(placeholders)
        return build_document_metadata(
            project_path=project_path,
            generator="bulk_reduce_worker",
            created_at=created_at,
            sources=sources,
            prompts=prompts,
            extra=extra,
        )

    def _source_references(self, inputs: Sequence[tuple[str, Path, str]]) -> Sequence[SourceReference]:
        refs: List[SourceReference] = []
        for kind, path, rel in inputs:
            refs.append(
                SourceReference(
                    path=path,
                    relative=rel,
                    kind=(path.suffix.lstrip(".") or "file"),
                    role=kind,
                    checksum=compute_file_checksum(path),
                )
            )
        return refs

    def _prompt_references(self) -> Sequence[PromptReference]:
        references: List[PromptReference] = []
        system_path = (self._group.system_prompt_path or "").strip()
        if system_path:
            references.append(
                PromptReference(
                    path=self._resolve_prompt_path(system_path),
                    role="system",
                )
            )
        else:
            references.append(PromptReference(identifier="document_analysis_system_prompt", role="system"))

        user_path = (self._group.user_prompt_path or "").strip()
        if user_path:
            references.append(
                PromptReference(
                    path=self._resolve_prompt_path(user_path),
                    role="user",
                )
            )
        else:
            references.append(PromptReference(identifier="document_bulk_analysis_prompt", role="user"))

        return [ref for ref in references if ref.to_dict()]

    def _resolve_prompt_path(self, prompt_path: str) -> Path:
        candidate = Path(prompt_path)
        if candidate.is_absolute():
            return candidate
        return (self._project_dir / candidate).resolve()

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
        for slug in (self._group.combine_map_groups or []):
            slug = slug.strip()
            if not slug:
                continue
            for path, rel in iter_map_outputs(self._project_dir, slug):
                items.append(("map", path, f"map/{slug}/{rel}"))

        for rel_dir in (self._group.combine_map_directories or []):
            rel_dir = rel_dir.strip("/")
            if not rel_dir:
                continue
            parts = rel_dir.split("/", 1)
            if len(parts) != 2:
                continue
            slug, remainder = parts
            slug = slug.strip()
            if not slug:
                continue
            normalized = normalize_map_relative(remainder)
            for path, rel in iter_map_outputs_under(self._project_dir, slug, normalized):
                items.append(("map", path, f"map/{slug}/{rel}"))

        for rel in (self._group.combine_map_files or []):
            rel = rel.strip("/")
            if not rel:
                continue
            parts = rel.split("/", 1)
            if len(parts) != 2:
                continue
            slug, remainder = parts
            slug = slug.strip()
            if not slug:
                continue
            normalized = normalize_map_relative(remainder)
            if not normalized:
                continue
            path = resolve_map_output_path(self._project_dir, slug, normalized)
            items.append(("map", path, f"map/{slug}/{normalized}"))

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
        elif config.provider_id == "anthropic_bedrock":
            bedrock_settings = settings.get("aws_bedrock_settings", {}) or {}
            kwargs["aws_region"] = bedrock_settings.get("region") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
            kwargs["aws_profile"] = bedrock_settings.get("profile")
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

    def _build_state_manifest(
        self,
        signature: dict[str, object],
        placeholders: Mapping[str, str],
    ) -> dict:
        return {
            "version": _MANIFEST_VERSION,
            "group_id": self._group.group_id,
            "group_slug": getattr(self._group, "slug", None) or self._group.folder_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signature": signature,
            "placeholders": self._serialise_placeholders(placeholders),
        }

    def _build_run_manifest(
        self,
        inputs: Sequence[tuple[str, Path, str]],
        provider_cfg: ProviderConfig,
        placeholders: Mapping[str, str],
    ) -> dict:
        manifest_inputs = []
        for kind, path, rel in inputs:
            try:
                stat_result = path.stat()
                mtime = float(stat_result.st_mtime)
            except OSError:
                mtime = 0.0
            manifest_inputs.append({"kind": kind, "path": rel, "mtime": round(mtime, 6)})

        return {
            "version": 1,
            "group_id": self._group.group_id,
            "group_slug": getattr(self._group, "slug", None) or self._group.folder_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "inputs": manifest_inputs,
            "provider": provider_cfg.provider_id,
            "model": provider_cfg.model,
            "temperature": provider_cfg.temperature,
            "system_prompt_path": self._group.system_prompt_path,
            "user_prompt_path": self._group.user_prompt_path,
            "placeholders": self._serialise_placeholders(placeholders),
        }
