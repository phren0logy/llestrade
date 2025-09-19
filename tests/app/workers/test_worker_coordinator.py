"""Unit tests for the WorkerCoordinator helper."""

from __future__ import annotations

from typing import List

import pytest

from src.app.workers.base import DashboardWorker
from src.app.workers.coordinator import WorkerCoordinator


class _StubPool:
    def __init__(self) -> None:
        self.started: List[DashboardWorker] = []

    def start(self, worker: DashboardWorker) -> None:  # pragma: no cover - trivial stub
        self.started.append(worker)
        worker.run()


class _StubWorker(DashboardWorker):
    def __init__(self, name: str = "stub") -> None:
        super().__init__(worker_name=name)
        self.ran = False

    def _run(self) -> None:
        self.ran = True

    def cancel(self) -> None:
        super().cancel()


def test_start_registers_and_runs_worker() -> None:
    pool = _StubPool()
    coord = WorkerCoordinator(pool)
    worker = _StubWorker()

    coord.start("alpha", worker)

    assert pool.started == [worker]
    assert worker.ran is True
    assert coord.get("alpha") is worker


def test_pop_and_clear_remove_workers() -> None:
    pool = _StubPool()
    coord = WorkerCoordinator(pool)
    worker = _StubWorker("beta")
    coord.register("beta", worker)

    popped = coord.pop("beta")
    assert popped is worker
    assert coord.get("beta") is None

    coord.register("gamma", _StubWorker("gamma"))
    coord.clear()
    assert coord.get("gamma") is None


def test_cancel_marks_worker_cancelled() -> None:
    pool = _StubPool()
    coord = WorkerCoordinator(pool)
    worker = _StubWorker("delta")
    coord.register("delta", worker)

    assert coord.cancel("delta") is True
    assert worker.is_cancelled() is True

    assert coord.cancel("missing") is False
