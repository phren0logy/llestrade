"""Tests for conversion helper registry and integration points."""

from __future__ import annotations

from src.new.core.conversion_helpers import registry, find_helper


def test_registry_lists_helpers() -> None:
    helpers = registry().list_helpers()
    helper_ids = {helper.helper_id for helper in helpers}
    assert "default" in helper_ids
    assert "text_only" in helper_ids


def test_find_helper_returns_correct_entry() -> None:
    helper = find_helper("text_only")
    assert helper.helper_id == "text_only"
    assert helper.name.lower().startswith("text-only")


def test_helper_options_exposed() -> None:
    helper = find_helper("default")
    option_keys = [option.key for option in helper.options]
    assert "include_pdf_front_matter" in option_keys

