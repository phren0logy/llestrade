"""Tests for bulk analysis prompt handling."""

from __future__ import annotations

import pytest

from src.app.core import bulk_analysis_runner as runner
from src.app.core.bulk_analysis_groups import BulkAnalysisGroup
from src.app.core.prompt_placeholders import MissingPlaceholdersError


class _StubPromptManager:
    def get_template(self, name: str) -> str:
        if name == "document_analysis_system_prompt":
            return "System"
        if name == "document_bulk_analysis_prompt":
            return "Summary without placeholder"
        raise KeyError(name)


def test_load_prompts_requires_document_placeholder(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    group = BulkAnalysisGroup.create("Group")

    monkeypatch.setattr(runner, "PromptManager", lambda: _StubPromptManager())

    with pytest.raises(MissingPlaceholdersError) as excinfo:
        runner.load_prompts(tmp_path, group, metadata=None)

    assert "{document_content}" in str(excinfo.value)


def test_render_prompts_apply_placeholder_values() -> None:
    bundle = runner.PromptBundle(
        system_template="Welcome {project_name} for {client}",
        user_template="{document_content} -- {client}",
    )
    values = {"client": "ACME Corp", "project_name": "Case-42"}
    system = runner.render_system_prompt(bundle, metadata=None, placeholder_values=values)
    user = runner.render_user_prompt(
        bundle,
        metadata=None,
        document_name="doc.md",
        document_content="Body",
        placeholder_values=values,
    )
    assert system == "Welcome Case-42 for ACME Corp"
    assert user.startswith("Body -- ACME Corp")


def test_combine_chunk_summaries_uses_placeholder_values() -> None:
    summaries = ["Summary A", "Summary B"]
    prompt, context = runner.combine_chunk_summaries(
        summaries,
        document_name="Doc1",
        metadata=None,
        placeholder_values={"client": "ACME"},
    )
    assert "ACME" in prompt
    assert context["client"] == "ACME"
