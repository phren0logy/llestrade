"""Background worker for highlight extraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from PySide6.QtCore import Signal

from src.app.core.highlight_extractor import HighlightExtractor
from src.app.core.highlights import (
    HighlightCollection,
    aggregate_highlights_by_color,
    save_color_aggregates,
    save_highlights_markdown,
    save_placeholder_markdown,
)
from src.app.core.highlight_manager import HighlightJob
from .base import DashboardWorker


@dataclass(slots=True)
class HighlightExtractionSummary:
    """Summary details produced after a highlight extraction batch."""

    generated_at: datetime
    documents_processed: int
    documents_with_highlights: int
    total_highlights: int
    color_files_written: int


class HighlightWorker(DashboardWorker):
    """Extract highlights for a batch of PDF documents."""

    progress = Signal(int, int, str)
    file_failed = Signal(str, str)
    finished = Signal(int, int)

    def __init__(self, jobs: Iterable[HighlightJob]) -> None:
        super().__init__(worker_name="highlights")
        self._jobs: List[HighlightJob] = list(jobs)
        self._extractor = HighlightExtractor()
        self.summary: Optional[HighlightExtractionSummary] = None

    def _run(self) -> None:  # pragma: no cover - executed in worker thread
        total = len(self._jobs)
        self.logger.info("%s starting extraction (jobs=%s)", self.job_tag, total)
        successes = 0
        failures = 0
        documents_with_highlights = 0
        total_highlights = 0
        collections_for_colors: List[tuple[HighlightJob, HighlightCollection]] = []
        colors_root: Optional[Path] = None
        generated_at = datetime.now(timezone.utc)

        for index, job in enumerate(self._jobs, start=1):
            if self.is_cancelled():
                self.logger.info("%s cancelled after %s/%s jobs", self.job_tag, index - 1, total)
                break

            try:
                collection = self._process_job(job)
                if collection and not collection.is_empty():
                    documents_with_highlights += 1
                    total_highlights += len(collection.highlights)
                    collections_for_colors.append((job, collection))
                    if colors_root is None:
                        colors_root = job.highlight_output.parents[2] / "colors"
                elif colors_root is None:
                    colors_root = job.highlight_output.parents[2] / "colors"
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

        color_files_written = 0
        if self.is_cancelled():
            self.summary = None
        else:
            if colors_root is not None:
                colors_root.mkdir(parents=True, exist_ok=True)
            if collections_for_colors and colors_root is not None:
                aggregates = aggregate_highlights_by_color(
                    [
                        (job.pdf_relative, collection)
                        for job, collection in collections_for_colors
                    ]
                )
                written = save_color_aggregates(
                    aggregates,
                    colors_root,
                    generated_at=generated_at,
                )
                color_files_written = len(written)
            elif colors_root is not None:
                for existing in colors_root.glob("*.md"):
                    existing.unlink()

            if total:
                self.summary = HighlightExtractionSummary(
                    generated_at=generated_at,
                    documents_processed=total,
                    documents_with_highlights=documents_with_highlights,
                    total_highlights=total_highlights,
                    color_files_written=color_files_written,
                )

        self.logger.info("%s finished: successes=%s failures=%s", self.job_tag, successes, failures)
        self.finished.emit(successes, failures)

    def _process_job(self, job: HighlightJob) -> HighlightCollection:
        collection = self._extractor.extract(job.source_pdf)

        if collection is None:
            raise RuntimeError("Highlight extraction returned no result")

        if collection.is_empty():
            save_placeholder_markdown(job.highlight_output, processed_at=datetime.now(timezone.utc))
            return collection

        save_highlights_markdown(
            collection,
            job.highlight_output,
            source_relative=job.pdf_relative,
        )
        return collection


__all__ = ["HighlightWorker", "HighlightExtractionSummary"]
