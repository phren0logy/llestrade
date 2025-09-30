"""Background worker for highlight extraction."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List

from PySide6.QtCore import Signal

from src.app.core.highlight_extractor import HighlightExtractor
from src.app.core.highlights import (
    HighlightCollection,
    save_highlights_markdown,
    save_placeholder_markdown,
)
from src.app.core.highlight_manager import HighlightJob
from .base import DashboardWorker


class HighlightWorker(DashboardWorker):
    """Extract highlights for a batch of PDF documents."""

    progress = Signal(int, int, str)
    file_failed = Signal(str, str)
    finished = Signal(int, int)

    def __init__(self, jobs: Iterable[HighlightJob]) -> None:
        super().__init__(worker_name="highlights")
        self._jobs: List[HighlightJob] = list(jobs)
        self._extractor = HighlightExtractor()

    def _run(self) -> None:  # pragma: no cover - executed in worker thread
        total = len(self._jobs)
        self.logger.info("%s starting extraction (jobs=%s)", self.job_tag, total)
        successes = 0
        failures = 0
        for index, job in enumerate(self._jobs, start=1):
            if self.is_cancelled():
                self.logger.info("%s cancelled after %s/%s jobs", self.job_tag, index - 1, total)
                break

            try:
                self._process_job(job)
            except Exception as exc:  # noqa: BLE001 - surface via signal
                failures += 1
                self.logger.exception("%s failed %s", self.job_tag, job.source_pdf)
                self.file_failed.emit(str(job.source_pdf), str(exc))
            else:
                successes += 1
            finally:
                self.logger.debug(
                    "%s progress %s/%s %s",
                    self.job_tag,
                    successes + failures,
                    total,
                    job.converted_relative,
                )
                self.progress.emit(successes + failures, total, job.converted_relative)
        self.logger.info("%s finished: successes=%s failures=%s", self.job_tag, successes, failures)
        self.finished.emit(successes, failures)

    def _process_job(self, job: HighlightJob) -> None:
        collection = self._extractor.extract(job.source_pdf)

        if collection is None:
            raise RuntimeError("Highlight extraction returned no result")

        if collection.is_empty():
            save_placeholder_markdown(job.highlight_output, processed_at=datetime.now(timezone.utc))
            return

        save_highlights_markdown(collection, job.highlight_output)


__all__ = ["HighlightWorker"]
