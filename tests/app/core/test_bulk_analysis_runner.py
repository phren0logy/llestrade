"""Tests for bulk analysis prompt handling."""

from __future__ import annotations

import pytest

from src.app.core import bulk_analysis_runner as runner
from src.app.core.summary_groups import SummaryGroup


class _StubPromptManager:
    def get_template(self, name: str) -> str:
        if name == "document_analysis_system_prompt":
            return "System"
        if name == "document_summary_prompt":
            return "Summary without placeholder"
        raise KeyError(name)


def test_load_prompts_requires_document_placeholder(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    group = SummaryGroup.create("Group")

    monkeypatch.setattr(runner, "PromptManager", lambda: _StubPromptManager())

    with pytest.raises(ValueError, match="document_content"):
        runner.load_prompts(tmp_path, group, metadata=None)
