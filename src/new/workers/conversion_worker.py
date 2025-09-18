"""Background worker for document conversion jobs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from PySide6.QtCore import QObject, QRunnable, Signal

from src.core.file_utils import (
    extract_text_from_pdf,
    process_docx_to_markdown,
    process_txt_to_markdown,
    write_file_content,
)
from src.new.core.conversion_manager import ConversionJob, copy_existing_markdown
from src.new.core.conversion_helpers import find_helper, registry

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
        helper: str = "default",
        options: Optional[Dict[str, Any]] = None,
    ) -> None:
        QObject.__init__(self)
        QRunnable.__init__(self)
        self.setAutoDelete(True)
        self._jobs: List[ConversionJob] = list(jobs)
        self._helper_id = helper or "default"
        self._options: Dict[str, Any] = dict(options or {})
        self._cancelled = False

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
        helper = self._helper()
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
        if not self._preserve_page_markers():
            content = self._strip_page_markers(content)

        if self._include_pdf_front_matter():
            metadata = (
                "---\n"
                f"title: {job.source_path.stem}\n"
                f"source: {job.source_path.name}\n"
                f"converted_with: {self._converted_with_tag()}\n"
                "---\n\n"
            )
            output = metadata + content
        else:
            output = content

        write_file_content(str(job.destination_path), output)

    # ------------------------------------------------------------------
    # Helper settings
    # ------------------------------------------------------------------
    def _include_pdf_front_matter(self) -> bool:
        default = self._helper_id != "text_only"
        return bool(self._option_value("include_pdf_front_matter", default))

    def _preserve_page_markers(self) -> bool:
        default = self._helper_id == "default"
        return bool(self._option_value("preserve_page_markers", default))

    def _converted_with_tag(self) -> str:
        if self._helper_id == "text_only":
            return "text_only_pdf_extractor"
        return "local_pdf_extractor"

    @staticmethod
    def _strip_page_markers(content: str) -> str:
        lines = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("--- Page ") and stripped.endswith(" ---"):
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    def _helper(self):
        try:
            return find_helper(self._helper_id)
        except KeyError:
            LOGGER.warning("Unknown helper '%s', falling back to default", self._helper_id)
            return registry().default_helper()

    def _option_value(self, key: str, default: Any) -> Any:
        if key in self._options:
            return self._options[key]
        helper = self._helper()
        for option in helper.options:
            if option.key == key:
                return option.default
        return default
