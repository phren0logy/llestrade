#!/usr/bin/env bash
set -euo pipefail

# Disable third-party pytest plugin auto-discovery to prevent stray plugins
# (e.g., phoenix) from spawning background services and hanging test runs.
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

# Explicitly load pytest-qt so fixtures like `qtbot` remain available.
exec uv run pytest -p pytestqt.plugin "$@"

