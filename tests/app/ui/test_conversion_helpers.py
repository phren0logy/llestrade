"""Tests for conversion helper registry and integration points."""

from __future__ import annotations

from src.app.core.conversion_helpers import registry, find_helper


def test_registry_lists_helpers() -> None:
    helpers = registry().list_helpers()
    helper_ids = {helper.helper_id for helper in helpers}
    assert helper_ids == {"azure_di"}


def test_find_helper_returns_correct_entry() -> None:
    helper = find_helper("azure_di")
    assert helper.helper_id == "azure_di"
    assert "Azure" in helper.name


def test_helper_options_exposed() -> None:
    helper = find_helper("azure_di")
    assert list(helper.options) == []
