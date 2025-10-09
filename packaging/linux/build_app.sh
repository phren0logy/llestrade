#!/usr/bin/env bash

# Convenience wrapper for building the Linux PyInstaller bundle.
# Produces dist/linux/llestrade/ with the frozen dashboard binary.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

SPEC_FILE="${ROOT_DIR}/scripts/build_dashboard.spec"
DIST_DIR="${ROOT_DIR}/dist/linux"

FRESH_DIST=0

usage() {
  cat <<'EOF'
Usage: ./packaging/linux/build_app.sh [--fresh-dist]

  --fresh-dist  Remove dist/linux before building to ensure a clean output directory.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
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
  printf '[linux-package] %s\n' "$*"
}

if [[ ! -f "${SPEC_FILE}" ]]; then
  echo "error: missing PyInstaller spec at ${SPEC_FILE}" >&2
  exit 1
fi

if [[ "${FRESH_DIST}" -eq 1 ]]; then
  log "removing ${DIST_DIR} for a clean build"
  rm -rf "${DIST_DIR}"
fi

export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-${ROOT_DIR}/.pyinstaller}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${ROOT_DIR}/.uv_cache}"

log "root: ${ROOT_DIR}"
log "spec: ${SPEC_FILE}"
log "PyInstaller config dir: ${PYINSTALLER_CONFIG_DIR}"
log "uv cache dir: ${UV_CACHE_DIR}"

log "building Linux bundle via PyInstaller"
(
  cd "${ROOT_DIR}"
  UV_CACHE_DIR="${UV_CACHE_DIR}" PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR}" uv run pyinstaller --clean --noconfirm "${SPEC_FILE}"
)

BUNDLE_DIR="${DIST_DIR}/llestrade"
EXECUTABLE="${BUNDLE_DIR}/llestrade"
if [[ -x "${EXECUTABLE}" ]]; then
  log "bundle ready at ${EXECUTABLE}"
else
  echo "warning: expected executable at ${EXECUTABLE} but it was not found" >&2
  exit 1
fi
