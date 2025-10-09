"""Tests for the report generation worker."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

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
        self.system_prompts: list[str] = []

    def generate(self, prompt: str, model: str | None = None, max_tokens: int = 32000, temperature: float = 0.1, system_prompt: str | None = None) -> dict:  # noqa: ARG002
        self._call_index += 1
        if system_prompt:
            self.system_prompts.append(system_prompt)
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


def _write_generation_user_prompt(path: Path) -> None:
    path.write_text(
        (
            "## Prompt\n\n"
            "Write the report section described in {template_section}.\n\n"
            "Transcript (if any):\n{transcript}\n\n"
            "Other sources:\n{additional_documents}\n"
        ),
        encoding="utf-8",
    )


def _write_refinement_user_prompt(path: Path) -> None:
    path.write_text(
        (
            "## Instructions\n\nPolish the draft into final prose.\n\n"
            "## Prompt\n\n"
            "<draft>{draft_report}</draft>\n\n"
            "<template>{template}</template>\n\n"
            "<transcript>{transcript}</transcript>\n"
        ),
        encoding="utf-8",
    )


def _write_system_prompt(path: Path, message: str) -> None:
    path.write_text(message, encoding="utf-8")


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
        dedent(
            """\
            # Section One

            Details for section one.

            # Section Two

            Details for section two.
            """
        ),
        encoding="utf-8",
    )

    prompt_dir = project_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    generation_user_prompt_path = prompt_dir / "generation_user_prompt.md"
    _write_generation_user_prompt(generation_user_prompt_path)
    refinement_user_prompt_path = prompt_dir / "refinement_user_prompt.md"
    _write_refinement_user_prompt(refinement_user_prompt_path)

    system_prompt_dir = project_dir / "system_prompts"
    system_prompt_dir.mkdir(parents=True, exist_ok=True)
    generation_system_prompt_path = system_prompt_dir / "generation.md"
    _write_system_prompt(generation_system_prompt_path, "You are helping draft a report section for {client_name}.")
    refinement_system_prompt_path = system_prompt_dir / "refinement.md"
    _write_system_prompt(refinement_system_prompt_path, "You are refining a report for {client_name}.")

    stub_provider = _StubProvider()
    monkeypatch.setattr(report_worker, "create_provider", lambda **_: stub_provider)
    monkeypatch.setattr(report_worker, "SecureSettings", lambda: _StubSettings())

    placeholder_values = {"client_name": "ACME Inc"}

    worker = ReportWorker(
        project_dir=project_dir,
        inputs=[(REPORT_CATEGORY_CONVERTED, "converted_documents/doc.md")],
        provider_id="anthropic",
        model="claude-sonnet-4-5-20250929",
        custom_model=None,
        context_window=None,
        template_path=template_path,
        transcript_path=None,
        generation_user_prompt_path=generation_user_prompt_path,
        refinement_user_prompt_path=refinement_user_prompt_path,
        generation_system_prompt_path=generation_system_prompt_path,
        refinement_system_prompt_path=refinement_system_prompt_path,
        metadata=ProjectMetadata(case_name="Case"),
        placeholder_values=placeholder_values,
        project_name="Case",
    )

    finished_results: list[dict] = []
    failures: list[str] = []
    worker.finished.connect(lambda payload: finished_results.append(payload))
    worker.failed.connect(failures.append)

    worker.run()

    assert not failures, f"Unexpected worker failure: {failures!r}"
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

    draft_text = draft_path.read_text(encoding="utf-8")
    assert "Section output" in draft_text
    assert "ACME Inc" in draft_text
    assert "Refined content" in refined_path.read_text(encoding="utf-8")
    assert "Reasoning trace" in reasoning_path.read_text(encoding="utf-8")
    assert result["generation_user_prompt"].endswith("generation_user_prompt.md")
    assert result["refinement_user_prompt"].endswith("refinement_user_prompt.md")
    assert result["generation_system_prompt"].endswith("generation.md")
    assert result["refinement_system_prompt"].endswith("refinement.md")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["provider"] == "anthropic"
    assert manifest["draft_path"].endswith("-draft.md")
    assert manifest["inputs"]
    assert len(manifest["sections"]) == 2
    assert manifest["generation_user_prompt"].endswith("generation_user_prompt.md")
    assert manifest["refinement_user_prompt"].endswith("refinement_user_prompt.md")
    assert manifest["generation_system_prompt"].endswith("generation.md")
    assert manifest["refinement_system_prompt"].endswith("refinement.md")
    assert any("ACME Inc" in prompt for prompt in stub_provider.system_prompts)


def test_report_worker_requires_generation_placeholders(
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
    template_path.write_text("# Only Section\\n\\nDetails", encoding="utf-8")

    prompt_dir = project_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    generation_user_prompt_path = prompt_dir / "generation_user_prompt.md"
    # Missing {additional_documents}
    generation_user_prompt_path.write_text(
        (
            "## Prompt\n\n"
            "Write the section described in {template_section}.\n\n"
            "Transcript (if any):\n{transcript}\n"
        ),
        encoding="utf-8",
    )
    refinement_user_prompt_path = prompt_dir / "refinement_user_prompt.md"
    _write_refinement_user_prompt(refinement_user_prompt_path)

    system_prompt_dir = project_dir / "system_prompts"
    system_prompt_dir.mkdir(parents=True, exist_ok=True)
    generation_system_prompt_path = system_prompt_dir / "generation.md"
    _write_system_prompt(generation_system_prompt_path, "Gen")
    refinement_system_prompt_path = system_prompt_dir / "refinement.md"
    _write_system_prompt(refinement_system_prompt_path, "Ref")

    monkeypatch.setattr(report_worker, "create_provider", lambda **_: _StubProvider())
    monkeypatch.setattr(report_worker, "SecureSettings", lambda: _StubSettings())

    worker = ReportWorker(
        project_dir=project_dir,
        inputs=[(REPORT_CATEGORY_CONVERTED, "converted_documents/doc.md")],
        provider_id="anthropic",
        model="claude-sonnet-4-5-20250929",
        custom_model=None,
        context_window=None,
        template_path=template_path,
        transcript_path=None,
        generation_user_prompt_path=generation_user_prompt_path,
        refinement_user_prompt_path=refinement_user_prompt_path,
        generation_system_prompt_path=generation_system_prompt_path,
        refinement_system_prompt_path=refinement_system_prompt_path,
        metadata=ProjectMetadata(case_name="Case"),
    )

    failures: list[str] = []
    worker.failed.connect(failures.append)

    worker.run()

    assert failures, "Expected failure signal when generation user prompt missing placeholders"
    assert "{additional_documents}" in failures[0]


def test_report_worker_requires_refinement_placeholders(
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
    template_path.write_text(
        dedent(
            """\
            # Only Section

            Details
            """
        ),
        encoding="utf-8",
    )

    prompt_dir = project_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    generation_user_prompt_path = prompt_dir / "generation_user_prompt.md"
    _write_generation_user_prompt(generation_user_prompt_path)
    refinement_user_prompt_path = prompt_dir / "refinement_user_prompt.md"
    refinement_user_prompt_path.write_text(
        "## Prompt\n\n<draft>{draft_report}</draft>",
        encoding="utf-8",
    )

    system_prompt_dir = project_dir / "system_prompts"
    system_prompt_dir.mkdir(parents=True, exist_ok=True)
    generation_system_prompt_path = system_prompt_dir / "generation.md"
    _write_system_prompt(generation_system_prompt_path, "Gen")
    refinement_system_prompt_path = system_prompt_dir / "refinement.md"
    _write_system_prompt(refinement_system_prompt_path, "Ref")

    monkeypatch.setattr(report_worker, "create_provider", lambda **_: _StubProvider())
    monkeypatch.setattr(report_worker, "SecureSettings", lambda: _StubSettings())

    worker = ReportWorker(
        project_dir=project_dir,
        inputs=[(REPORT_CATEGORY_CONVERTED, "converted_documents/doc.md")],
        provider_id="anthropic",
        model="claude-sonnet-4-5-20250929",
        custom_model=None,
        context_window=None,
        template_path=template_path,
        transcript_path=None,
        generation_user_prompt_path=generation_user_prompt_path,
        refinement_user_prompt_path=refinement_user_prompt_path,
        generation_system_prompt_path=generation_system_prompt_path,
        refinement_system_prompt_path=refinement_system_prompt_path,
        metadata=ProjectMetadata(case_name="Case"),
    )

    failures: list[str] = []
    worker.failed.connect(failures.append)

    worker.run()

    assert failures, "Expected failure signal when refinement user prompt missing placeholders"
    assert "{template}" in failures[0]


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
    template_path.write_text("# Template Section\n\nDetails", encoding="utf-8")

    prompt_dir = project_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    generation_user_prompt_path = prompt_dir / "generation_user_prompt.md"
    _write_generation_user_prompt(generation_user_prompt_path)
    refinement_user_prompt_path = prompt_dir / "refinement_user_prompt.md"
    _write_refinement_user_prompt(refinement_user_prompt_path)

    system_prompt_dir = project_dir / "system_prompts"
    system_prompt_dir.mkdir(parents=True, exist_ok=True)
    generation_system_prompt_path = system_prompt_dir / "generation.md"
    _write_system_prompt(generation_system_prompt_path, "Gen")
    refinement_system_prompt_path = system_prompt_dir / "refinement.md"
    _write_system_prompt(refinement_system_prompt_path, "Ref")

    monkeypatch.setattr(report_worker, "create_provider", lambda **_: _StubProvider())
    monkeypatch.setattr(report_worker, "SecureSettings", lambda: _StubSettings())

    worker = ReportWorker(
        project_dir=project_dir,
        inputs=[],
        provider_id="anthropic",
        model="claude-sonnet-4-5-20250929",
        custom_model=None,
        context_window=None,
        template_path=template_path,
        transcript_path=transcript_path,
        generation_user_prompt_path=generation_user_prompt_path,
        refinement_user_prompt_path=refinement_user_prompt_path,
        generation_system_prompt_path=generation_system_prompt_path,
        refinement_system_prompt_path=refinement_system_prompt_path,
        metadata=ProjectMetadata(case_name="Case"),
    )

    finished_results: list[dict] = []
    failures: list[str] = []
    worker.finished.connect(lambda payload: finished_results.append(payload))
    worker.failed.connect(failures.append)

    worker.run()

    assert not failures, f"Unexpected worker failure: {failures!r}"
    assert finished_results, "Expected finished signal when only transcript provided"
    result = finished_results[0]
    assert result["inputs"] == []
    assert Path(result["manifest_path"]).exists()
    assert result["generation_user_prompt"].endswith("generation_user_prompt.md")
    assert result["refinement_user_prompt"].endswith("refinement_user_prompt.md")
