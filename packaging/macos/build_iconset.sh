#!/usr/bin/env bash

# Build a macOS .iconset (and .icns) from the master Llestrade PNG.
# Usage:
#   ./packaging/macos/build_iconset.sh [source_png] [iconset_dir] [icns_output]
# Defaults assume the repository layout created by the packaging plan.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

SRC_PNG="${1:-${ROOT_DIR}/assets/icons/llestrade.png}"
ICONSET_DIR="${2:-${ROOT_DIR}/assets/icons/llestrade.iconset}"
ICNS_OUTPUT="${3:-${ROOT_DIR}/assets/icons/llestrade.icns}"

if ! command -v sips >/dev/null 2>&1; then
  echo "error: 'sips' not found. Install Xcode command-line tools on macOS." >&2
  exit 1
fi

if ! command -v iconutil >/dev/null 2>&1; then
  echo "error: 'iconutil' not found. It should be available on macOS with Xcode tools." >&2
  exit 1
fi

if [[ ! -f "${SRC_PNG}" ]]; then
  echo "error: master PNG not found at ${SRC_PNG}" >&2
  exit 1
fi

echo "Building icon set from ${SRC_PNG}"
rm -rf "${ICONSET_DIR}"
mkdir -p "${ICONSET_DIR}"

BASE_SIZES=(16 32 128 256 512)
for size in "${BASE_SIZES[@]}"; do
  sips -z "${size}" "${size}" "${SRC_PNG}" --out "${ICONSET_DIR}/icon_${size}x${size}.png" >/dev/null
  retina=$((size * 2))
  sips -z "${retina}" "${retina}" "${SRC_PNG}" --out "${ICONSET_DIR}/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil -c icns "${ICONSET_DIR}" -o "${ICNS_OUTPUT}"
echo "Created ${ICNS_OUTPUT}"
