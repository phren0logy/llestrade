# Dashboard Refactor Plan

## Objective

Move the active dashboard UI code out of `src/new/` into a clean top-level package (`src/app/`), remove stale references to the legacy UI, and align the tests/resources/tooling with the new structure.

## Detailed Steps

### 1. Create `src/app/` package
- [x] Introduce a new `src/app/__init__.py` that re-exports the primary dashboard interfaces (e.g., `SecureSettings`, `ProjectManager`, etc.).
- [x] Move modules from `src/new/` into `src/app/` with the following structure:
- `src/app/core/` → domain/business logic (`project_manager.py`, `file_tracker.py`, `bulk_analysis_groups.py`, `feature_flags.py`, `workspace_controller.py`, etc.)
  - `src/app/services/` → optional layer for conversion/bulk runners if further separation is desired (`conversion_manager.py`, `bulk_analysis_runner.py`, helper registries).
  - `src/app/ui/`
    - `ui/stages/` → formerly `src/new/stages/`
    - `ui/dialogs/` → formerly `src/new/dialogs/`
    - `ui/widgets/` → formerly `src/new/widgets/`
  - `src/app/workers/` → formerly `src/new/workers/`
- [x] Update all relative imports inside the moved modules to reflect the new package layout (`from src.new...` → `from src.app...`).

### 2. Normalize entry points
- [x] Fold `main_new.py` into the package:
  - Extract the main window code into `src/app/main_window.py` (or similar) and expose a `run()` helper from `src/app/__init__.py`.
  - Optionally add `src/app/__main__.py` so `python -m src.app` launches the dashboard directly.
- [x] Simplify `main.py` so it just imports and executes the `src.app` entry point (no `sys.path` manipulation).
- [x] Update shell scripts (`run_app.sh`, `run_new_ui.sh`, `run_debug.sh`) to reference the new module path.

### 3. Align tests with the new package
- [x] Rename test packages to mirror `src/app`:
  - `tests/new_ui/` → `tests/app/ui/`
  - `tests/new_workers/` → `tests/app/workers/`
  - Any other `tests/new_*` → matching `tests/app/...`
- [x] Update import paths inside tests and fixtures from `src.new...` to `src.app...`.
- [x] Verify pytest discovery still works (`uv run -m pytest tests/app/...`).

### 4. Resource & configuration cleanup
- [x] Evaluate `templates/` and `prompt_templates/` – move dashboard-specific resources under `src/app/resources/`.
- [x] Ensure runtime artefacts (`var/app_settings.json`, `var/logs/`, `var/test_output/`) live under `var/` with gitignored contents.
- [ ] Document the new layout in README and any developer onboarding docs.

### 5. Tooling and documentation updates
- [ ] Update scripts (`scripts/update_imports.py`, etc.) to search/replace `src.new` → `src.app`.
- [ ] Review logging configuration (`src/config/logging_config.py`) and observability code for references to the old package path.
- [ ] Update docs (e.g., `docs/work_plan.md`, runbooks) to reference `src/app` instead of `src/new`.

### 6. Verification
- [ ] Run targeted pytest suites (`tests/app/...`) to confirm imports are correct.
- [ ] Launch the application via `uv run main.py` to ensure the dashboard starts without import errors.
- [ ] Check packaging/build scripts if any (PyInstaller, etc.) to ensure resource paths are still valid.

### Notes
- `src/core/`, `src/common/llm/`, and `src/config/` remain as shared libraries – avoid cyclic imports by keeping `src/app` dependent on them but not vice versa.
- Keep commits logical (e.g., one for moving files, one for import updates, one for test renames) to make rollbacks easier if something breaks.
- If emergency rollback is needed, refer to commit `fbf98c2` (legacy removal) or earlier for the pre-move structure.
