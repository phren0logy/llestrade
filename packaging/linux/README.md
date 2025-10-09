# Linux Packaging Notes

PyInstaller packaging for Linux targets relies on the shared spec at `scripts/build_dashboard.spec`. The helper script in this directory standardises the environment setup so the frozen bundle consistently collects Qt plugins and dashboard resources.

## Usage

```bash
./packaging/linux/build_app.sh [--fresh-dist]
```

- `--fresh-dist` removes `dist/linux/` before the build so the output directory is regenerated from scratch.

The script exports sensible defaults for `PYINSTALLER_CONFIG_DIR` (`.pyinstaller/`) and `UV_CACHE_DIR` (`.uv_cache/`) relative to the repository root. Override them by pre-setting the environment variables if you need different cache locations.

PyInstaller emits the frozen files under `dist/linux/llestrade/`; the executable itself lives at `dist/linux/llestrade/llestrade`. Ship the entire directory so the binary can locate its accompanying Qt plugins and resources.

## Included Assets

- `src/app/resources/**` prompts, templates, and JSON configuration files.
- Qt plugins (`platforms/`, `imageformats/`, `xcbglintegrations/`) and Qt translations resolved via `PySide6.QtCore.QLibraryInfo`.
- Core/shared modules imported by the dashboard (`src/config/`, `src/core/`, `src/common/llm/`).

As with the macOS build, omit development artefacts (`tests/`, `docs/`, `.env`, `var/`) from the release package unless explicitly required.
