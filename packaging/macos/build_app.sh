#!/usr/bin/env bash

# Convenience wrapper to regenerate icons (optional) and build the unsigned macOS
# bundle via PyInstaller. Produces dist/darwin/Llestrade.app.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

ICON_SCRIPT="${SCRIPT_DIR}/build_iconset.sh"
ICON_PNG="${ROOT_DIR}/assets/icons/llestrade.png"
ICON_ICNS="${ROOT_DIR}/assets/icons/llestrade.icns"
SPEC_FILE="${ROOT_DIR}/scripts/build_dashboard.spec"

REFRESH_ICON=1
FRESH_DIST=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [--skip-icon] [--fresh-dist]

  --skip-icon   Do not regenerate the .iconset/.icns (assumes assets/icons/llestrade.icns exists)
  --fresh-dist  Remove dist/darwin before building to ensure a clean output directory
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-icon)
      REFRESH_ICON=0
      shift
      ;;
    --fresh-dist)
      FRESH_DIST=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option '$1'" >&2
      usage
      exit 1
      ;;
  esac
done

log() {
  printf '[macos-package] %s\n' "$*"
}

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "error: missing required file: $1" >&2
    exit 1
  fi
}

log "root: ${ROOT_DIR}"

if [[ "${REFRESH_ICON}" -eq 1 ]]; then
  require_file "${ICON_SCRIPT}"
  require_file "${ICON_PNG}"
  log "regenerating icon set via ${ICON_SCRIPT}"
  "${ICON_SCRIPT}"
elif [[ ! -f "${ICON_ICNS}" ]]; then
  echo "error: --skip-icon requested but ${ICON_ICNS} not found" >&2
  exit 1
fi

if [[ "${FRESH_DIST}" -eq 1 ]]; then
  log "removing ${ROOT_DIR}/dist/darwin for a clean build"
  rm -rf "${ROOT_DIR}/dist/darwin"
fi

require_file "${SPEC_FILE}"

export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-${ROOT_DIR}/.pyinstaller}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${ROOT_DIR}/.uv_cache}"

log "building app bundle with PyInstaller"
(
  cd "${ROOT_DIR}"
  UV_CACHE_DIR="${UV_CACHE_DIR}" PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR}" uv run pyinstaller -y "${SPEC_FILE}"
)

APP_PATH="${ROOT_DIR}/dist/darwin/Llestrade.app"
if [[ -d "${APP_PATH}" ]]; then
  log "bundle ready at ${APP_PATH}"
else
  echo "warning: expected bundle at ${APP_PATH} but it was not found" >&2
  exit 1
fi
