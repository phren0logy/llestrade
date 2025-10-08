"""Services for orchestrating report generation workers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from shiboken6 import isValid

from src.app.core.project_manager import ProjectMetadata
from src.app.workers import WorkerCoordinator
from src.app.workers.report_worker import ReportWorker


@dataclass(slots=True)
class ReportJobConfig:
    """Configuration payload required to launch a report worker."""

    project_dir: Path
    inputs: Sequence[tuple[str, str]]
    provider_id: str
    model: str
    custom_model: Optional[str]
    context_window: Optional[int]
    template_path: Path
    transcript_path: Optional[Path]
    generation_user_prompt_path: Path
    refinement_user_prompt_path: Path
    generation_system_prompt_path: Path
    refinement_system_prompt_path: Path
    metadata: ProjectMetadata
    max_report_tokens: int = 60_000


class ReportsService:
    """Create and manage report workers on behalf of the UI controller."""

    _WORKER_KEY = "report:run"

    def __init__(self, workers: WorkerCoordinator) -> None:
        self._workers = workers

    def is_running(self) -> bool:
        return self._workers.get(self._WORKER_KEY) is not None

    def run(
        self,
        config: ReportJobConfig,
        *,
        on_started: Callable[[], None],
        on_progress: Callable[[int, str], None],
        on_log: Callable[[str], None],
        on_finished: Callable[[dict], None],
        on_failed: Callable[[str], None],
    ) -> bool:
        if self.is_running():
            return False

        worker = ReportWorker(
            project_dir=config.project_dir,
            inputs=list(config.inputs),
            provider_id=config.provider_id,
            model=config.model,
            custom_model=config.custom_model,
            context_window=config.context_window,
            template_path=config.template_path,
            transcript_path=config.transcript_path,
            generation_user_prompt_path=config.generation_user_prompt_path,
            refinement_user_prompt_path=config.refinement_user_prompt_path,
            generation_system_prompt_path=config.generation_system_prompt_path,
            refinement_system_prompt_path=config.refinement_system_prompt_path,
            metadata=config.metadata,
            max_report_tokens=config.max_report_tokens,
        )

        worker.progress.connect(on_progress)
        worker.log_message.connect(on_log)
        worker.finished.connect(lambda result, w=worker: self._handle_finished(w, result, on_finished))
        worker.failed.connect(lambda message, w=worker: self._handle_failed(w, message, on_failed))

        on_started()
        self._workers.start(self._WORKER_KEY, worker)
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _handle_finished(
        self,
        worker: ReportWorker,
        result: dict,
        callback: Callable[[dict], None],
    ) -> None:
        stored = self._workers.pop(self._WORKER_KEY)
        if worker and isValid(worker):
            worker.deleteLater()
        if stored and stored is not worker and isValid(stored):
            stored.deleteLater()
        callback(result)

    def _handle_failed(
        self,
        worker: ReportWorker,
        message: str,
        callback: Callable[[str], None],
    ) -> None:
        stored = self._workers.pop(self._WORKER_KEY)
        if worker and isValid(worker):
            worker.deleteLater()
        if stored and stored is not worker and isValid(stored):
            stored.deleteLater()
        callback(message)


__all__ = ["ReportJobConfig", "ReportsService"]
