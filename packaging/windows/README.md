# Windows Packaging Notes

The PyInstaller build is orchestrated through `scripts/build_dashboard.spec`, which already bundles the Qt plugins and `src/app/resources/` assets needed at runtime. The wrapper script in this directory standardises the environment setup for Windows operators.

## Usage

Run the wrapper from a PowerShell prompt on Windows:

```powershell
.\packaging\windows\build_app.ps1 [-FreshDist] [-PyInstallerConfigDir <path>] [-UvCacheDir <path>]
```

- `-FreshDist` removes `dist/win32/` before invoking PyInstaller so the bundle is rebuilt from scratch.
- `-PyInstallerConfigDir` overrides the working cache used by PyInstaller (defaults to `.pyinstaller/` in the repo root).
- `-UvCacheDir` overrides the cache used by `uv run` (defaults to `.uv_cache/` in the repo root).

The script drops the frozen payload at `dist/win32/llestrade/llestrade.exe`. PyInstaller retains its supporting DLLs and resources inside the same `llestrade` directory; distribute the entire folder to end users.

## Included Assets

- `src/app/resources/**` prompts/templates.
- Qt plugins (`platforms/`, `styles/`, `imageformats/`) and translations, collected automatically by the spec.
- Shared helpers in `src/config/`, `src/core/`, and `src/common/llm/` that the dashboard imports.

Exclude placeholder `.env` files, `var/` artifacts, and development-only directories from release bundles unless explicitly required.
