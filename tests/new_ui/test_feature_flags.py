"""Tests for dashboard feature flags."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

_FEATURE_FLAGS_PATH = ROOT / "src" / "new" / "core" / "feature_flags.py"
_spec = importlib.util.spec_from_file_location("feature_flags", _FEATURE_FLAGS_PATH)
assert _spec and _spec.loader
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
FeatureFlags = _module.FeatureFlags


class _StubSettings:
    def __init__(self, payload: Dict[str, Any] | None = None) -> None:
        self._payload = payload or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._payload.get(key, default)


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in FeatureFlags.ENV_MAPPING.values():
        monkeypatch.delenv(key, raising=False)


def test_defaults_without_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)

    flags = FeatureFlags.from_settings(None)

    assert flags.dashboard_workspace_enabled is True
    assert flags.summary_groups_enabled is False
    assert flags.progress_tab_enabled is False
    assert flags.auto_run_conversion_on_create is True


def test_settings_override(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    settings = _StubSettings(
        {
            "feature_flags": {
                "summary_groups_enabled": True,
                "auto_run_conversion_on_create": False,
            }
        }
    )

    flags = FeatureFlags.from_settings(settings)

    assert flags.summary_groups_enabled is True
    assert flags.auto_run_conversion_on_create is False


def test_environment_has_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("FRD_ENABLE_SUMMARY_GROUPS", "yes")
    monkeypatch.setenv("FRD_AUTO_RUN_CONVERSION", "0")

    settings = _StubSettings(
        {
            "feature_flags": {
                "summary_groups_enabled": False,
                "auto_run_conversion_on_create": True,
            }
        }
    )

    flags = FeatureFlags.from_settings(settings)

    assert flags.summary_groups_enabled is True
    assert flags.auto_run_conversion_on_create is False
