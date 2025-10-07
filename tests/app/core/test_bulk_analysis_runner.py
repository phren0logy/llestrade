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
