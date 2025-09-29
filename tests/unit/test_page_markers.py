from __future__ import annotations

import re
from pathlib import Path

import pytest

from PySide6.QtWidgets import QApplication

from src.app.workers.conversion_worker import ConversionWorker


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_insert_azure_page_markers_increments_pages(qt_app: QApplication) -> None:
    worker = ConversionWorker([])
    sample = (
        "Intro text\n\n"
        "<!-- PageBreak -->\n"
        "Page two content\n\n"
        "<!-- PageBreak -->\n"
        "Page three content\n\n"
        "<!-- PageBreak -->\n"
        "Page four content\n"
    )
    content, pages = worker._insert_azure_page_markers(sample, "docs/sample.pdf")

    # Expect page 1 at start plus 3 breaks -> 4 markers total
    assert pages == 4
    markers = re.findall(r"<!---\s*docs/sample\.pdf#page=(\d+)\s*--->", content)
    assert [int(n) for n in markers] == [1, 2, 3, 4]


def test_warn_if_page_mismatch_logs(qt_app: QApplication, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    worker = ConversionWorker([])
    caplog.clear()
    caplog.set_level("WARNING")

    class _J:
        def __init__(self, name: str) -> None:
            self.source_path = Path(name)

    job = _J("huge.pdf")
    worker._warn_if_page_mismatch(job, pages_detected=1200, pages_pdf=1180)
    assert any("Page count mismatch" in rec.message for rec in caplog.records)

