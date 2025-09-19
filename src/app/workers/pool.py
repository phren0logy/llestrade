"""Shared worker pool helpers."""

from __future__ import annotations

from PySide6.QtCore import QThreadPool

_POOL: QThreadPool | None = None


def get_worker_pool(max_workers: int = 3) -> QThreadPool:
    """Return the shared worker pool configured for dashboard tasks."""
    global _POOL
    if _POOL is None:
        _POOL = QThreadPool.globalInstance()
        _POOL.setMaxThreadCount(max_workers)
    else:
        if _POOL.maxThreadCount() != max_workers:
            _POOL.setMaxThreadCount(max_workers)
    return _POOL


__all__ = ["get_worker_pool"]
