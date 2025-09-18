"""Shared pytest configuration for dashboard tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isolate_settings_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Keep tests from writing into the user's real settings directory."""

    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    monkeypatch.setenv("FRD_SETTINGS_DIR", str(settings_dir))
    yield
