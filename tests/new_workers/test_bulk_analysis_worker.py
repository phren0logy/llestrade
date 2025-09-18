"""Tests for the bulk analysis worker."""

from __future__ import annotations

from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

_ = PySide6

from src.common.llm.base import BaseLLMProvider
from src.new.core.project_manager import ProjectMetadata
from src.new.core.summary_groups import SummaryGroup
from src.new.workers import bulk_analysis_worker
from src.new.workers.bulk_analysis_worker import BulkAnalysisWorker


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _StubSettings:
    def get_api_key(self, provider: str) -> str | None:  # noqa: ARG002
        return None

    def get(self, key: str, default: object = None) -> object:  # noqa: ARG002
        return default


class _StubProvider(BaseLLMProvider):
    def __init__(self) -> None:
        super().__init__(timeout=0, max_retries=0, default_system_prompt="stub", debug=False)
        self.set_initialized(True)

    def generate(self, prompt: str, model: str | None = None, max_tokens: int = 32000, temperature: float = 0.1, system_prompt: str | None = None) -> dict:
        return {"success": True, "content": f"Generated summary for {model or 'stub'}"}

    def count_tokens(self, text: str | None = None, messages: list[dict] | None = None) -> dict:  # noqa: ARG002
        length = len(text or "")
        return {"success": True, "token_count": max(length // 4, 1)}

    @property
    def provider_name(self) -> str:  # type: ignore[override]
        return "stub"

    @property
    def default_model(self) -> str:  # type: ignore[override]
        return "stub-model"


def test_bulk_analysis_worker_writes_output(tmp_path: Path, qt_app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    assert qt_app is not None

    converted_dir = tmp_path / "converted_documents"
    converted_dir.mkdir(parents=True, exist_ok=True)
    (converted_dir / "doc.md").write_text("# Heading\nBody text", encoding="utf-8")

    group = SummaryGroup.create(name="Example", files=["doc.md"])
    group.slug = "example-group"
    group.system_prompt_path = "prompt_templates/document_analysis_system_prompt.md"
    group.user_prompt_path = "prompt_templates/document_summary_prompt.md"

    metadata = ProjectMetadata(
        case_name="Case",
        subject_name="Subject",
        date_of_birth="2000-01-01",
        case_description="Details",
    )

    stub_provider = _StubProvider()
    monkeypatch.setattr(bulk_analysis_worker, "create_provider", lambda **_: stub_provider)
    monkeypatch.setattr(bulk_analysis_worker, "SecureSettings", lambda: _StubSettings())

    worker = BulkAnalysisWorker(
        project_dir=tmp_path,
        group=group,
        files=["doc.md"],
        metadata=metadata,
        default_provider=("stub", "stub-model"),
    )

    finished_events: list[tuple[int, int]] = []
    worker.finished.connect(lambda success, failure: finished_events.append((success, failure)))

    worker.run()

    assert finished_events == [(1, 0)]
    output_path = tmp_path / "bulk_analysis" / group.folder_name / "outputs" / "doc_analysis.md"
    assert output_path.exists()
    assert "Generated summary" in output_path.read_text(encoding="utf-8")
