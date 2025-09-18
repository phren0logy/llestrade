"""Background worker for document conversion jobs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from PySide6.QtCore import QObject, QRunnable, Signal

from src.core.file_utils import (
    extract_text_from_pdf,
    process_docx_to_markdown,
    write_file_content,
)
from src.new.core.conversion_manager import ConversionJob, copy_existing_markdown
from src.new.core.conversion_helpers import ConversionHelper, registry
from src.new.core.secure_settings import SecureSettings

LOGGER = logging.getLogger(__name__)


class ConversionWorker(QObject, QRunnable):
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
        QObject.__init__(self)
        QRunnable.__init__(self)
        self.setAutoDelete(True)
        self._jobs: List[ConversionJob] = list(jobs)
        self._helper_id = helper or "azure_di"
        self._cancelled = False
        self._helper_cache: Optional[ConversionHelper] = None

    def run(self) -> None:  # pragma: no cover - executed in worker thread
        total = len(self._jobs)
        successes = 0
        failures = 0
        for index, job in enumerate(self._jobs, start=1):
            if self._cancelled:
                break
            try:
                self._execute(job)
            except Exception as exc:  # noqa: BLE001 - propagate via signal
                failures += 1
                LOGGER.exception("Conversion failed for %s", job.source_path)
                self.file_failed.emit(str(job.source_path), str(exc))
            else:
                successes += 1
            finally:
                self.progress.emit(successes + failures, total, job.display_name)
        self.finished.emit(successes, failures)

    def cancel(self) -> None:
        self._cancelled = True

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
        if produced != job.destination_path:
            if job.destination_path.exists():
                job.destination_path.unlink()
            produced.rename(job.destination_path)

    def _convert_pdf_locally(self, job: ConversionJob) -> None:
        job.destination_path.parent.mkdir(parents=True, exist_ok=True)
        content = extract_text_from_pdf(str(job.source_path))
        write_file_content(str(job.destination_path), content)

    def _convert_pdf_with_azure(self, job: ConversionJob) -> None:
        endpoint, key = self._azure_credentials()
        output_dir = job.destination_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        json_dir = output_dir / ".azure-di"
        json_dir.mkdir(parents=True, exist_ok=True)

        json_path, markdown_path = self._process_with_azure(
            job.source_path,
            output_dir,
            json_dir,
            endpoint,
            key,
        )

        produced = Path(markdown_path)
        if produced != job.destination_path:
            if job.destination_path.exists():
                job.destination_path.unlink()
            produced.rename(job.destination_path)

        LOGGER.debug("Azure DI JSON saved to %s", json_path)

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
            str(json_dir),
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
