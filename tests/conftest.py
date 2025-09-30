"""Shared pytest configuration for dashboard tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import os

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


@pytest.fixture(scope="session", autouse=True)
def _env_keys_from_keychain():
    """Populate API key environment variables from keychain/.env if missing.

    This lets provider tests run using keys stored via SecureSettings without
    requiring users to export env vars manually.
    """
    # First try to load values from a local .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    # If env vars are still missing, try OS keychain via SecureSettings
    try:
        from src.app.core.secure_settings import SecureSettings

        settings = SecureSettings()

        gemini = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not gemini:
            gemini = settings.get_api_key("gemini") or settings.get_api_key("google")
        if gemini and not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
            os.environ["GEMINI_API_KEY"] = gemini

        anthropic = os.environ.get("ANTHROPIC_API_KEY")
        if not anthropic:
            anthropic = settings.get_api_key("anthropic")
        if anthropic and not os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = anthropic
    except Exception:
        # Keychain may not be available in some CI/sandboxed environments
        pass
    yield
