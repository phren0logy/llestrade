# macOS Packaging Notes

The PyInstaller flow lives at `scripts/build_dashboard.spec`. These notes capture the decisions for the unsigned `.app` bundle.

Build the bundle with:

```bash
PYINSTALLER_CONFIG_DIR=.pyinstaller UV_CACHE_DIR=.uv_cache uv run pyinstaller scripts/build_dashboard.spec
```

The spec emits `dist/darwin/Llestrade.app` so Finder launches straight into the GUI (no stray Terminal window) and nests PyInstaller’s `_internal` payload inside the bundle.

For convenience, you can run:

```bash
./packaging/macos/build_app.sh [--skip-icon] [--fresh-dist]
```

This wrapper regenerates the icon (unless skipped), sets up the PyInstaller cache directories, and drops the resulting `Llestrade.app` under `dist/darwin/`.

## Icon pipeline

1. Place the master 1024×1024 PNG at `assets/icons/llestrade.png`.
2. Run `./packaging/macos/build_iconset.sh` to produce `assets/icons/llestrade.iconset` and `assets/icons/llestrade.icns`. (You may need the Xcode command-line tools for `sips` and `iconutil`.)
3. The spec checks for `assets/icons/llestrade.icns` on macOS builds and embeds it as the bundle icon. The `.iconset` directory is just an intermediate artifact.

## Bundle contents

- **Included:** `src/app/resources/**` (prompts, templates, JSON assets), Qt plugins (`platforms`, `styles`, `imageformats`), and Qt translations collected via PyInstaller hooks. Add any new runtime assets explicitly to `datas` in the spec.
- **Excluded:** Development tooling (`tests/`, `docs/`, `scripts/`, `.venv`, git metadata), workspace artifacts (`var/logs/`, `var/test_output/`, caches), build outputs (`build/`, `dist/`), and any sample data not listed in the spec. PyInstaller already omits unused source modules.

This keeps the bundle lean while preserving everything the dashboard needs at runtime.
