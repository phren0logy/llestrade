#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

WRAPPER="${PROJECT_ROOT}/packaging/linux/build_app.sh"

if [[ -x "${WRAPPER}" ]]; then
  "${WRAPPER}" "$@"
  exit $?
fi

echo "[linux-package] warning: ${WRAPPER} not found or not executable; falling back to direct PyInstaller invocation." >&2
cd "$PROJECT_ROOT"
uv run pyinstaller --clean --noconfirm scripts/build_dashboard.spec
