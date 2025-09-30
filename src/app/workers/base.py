"""Shared base classes for dashboard workers."""

from __future__ import annotations

import logging
import threading
from typing import Final
from uuid import uuid4

from PySide6.QtCore import QObject, QRunnable


class DashboardWorker(QObject, QRunnable):
    """Base class for QRunnable-based workers used in the dashboard.

    Subclasses should implement :meth:`_run` and emit any signals they need.
    The base class provides cancellation helpers and consistent crash logging.
    """

    def __init__(self, *, worker_name: str, auto_delete: bool = False) -> None:
        QObject.__init__(self)
        QRunnable.__init__(self)
        self.setAutoDelete(auto_delete)
        self._worker_name: Final[str] = worker_name
        self._cancel_event = threading.Event()
        self.logger = logging.getLogger(f"{__name__}.{worker_name}")
        # Stable identifier for traceability across logs
        self.job_id: Final[str] = uuid4().hex[:8]
        self.job_tag: Final[str] = f"[{self._worker_name}:{self.job_id}]"

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
    def cancel(self) -> None:
        """Request cancellation of the worker."""
        self._cancel_event.set()
        try:
            self.logger.info("%s cancel requested", self.job_tag)
        except Exception:
            pass

    def is_cancelled(self) -> bool:
        """Return True if cancellation has been requested."""
        return self._cancel_event.is_set()

    def run(self) -> None:  # pragma: no cover - thin wrapper around subclass logic
        try:
            self.logger.info("%s started", self.job_tag)
            self._run()
            self.logger.info("%s finished", self.job_tag)
        except Exception as exc:  # noqa: BLE001 - logged and surfaced via hook
            self.logger.exception("%s crashed: %s", self.job_tag, exc)
            self._handle_failure(exc)

    # ------------------------------------------------------------------
    # Extension points
    # ------------------------------------------------------------------
    def _run(self) -> None:  # pragma: no cover - must be implemented by subclass
        raise NotImplementedError

    def _handle_failure(self, exc: Exception) -> None:
        """Hook for subclasses to surface unexpected failures."""
        # Default implementation swallows the exception after logging.
        # Subclasses may override to emit a failure signal or similar behaviour.
        _ = exc


__all__ = ["DashboardWorker"]
