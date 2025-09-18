"""Background worker for document conversion jobs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List

from PySide6.QtCore import QObject, QRunnable, Signal

from src.core.file_utils import (
    extract_text_from_pdf,
    process_docx_to_markdown,
    process_txt_to_markdown,
    write_file_content,
)
from src.new.core.conversion_manager import ConversionJob, copy_existing_markdown

LOGGER = logging.getLogger(__name__)


class ConversionWorker(QObject, QRunnable):
    """Run conversion jobs on a thread pool."""

    progress = Signal(int, int, str)  # completed, total, relative path
    file_failed = Signal(str, str)    # source path, error message
    finished = Signal(int, int)       # successful, failed

    def __init__(self, jobs: Iterable[ConversionJob], helper: str = "default") -> None:
        QObject.__init__(self)
        QRunnable.__init__(self)
        self.setAutoDelete(True)
        self._jobs: List[ConversionJob] = list(jobs)
        self._helper = helper

    def run(self) -> None:  # pragma: no cover - executed in worker thread
        total = len(self._jobs)
        successes = 0
        failures = 0
        for index, job in enumerate(self._jobs, start=1):
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _execute(self, job: ConversionJob) -> None:
        conversion_type = job.conversion_type
        if conversion_type == "copy":
            self._copy_markdown(job)
        elif conversion_type == "text":
            self._convert_text(job)
        elif conversion_type == "docx":
            self._convert_docx(job)
        elif conversion_type == "pdf":
            self._convert_pdf(job)
        else:
            raise ValueError(f"Unsupported conversion type: {conversion_type}")

    def _copy_markdown(self, job: ConversionJob) -> None:
        copy_existing_markdown(job.source_path, job.destination_path)

    def _convert_text(self, job: ConversionJob) -> None:
        job.destination_path.parent.mkdir(parents=True, exist_ok=True)
        output_dir = job.destination_path.parent
        produced = Path(process_txt_to_markdown(str(job.source_path), str(output_dir)))
        if produced != job.destination_path:
            if job.destination_path.exists():
                job.destination_path.unlink()
            produced.rename(job.destination_path)

    def _convert_docx(self, job: ConversionJob) -> None:
        job.destination_path.parent.mkdir(parents=True, exist_ok=True)
        output_dir = job.destination_path.parent
        produced = Path(process_docx_to_markdown(str(job.source_path), str(output_dir)))
        if produced != job.destination_path:
            if job.destination_path.exists():
                job.destination_path.unlink()
            produced.rename(job.destination_path)

    def _convert_pdf(self, job: ConversionJob) -> None:
        job.destination_path.parent.mkdir(parents=True, exist_ok=True)
        content = extract_text_from_pdf(str(job.source_path))
        metadata = (
            "---\n"
            f"title: {job.source_path.stem}\n"
            f"source: {job.source_path.name}\n"
            "converted_with: local_pdf_extractor\n"
            "---\n\n"
        )
        write_file_content(str(job.destination_path), metadata + content)
