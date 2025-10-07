"""Background worker for document conversion jobs.

Adds standardised YAML front matter and page markers to PDF/DOCX conversions:
- Front matter describes project context, source documents, converter details, and page counts.
- Page markers for PDFs are emitted as HTML comments:
  <!--- <project_rel_source>.pdf#page=N --->
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from PySide6.QtCore import Signal

from src.common.markdown import (
    SourceReference,
    apply_frontmatter,
    build_document_metadata,
    compute_file_checksum,
)
from src.core.file_utils import (
    extract_text_from_pdf,
    process_docx_to_markdown,
    write_file_content,
)
from src.app.core.conversion_manager import ConversionJob, copy_existing_markdown
from src.app.core.conversion_helpers import ConversionHelper, registry
from src.app.core.secure_settings import SecureSettings
from .base import DashboardWorker


class ConversionWorker(DashboardWorker):
    """Run conversion jobs on a thread pool."""

    progress = Signal(int, int, str)  # completed, total, relative path
    file_failed = Signal(str, str)    # source path, error message
    finished = Signal(int, int)       # successful, failed

    def __init__(
        self,
        jobs: Iterable[ConversionJob],
        *,
        helper: str = "azure_di",
        options: Optional[Dict[str, object]] = None,
    ) -> None:
        super().__init__(worker_name="conversion")
        self._jobs: List[ConversionJob] = list(jobs)
        self._helper_id = helper or "azure_di"
        self._options = dict(options or {})
        self._helper_cache: Optional[ConversionHelper] = None

    def _run(self) -> None:  # pragma: no cover - executed in worker thread
        total = len(self._jobs)
        self.logger.info("%s starting conversion (jobs=%s)", self.job_tag, total)
        successes = 0
        failures = 0
        for job in self._jobs:
            if self.is_cancelled():
                self.logger.info("%s cancelled after %s/%s jobs", self.job_tag, successes + failures, total)
                break
            try:
                self._execute(job)
            except Exception as exc:  # noqa: BLE001 - propagate via signal
                failures += 1
                self.logger.exception("%s failed %s", self.job_tag, job.source_path)
                self.file_failed.emit(str(job.source_path), str(exc))
            else:
                successes += 1
            finally:
                self.logger.debug(
                    "%s progress %s/%s %s",
                    self.job_tag,
                    successes + failures,
                    total,
                    job.display_name,
                )
                self.progress.emit(successes + failures, total, job.display_name)
        self.logger.info("%s finished: successes=%s failures=%s", self.job_tag, successes, failures)
        self.finished.emit(successes, failures)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _execute(self, job: ConversionJob) -> None:
        conversion_type = job.conversion_type
        if conversion_type == "copy":
            self._copy_markdown(job)
        elif conversion_type == "docx":
            self._convert_docx(job)
        elif conversion_type == "pdf":
            if self._use_azure():
                self._convert_pdf_with_azure(job)
            else:
                self._convert_pdf_locally(job)
        else:
            raise ValueError(f"Unsupported conversion type: {conversion_type}")

    def _copy_markdown(self, job: ConversionJob) -> None:
        copy_existing_markdown(job.source_path, job.destination_path)

    def _convert_docx(self, job: ConversionJob) -> None:
        job.destination_path.parent.mkdir(parents=True, exist_ok=True)
        output_dir = job.destination_path.parent
        produced = Path(process_docx_to_markdown(str(job.source_path), str(output_dir)))
        # Ensure final path
        final_path = job.destination_path
        if produced != final_path:
            if final_path.exists():
                final_path.unlink()
            produced.rename(final_path)
        # Inject YAML front-matter
        try:
            content = final_path.read_text(encoding="utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.warning("Failed to read DOCX conversion for metadata injection: %s", exc)
            return
        metadata = self._conversion_metadata(
            job,
            source_format="docx",
            pages_detected=None,
            pages_pdf=None,
            converter="docx-pandoc",
        )
        updated = apply_frontmatter(content, metadata, merge_existing=True)
        final_path.write_text(updated, encoding="utf-8")

    def _convert_pdf_locally(self, job: ConversionJob) -> None:
        job.destination_path.parent.mkdir(parents=True, exist_ok=True)
        raw = extract_text_from_pdf(str(job.source_path))
        # Replace legacy page markers with HTML comments carrying project-relative path
        source_rel = self._project_relative(job)
        # Pattern like: --- Page N --- at start of a line
        def _repl(match: re.Match) -> str:
            n = match.group(1)
            return f"<!--- {source_rel}#page={n} --->\n"

        content = re.sub(r"^---\s*Page\s*(\d+)\s*---\s*$", _repl, raw, flags=re.MULTILINE)
        # Inject YAML front-matter with page count (count of markers)
        pages_detected = len(re.findall(r"<!---\s*.+#page=\d+\s*--->", content)) or 0
        # Count pages via PyMuPDF as a sanity check
        try:
            import fitz  # PyMuPDF
            pages_pdf = len(fitz.open(job.source_path))
        except Exception:
            pages_pdf = None
        metadata = self._conversion_metadata(
            job,
            source_format="pdf",
            pages_detected=pages_detected or None,
            pages_pdf=pages_pdf,
            converter="pdf-local",
        )
        self._warn_if_page_mismatch(job, pages_detected, pages_pdf)
        updated = apply_frontmatter(content, metadata, merge_existing=True)
        write_file_content(str(job.destination_path), updated)

    def _convert_pdf_with_azure(self, job: ConversionJob) -> None:
        endpoint, key = self._azure_credentials()
        output_dir = job.destination_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        # NOTE: Azure DI JSON export is temporarily disabled. Keep this block commented so we can
        #       restore the raw output if downstream tooling needs it again.
        # json_dir = output_dir / ".azure-di"
        # json_dir.mkdir(parents=True, exist_ok=True)
        json_dir = None

        json_path, markdown_path = self._process_with_azure(
            job.source_path,
            output_dir,
            json_dir,
            endpoint,
            key,
        )

        produced = Path(markdown_path)
        final_path = job.destination_path
        if produced != final_path:
            if final_path.exists():
                final_path.unlink()
            produced.rename(final_path)

        # Insert page markers by parsing Azure DI markdown, then inject YAML front-matter
        try:
            content = final_path.read_text(encoding="utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.warning("Failed to read Azure DI markdown for page markers: %s", exc)
            return
        source_rel = self._project_relative(job)
        content_marked, pages_detected = self._insert_azure_page_markers(content, source_rel)
        try:
            import fitz  # PyMuPDF
            pages_pdf = len(fitz.open(job.source_path))
        except Exception:
            pages_pdf = None
        converter_tag = f"pdf-{self._helper_id.replace('_', '-')}"
        metadata = self._conversion_metadata(
            job,
            source_format="pdf",
            pages_detected=pages_detected or None,
            pages_pdf=pages_pdf,
            converter=converter_tag,
        )
        updated = apply_frontmatter(content_marked, metadata, merge_existing=True)
        final_path.write_text(updated, encoding="utf-8")
        self._warn_if_page_mismatch(job, pages_detected, pages_pdf)

        if json_path:
            self.logger.debug("%s Azure DI JSON saved to %s", self.job_tag, json_path)

    def _azure_credentials(self) -> tuple[str, str]:
        settings = SecureSettings()
        endpoint = (settings.get("azure_di_settings", {}) or {}).get("endpoint", "")
        key = settings.get_api_key("azure_di")
        if not endpoint or not key:
            raise RuntimeError(
                "Azure Document Intelligence credentials are not configured. "
                "Set the endpoint and API key in Settings → Azure Services."
            )
        return endpoint, key

    def _process_with_azure(
        self,
        source_path: Path,
        output_dir: Path,
        json_dir: Path,
        endpoint: str,
        key: str,
    ) -> tuple[str, str]:
        try:
            from src.core.pdf_utils import process_pdf_with_azure
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Azure Document Intelligence dependencies are not installed. "
                "Install azure-ai-documentintelligence to enable this helper."
            ) from exc

        return process_pdf_with_azure(
            str(source_path),
            str(output_dir),
            str(json_dir) if json_dir is not None else None,
            str(output_dir),
            endpoint,
            key,
        )

    def _use_azure(self) -> bool:
        return self._helper_id == "azure_di"

    def _helper(self) -> ConversionHelper:
        if self._helper_cache is not None:
            return self._helper_cache
        helper = registry().get(self._helper_id)
        if helper is None:
            helper = registry().default_helper()
        self._helper_cache = helper
        return helper

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------
    def _project_relative(self, job: ConversionJob) -> str:
        """Return project-relative path to the source file for page markers."""
        _, relative = self._project_context(job)
        return relative

    def _project_context(self, job: ConversionJob) -> tuple[Path | None, str]:
        """Return project directory (if resolved) and project-relative source path."""
        dest = job.destination_path.resolve()
        parts = dest.parts
        try:
            idx = parts.index("converted_documents")
        except ValueError:
            return None, job.source_path.name

        project_dir = Path(*parts[:idx])
        project_resolved = project_dir.resolve()
        source_resolved = job.source_path.resolve()
        try:
            rel = source_resolved.relative_to(project_resolved).as_posix()
        except Exception:
            # Fallback to os.path.relpath with potential .. segments
            import os as _os

            rel = Path(_os.path.relpath(source_resolved, project_resolved)).as_posix()
        return project_dir, rel

    def _conversion_metadata(
        self,
        job: ConversionJob,
        *,
        source_format: str,
        pages_detected: int | None,
        pages_pdf: int | None,
        converter: str,
    ) -> Dict[str, object]:
        project_dir, source_rel = self._project_context(job)
        checksum = compute_file_checksum(job.source_path)
        try:
            mtime_int = int(job.source_path.stat().st_mtime)
        except Exception:
            mtime = None
        else:
            mtime = datetime.fromtimestamp(mtime_int, timezone.utc).isoformat()

        extra: Dict[str, object] = {
            "source_format": source_format,
            "source_mtime": mtime,
            "pages_detected": pages_detected,
            "pages_pdf": pages_pdf,
            "converter": converter,
        }

        metadata = build_document_metadata(
            project_path=project_dir,
            generator="conversion_worker",
            sources=[
                SourceReference(
                    path=job.source_path,
                    relative=source_rel,
                    kind=source_format,
                    role="primary",
                    checksum=checksum,
                )
            ],
            extra=extra,
        )
        return metadata

    def _insert_azure_page_markers(self, markdown: str, source_rel: str) -> tuple[str, int]:
        """Attempt to insert page markers into Azure DI Markdown by parsing headings.

        Heuristics (Markdown only, no JSON):
        - Replace lines like "--- Page N ---" with HTML comment markers
        - Insert a marker before lines matching heading patterns: "# Page N" or "## Page N"
        If no markers are found, return original content with zero count.
        """
        lines = markdown.splitlines()
        out: list[str] = []
        count = 0
        # --- Page N ---
        page_pat1 = re.compile(r"^---\s*Page\s*(\d+)\s*---\s*$", re.IGNORECASE)
        # # Page N / ## Page N / ### Page N
        page_pat2 = re.compile(r"^\s*#{1,3}\s*Page\s+(\d+)\s*$", re.IGNORECASE)
        # Page N of M (as standalone line)
        page_pat3 = re.compile(r"^\s*Page\s+(\d+)\s+(?:of|/)\s*\d+\s*$", re.IGNORECASE)
        # **Page N** standalone
        page_pat4 = re.compile(r"^\s*\*\*\s*Page\s+(\d+)\s*\*\*\s*$", re.IGNORECASE)
        # Lines like — Page N — or -- Page N -- using various dashes
        dash = "\u2012\u2013\u2014\-"  # figure/en/en em dashes and hyphen
        page_pat5 = re.compile(rf"^[{dash}\s]*Page\s+(\d+)[{dash}\s]*$", re.IGNORECASE)

        # Azure default emits explicit page breaks as HTML comments
        pagebreak_pat = re.compile(r"^\s*<!--\s*PageBreak\s*-->\s*$", re.IGNORECASE)
        pagenum_misc_pat = re.compile(r"^\s*<!--\s*PageNumber=.*-->\s*$", re.IGNORECASE)

        # Start with a page 1 marker at the very beginning
        out.append(f"<!--- {source_rel}#page=1 --->")
        count += 1
        current_page = 1

        for line in lines:
            if pagenum_misc_pat.match(line):
                # Skip non-page-number metadata comments
                continue
            if pagebreak_pat.match(line):
                current_page += 1
                out.append(f"<!--- {source_rel}#page={current_page} --->")
                count += 1
                continue
            out.append(line)

        return "\n".join(out) + "\n", count

    def _warn_if_page_mismatch(self, job, pages_detected: int | None, pages_pdf: int | None) -> None:
        if pages_detected is None or pages_pdf is None:
            return
        if pages_detected != pages_pdf:
            self.logger.warning(
                "Page count mismatch for %s: detected=%s, pdf=%s",
                job.source_path.name,
                pages_detected,
                pages_pdf,
            )
