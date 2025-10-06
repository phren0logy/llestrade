# Distribution Prep Notes

## Packaging Strategy
- Use PyInstaller to freeze `main.py` as the entry point.
- Include `src/app/resources/` as bundled data so prompts/templates ship with the binary.
- Load resources at runtime via `config.paths.app_resource_root()`, which transparently resolves paths when frozen (uses `sys._MEIPASS`).
- Generate a lockfile for the build with `uv export --format requirements-txt > build/requirements.txt` before running PyInstaller to keep the frozen environment reproducible.

## Runtime Secrets
- The application no longer auto-loads placeholder keys from `config.template.env`; users must provide their own `.env` or enter credentials through the UI (stored via `SecureSettings`).
- Do **not** ship a populated `.env`. Document the required variables (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `AZURE_*`) in release notes.

## Dependency Considerations
- `PySide6` requires its Qt plugin folders (`platforms`, `imageformats`, `styles`) and an accompanying `qt.conf`. Configure the PyInstaller spec to collect these directories via `PySide6.QtCore.QLibraryInfo`.
- `pypandoc-binary` embeds Pandoc; ensure `PYPANDOC_PANDOC` is discovered or copy the binary into the bundle with `--add-binary` if detection fails.
- `keyring` backends vary per OS. The frozen build should include the default backend for each target platform; add optional backends as needed.
- Network SDKs (`anthropic`, `openai`, `google-generativeai`, `azure-ai-documentintelligence`) are heavyweight; keep them but consider conditional loading in the UI if footprint becomes an issue.

## Build Next Steps
1. Add a PyInstaller spec (`scripts/build_dashboard.spec`) capturing data files and hidden imports.
2. Create `scripts/build_dashboard.py` or shell wrappers to orchestrate `uv export`, PyInstaller, and artifact staging per platform.
3. Extend CI to execute the bundling pipeline and attach artifacts for macOS, Windows, and Linux.

