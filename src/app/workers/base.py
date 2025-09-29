"""Shared base classes for dashboard workers."""

from __future__ import annotations

import logging
import threading
from typing import Final

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

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
    def cancel(self) -> None:
        """Request cancellation of the worker."""
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        """Return True if cancellation has been requested."""
        return self._cancel_event.is_set()

    def run(self) -> None:  # pragma: no cover - thin wrapper around subclass logic
        try:
            self._run()
        except Exception as exc:  # noqa: BLE001 - logged and surfaced via hook
            self.logger.exception("Unhandled error in worker '%s'", self._worker_name)
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
