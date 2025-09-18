"""Tests for conversion helper registry and integration points."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "src" / "new" / "core" / "conversion_helpers.py"
_SPEC = importlib.util.spec_from_file_location("conversion_helpers_module", MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

registry = _MODULE.registry
find_helper = _MODULE.find_helper


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
