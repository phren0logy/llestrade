import logging

from src.app.workers.base import DashboardWorker


class _DummyWorker(DashboardWorker):
    def __init__(self) -> None:
        super().__init__(worker_name="dummy")

    def _run(self) -> None:  # pragma: no cover - simple no-op
        # Minimal work to trigger start/finish logs
        self.logger.debug("%s doing work", self.job_tag)


def test_job_logging_start_finish(caplog):
    worker = _DummyWorker()
    tag = worker.job_tag

    caplog.set_level(logging.INFO)
    worker.run()

    messages = [rec.getMessage() for rec in caplog.records if rec.name.endswith("base.dummy")]
    assert any(tag in m and "started" in m for m in messages), "should log started with job tag"
    assert any(tag in m and "finished" in m for m in messages), "should log finished with job tag"


def test_job_logging_cancel(caplog):
    worker = _DummyWorker()
    tag = worker.job_tag

    caplog.set_level(logging.INFO)
    worker.cancel()

    messages = [rec.getMessage() for rec in caplog.records if rec.name.endswith("base.dummy")]
    assert any(tag in m and "cancel requested" in m for m in messages), "should log cancel with job tag"

