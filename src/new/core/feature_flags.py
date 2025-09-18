"""Feature flag helpers for the dashboard refactor."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from typing import Any, ClassVar, Dict, Mapping


def _parse_bool(value: Any, default: bool = False) -> bool:
    """Return a boolean coerced from ``value`` with sensible defaults."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


@dataclass(frozen=True)
class FeatureFlags:
    """Feature toggles that can be overridden by settings or environment."""

    dashboard_workspace_enabled: bool = True
    summary_groups_enabled: bool = True
    progress_tab_enabled: bool = False
    auto_run_conversion_on_create: bool = True

    ENV_MAPPING: ClassVar[Mapping[str, str]] = {
        "dashboard_workspace_enabled": "FRD_ENABLE_DASHBOARD_WORKSPACE",
        "summary_groups_enabled": "FRD_ENABLE_SUMMARY_GROUPS",
        "progress_tab_enabled": "FRD_ENABLE_PROGRESS_TAB",
        "auto_run_conversion_on_create": "FRD_AUTO_RUN_CONVERSION",
    }

    SETTINGS_KEY: ClassVar[str] = "feature_flags"

    @classmethod
    def from_settings(cls, settings: Any | None = None) -> "FeatureFlags":
        """Build a ``FeatureFlags`` instance from ``SecureSettings`` and env vars."""
        defaults = {field.name: getattr(cls(), field.name) for field in fields(cls) if field.init}

        if settings is not None:
            try:
                stored = settings.get(cls.SETTINGS_KEY, {})  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - defensive
                stored = {}
            if isinstance(stored, Mapping):
                for key, value in stored.items():
                    if key in defaults:
                        defaults[key] = _parse_bool(value, defaults[key])

        for attr, env_name in cls.ENV_MAPPING.items():
            env_value = os.getenv(env_name)
            if env_value is not None:
                defaults[attr] = _parse_bool(env_value, defaults[attr])

        return cls(**defaults)

    def as_dict(self) -> Dict[str, bool]:
        """Return a plain dictionary representation of the flags."""
        return {field.name: getattr(self, field.name) for field in fields(self) if field.init}


__all__ = ["FeatureFlags"]
