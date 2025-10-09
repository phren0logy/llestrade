from __future__ import annotations

from pathlib import Path

import pytest

from src.app.core.project_manager import ProjectMetadata
from src.app.core.bulk_analysis_groups import BulkAnalysisGroup
from src.app.workers import bulk_reduce_worker as reduce_module
from src.app.workers.bulk_reduce_worker import BulkReduceWorker, ProviderConfig


def test_bulk_reduce_worker_force_rerun(tmp_path: Path, qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = qtbot
    project_dir = tmp_path
    converted = project_dir / "converted_documents" / "folder"
    converted.mkdir(parents=True, exist_ok=True)
    converted_doc = converted / "doc.md"
    converted_doc.write_text("content", encoding="utf-8")

    group = BulkAnalysisGroup.create("Group")
    group.combine_converted_files = ["folder/doc.md"]
    metadata = ProjectMetadata(case_name="Case")

    call_count = {"value": 0}

    monkeypatch.setattr(
        reduce_module,
        "load_prompts",
        lambda *_args, **_kwargs: reduce_module.PromptBundle("System", "User {document_content}"),
    )
    monkeypatch.setattr(
        BulkReduceWorker,
        "_resolve_provider",
        lambda self: ProviderConfig(provider_id="anthropic", model="claude", temperature=0.1),
    )
    monkeypatch.setattr(
        BulkReduceWorker,
        "_create_provider",
        lambda self, *_: object(),
    )
    monkeypatch.setattr(
        reduce_module,
        "should_chunk",
        lambda *_args, **_kwargs: (False, 1000, 2000),
    )

    def fake_invoke(self, *args, **kwargs):  # noqa: ANN001
        call_count["value"] += 1
        return "summary"

    monkeypatch.setattr(BulkReduceWorker, "_invoke_provider", fake_invoke)

    worker = BulkReduceWorker(
        project_dir=project_dir,
        group=group,
        metadata=metadata,
        force_rerun=False,
        placeholder_values={},
        project_name="Case",
    )
    worker._run()
    assert call_count["value"] == 1

    skip_worker = BulkReduceWorker(
        project_dir=project_dir,
        group=group,
        metadata=metadata,
        force_rerun=False,
        placeholder_values={},
        project_name="Case",
    )
    skip_worker._run()
    assert call_count["value"] == 1

    force_worker = BulkReduceWorker(
        project_dir=project_dir,
        group=group,
        metadata=metadata,
        force_rerun=True,
        placeholder_values={},
        project_name="Case",
    )
    force_worker._run()
    assert call_count["value"] == 2


def test_bulk_reduce_worker_applies_placeholder_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_dir = tmp_path
    converted_dir = project_dir / "converted_documents"
    converted_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = project_dir / "sources" / "doc.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_text("pdf", encoding="utf-8")

    import frontmatter

    doc_path = converted_dir / "doc.md"
    post = frontmatter.Post("Content", metadata={"sources": [{"path": str(pdf_path)}]})
    doc_path.write_text(frontmatter.dumps(post), encoding="utf-8")

    group = BulkAnalysisGroup.create("Group")
    group.combine_converted_files = ["doc.md"]

    metadata = ProjectMetadata(case_name="Case")

    monkeypatch.setattr(
        reduce_module,
        "load_prompts",
        lambda *_args, **_kwargs: reduce_module.PromptBundle(
            "System for {project_name}",
            "Combined {reduce_source_list} {client_name}",
        ),
    )
    monkeypatch.setattr(
        BulkReduceWorker,
        "_resolve_provider",
        lambda self: ProviderConfig(provider_id="anthropic", model="claude", temperature=0.1),
    )
    monkeypatch.setattr(
        BulkReduceWorker,
        "_create_provider",
        lambda self, *_: object(),
    )
    monkeypatch.setattr(
        reduce_module,
        "should_chunk",
        lambda *_args, **_kwargs: (False, 100, 2000),
    )

    captured: dict[str, list[str]] = {"system": [], "user": []}

    def fake_invoke(self, provider, cfg, prompt, system_prompt):  # noqa: ANN001
        captured["system"].append(system_prompt)
        captured["user"].append(prompt)
        return "summary"

    monkeypatch.setattr(BulkReduceWorker, "_invoke_provider", fake_invoke)

    worker = BulkReduceWorker(
        project_dir=project_dir,
        group=group,
        metadata=metadata,
        force_rerun=True,
        placeholder_values={"client_name": "ACME"},
        project_name="Case Project",
    )
    worker._run()

    assert captured["system"], "expected system prompt captured"
    assert captured["user"], "expected user prompt captured"
    assert captured["system"][0] == "System for Case Project"
    assert "doc.pdf" in captured["user"][0]
    assert "ACME" in captured["user"][0]
