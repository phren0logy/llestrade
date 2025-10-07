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
    )
    worker._run()
    assert call_count["value"] == 1

    skip_worker = BulkReduceWorker(
        project_dir=project_dir,
        group=group,
        metadata=metadata,
        force_rerun=False,
    )
    skip_worker._run()
    assert call_count["value"] == 1

    force_worker = BulkReduceWorker(
        project_dir=project_dir,
        group=group,
        metadata=metadata,
        force_rerun=True,
    )
    force_worker._run()
    assert call_count["value"] == 2
