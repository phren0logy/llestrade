# Repository Guidelines

## Project Structure & Module Organization
`main.py` still boots the legacy tabbed UI; `main_new.py` hosts the in-progress dashboard workflow. Legacy code now lives in `src/legacy/`, while `src/new/` contains dashboard stages, workers, and core classes from `docs/work_plan.md`. Shared helpers stay in `src/config/`, `src/core/`, and `llm/`; prompts live in `prompt_templates/`, templates in `templates/`, scripts in `scripts/`, tests in `tests/`, and build artefacts in `test_output/` and `logs/`.

## Build, Run, and Development Commands
Install dependencies with `uv sync`; this repo targets Python 3.12+. Launch the stable baseline via `uv run main.py`. Exercise the dashboard refactor with `uv run main_new.py` (or `uv run main.py --new-ui` while entry points migrate) and expect churn until Priority 0 completes. `./run_debug.sh` or `DEBUG=true uv run main.py` surface instrumentation; `uv run scripts/setup_env.py` verifies credentials.

## Coding Style & Naming Conventions
Python modules follow snake_case filenames with 4-space indentation and type hints. Classes use CapWords, Qt signals stay uppercase with underscores, and worker classes end with `Worker`. New dashboard modules should stay small (~400 lines) with dataclasses in `src/new/core/`. Keep configuration keys lowercase, align prompts to the `topic_action.md` pattern, and document public functions as needed. Run `uv run pytest tests/` before committing.

## Testing Guidelines
Tests rely on `pytest` and `pytest-qt`; name files `test_*.py` and mirror the source tree. New dashboard code currently lacks coverage—prioritize business-logic tests for `src/new/core/` classes and worker behaviors. Use fixtures for LLM stubs, store artefacts under `test_output/`, and run `uv run pytest --cov=. tests/` to track coverage. Capture before/after screenshots when UI flows change.

## Commit & Pull Request Guidelines
Commit messages follow the existing imperative, sentence-cased style (`Fix project creation workflow issues`). Reference relevant checklist items from `docs/work_plan.md` when advancing the dashboard refactor. Group logical changes per commit, summarize user impact, list executed commands, and include screenshots for UI tweaks. Call out env requirements or migrations and tag reviewers closest to the touched module.

## Configuration & Secrets
Copy `config.template.env` to `.env` and populate provider keys (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, Azure credentials). Avoid hardcoding secrets; use the keyring helper in `src/config`. Scrub PII from `logs/` before sharing and rotate credentials after exporting crash data.

## Dashboard Refactor Focus
Treat `docs/work_plan.md` as the source of truth. Priority 0 centers on shipping the dashboard workspace: land `FileTracker`, summary groups, and `QThreadPool` consolidation before touching legacy cleanup. Breaking changes are fine—just preserve the project folder structure (`imported_documents/`, `processed_documents/`, `summaries/`) and keep implementations observable and simple.
