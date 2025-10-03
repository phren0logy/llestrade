"""Tests for the report generation worker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

_ = PySide6

from src.app.core.project_manager import ProjectMetadata
from src.app.core.report_inputs import REPORT_CATEGORY_CONVERTED
from src.app.workers import report_worker
from src.app.workers.report_worker import ReportWorker
from src.common.llm.base import BaseLLMProvider


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
        self._call_index = 0

    def generate(self, prompt: str, model: str | None = None, max_tokens: int = 32000, temperature: float = 0.1, system_prompt: str | None = None) -> dict:  # noqa: ARG002
        self._call_index += 1
        lower_prompt = (prompt or "").lower()
        if "refine" in lower_prompt or "<draft>" in lower_prompt:
            content = "Refined content"
            reasoning = "Reasoning trace"
        else:
            content = f"Section output {self._call_index}"
            reasoning = ""
        response = {
            "success": True,
            "content": content,
            "usage": {"output_tokens": 100 + self._call_index},
            "reasoning": reasoning,
        }
        return response

    def count_tokens(self, text: str | None = None, messages: list[dict] | None = None) -> dict:  # noqa: ARG002
        length = len(text or "")
        return {"success": True, "token_count": max(length // 4, 1)}

    @property
    def provider_name(self) -> str:  # type: ignore[override]
        return "stub"

    @property
    def default_model(self) -> str:  # type: ignore[override]
        return "stub-model"


class _StubPromptManager:
    def get_prompt_template(self, name: str) -> dict:
        raise KeyError(name)

    def get_template(self, name: str) -> str:
        if name == "refinement_prompt":
            return "Refine using {instructions}\n<draft>{report_content}</draft>{template_section}{transcript_section}"
        if name == "report_generation_instructions":
            return (
                "Generate the report section using the supplied template. "
                "Incorporate material from <documents> and <transcript> when present."
            )
        raise KeyError(name)

    def get_system_prompt(self) -> str:
        return "System"


class _StubPromptManagerMissingInstructions(_StubPromptManager):
    def get_template(self, name: str) -> str:
        if name == "report_generation_instructions":
            raise KeyError(name)
        return super().get_template(name)


def test_report_worker_generates_outputs(tmp_path: Path, qt_app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    assert qt_app is not None

    project_dir = tmp_path
    converted_dir = project_dir / "converted_documents"
    converted_dir.mkdir(parents=True, exist_ok=True)
    (converted_dir / "doc.md").write_text("# Heading\nBody", encoding="utf-8")
    template_dir = project_dir / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    template_path = template_dir / "report-template.md"
    template_path.write_text(
        "# Section One\n\nDetails for section one.\n\n# Section Two\n\nDetails for section two.",
        encoding="utf-8",
    )

    monkeypatch.setattr(report_worker, "create_provider", lambda **_: _StubProvider())
    monkeypatch.setattr(report_worker, "SecureSettings", lambda: _StubSettings())
    monkeypatch.setattr(report_worker, "PromptManager", lambda: _StubPromptManager())

    worker = ReportWorker(
        project_dir=project_dir,
        inputs=[(REPORT_CATEGORY_CONVERTED, "converted_documents/doc.md")],
        provider_id="anthropic",
        model="claude-sonnet-4-5-20250929",
        custom_model=None,
        context_window=None,
        instructions="Follow instructions",
        template_path=template_path,
        transcript_path=None,
        refinement_prompt_name="refinement_prompt",
        metadata=ProjectMetadata(case_name="Case"),
    )

    finished_results: list[dict] = []
    worker.finished.connect(lambda payload: finished_results.append(payload))

    worker.run()

    assert finished_results, "Expected finished signal"
    result = finished_results[0]
    draft_path = Path(result["draft_path"])
    refined_path = Path(result["refined_path"])
    reasoning_path = Path(result["reasoning_path"])
    manifest_path = Path(result["manifest_path"])
    inputs_path = Path(result["inputs_path"])

    assert draft_path.exists()
    assert refined_path.exists()
    assert reasoning_path.exists()
    assert manifest_path.exists()
    assert inputs_path.exists()

    assert "Section output" in draft_path.read_text(encoding="utf-8")
    assert "Refined content" in refined_path.read_text(encoding="utf-8")
    assert "Reasoning trace" in reasoning_path.read_text(encoding="utf-8")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["provider"] == "anthropic"
    assert manifest["draft_path"].endswith("-draft.md")
    assert manifest["inputs"]
    assert len(manifest["sections"]) == 2


def test_report_worker_requires_generation_instructions(
    tmp_path: Path,
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert qt_app is not None

    project_dir = tmp_path
    converted_dir = project_dir / "converted_documents"
    converted_dir.mkdir(parents=True, exist_ok=True)
    (converted_dir / "doc.md").write_text("Body", encoding="utf-8")
    template_dir = project_dir / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    template_path = template_dir / "report-template.md"
    template_path.write_text("# Only Section\n\nDetails", encoding="utf-8")

    monkeypatch.setattr(report_worker, "create_provider", lambda **_: _StubProvider())
    monkeypatch.setattr(report_worker, "SecureSettings", lambda: _StubSettings())
    monkeypatch.setattr(report_worker, "PromptManager", lambda: _StubPromptManagerMissingInstructions())

    worker = ReportWorker(
        project_dir=project_dir,
        inputs=[(REPORT_CATEGORY_CONVERTED, "converted_documents/doc.md")],
        provider_id="anthropic",
        model="claude-sonnet-4-5-20250929",
        custom_model=None,
        context_window=None,
        instructions="Follow instructions",
        template_path=template_path,
        transcript_path=None,
        refinement_prompt_name="refinement_prompt",
        metadata=ProjectMetadata(case_name="Case"),
    )

    failures: list[str] = []
    worker.failed.connect(failures.append)

    worker.run()

    assert failures, "Expected failure signal when section instructions missing"
    assert "report_generation_instructions" in failures[0]


def test_report_worker_requires_template(tmp_path: Path, qt_app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    assert qt_app is not None

    project_dir = tmp_path
    converted_dir = project_dir / "converted_documents"
    converted_dir.mkdir(parents=True, exist_ok=True)
    (converted_dir / "doc.md").write_text("Content", encoding="utf-8")

    monkeypatch.setattr(report_worker, "create_provider", lambda **_: _StubProvider())
    monkeypatch.setattr(report_worker, "SecureSettings", lambda: _StubSettings())
    monkeypatch.setattr(report_worker, "PromptManager", lambda: _StubPromptManager())

    worker = ReportWorker(
        project_dir=project_dir,
        inputs=[(REPORT_CATEGORY_CONVERTED, "converted_documents/doc.md")],
        provider_id="anthropic",
        model="claude-sonnet-4-5-20250929",
        custom_model=None,
        context_window=None,
        instructions="Do it",
        template_path=None,
        transcript_path=None,
        refinement_prompt_name="refinement_prompt",
        metadata=ProjectMetadata(case_name="Case"),
    )

    failures: list[str] = []
    worker.failed.connect(failures.append)

    worker.run()

    assert failures, "Expected failure signal when template missing"
    assert "template" in failures[0].lower()


def test_report_worker_supports_transcript_without_inputs(
    tmp_path: Path,
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert qt_app is not None

    project_dir = tmp_path
    transcript_path = project_dir / "call-transcript.md"
    transcript_path.write_text("Transcript content", encoding="utf-8")
    template_dir = project_dir / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    template_path = template_dir / "report-template.md"
    template_path.write_text("Template body", encoding="utf-8")

    monkeypatch.setattr(report_worker, "create_provider", lambda **_: _StubProvider())
    monkeypatch.setattr(report_worker, "SecureSettings", lambda: _StubSettings())
    monkeypatch.setattr(report_worker, "PromptManager", lambda: _StubPromptManager())

    worker = ReportWorker(
        project_dir=project_dir,
        inputs=[],
        provider_id="anthropic",
        model="claude-sonnet-4-5-20250929",
        custom_model=None,
        context_window=None,
        instructions="Follow",
        template_path=template_path,
        transcript_path=transcript_path,
        refinement_prompt_name="refinement_prompt",
        metadata=ProjectMetadata(case_name="Case"),
    )

    finished_results: list[dict] = []
    worker.finished.connect(lambda payload: finished_results.append(payload))

    worker.run()

    assert finished_results, "Expected finished signal when only transcript provided"
    result = finished_results[0]
    assert result["inputs"] == []
    assert Path(result["manifest_path"]).exists()
