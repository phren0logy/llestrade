# Bulk Analysis Enablement Plan

This document outlines the work required to ship the bulk-analysis experience in the new dashboard UI without keeping it behind a feature flag. The goal is to reuse the mature pieces from the legacy summarisation pipeline while aligning with the new architecture (QThreadPool workers, Dashboard metrics, renamed `bulk_analysis` storage).

## 1. Clean Up Terminology & Storage

- Rename the `summaries/` storage tree to `bulk_analysis/` throughout the persistence layer (no migration step needed—new runs should simply use the new folder):
  - Update `SummaryGroup` persistence in `src/new/core/summary_groups.py` to write configs under `project_dir / "bulk_analysis" / <slug> / config.json`.
  - Adjust `ProjectManager.project_data`, `save_summary_group`, `load_summary_groups`, `delete_summary_group`, and related tests.
  - Switch the workspace “Open Folder” action and table copy to say “Bulk Analysis” and point to the new directory.
- Update the unit tests in `tests/new_ui/test_summary_groups.py` and any other references to expect the new folder name.

## 2. Introduce a Real Bulk Analysis Worker

- Implement a new `BulkAnalysisWorker` in `src/new/workers/` as a `QRunnable` (matching `ConversionWorker`). Core responsibilities:
  - Resolve the group’s selected files and folders to actual converted markdown paths.
  - Load group prompts (system/user) if provided; fall back to defaults via `PromptManager`.
  - Instantiate the configured LLM provider using `src/common/llm/factory.py` and run summaries over each document (supporting chunking via `src/common/llm/chunking.py`).
  - Persist results under `project_dir / bulk_analysis / <group.slug> / outputs/…` with a consistent file naming scheme.
  - Emit progress, completion, and error signals so the UI can respond.
  - Honour cancellation requests by checking a shared `threading.Event` between chunk submissions and returning early if set. LLM SDKs do not expose hard-stops today, so cancellation should simply stop enqueuing new chunks and ignore late responses.
- Extract the prompt/chunk orchestration from `src/legacy/workers/llm_summary_thread.py` into a shared helper module (e.g., `src/new/core/bulk_analysis_runner.py`) so both the new worker and any future engines reuse the battle-tested logic without duplicating thread code.
- Keep the existing factory usage for now; note a future enhancement could swap in a `litellm`-backed factory once cancellation hooks exist.

## 3. Wire the Workspace UI to the Worker Pool

- Replace the current 2-second `QTimer` simulation (`_start_group_run`) with logic that:
  - Builds a `BulkAnalysisWorker` instance for the selected group.
  - Submits it to the global `QThreadPool` (mirroring how conversions run).
  - Tracks in-flight jobs, updates the table row status, and streams log entries into the “Progress” tab using the existing workspace logger plumbing.
  - Implements cancellation by calling a `cancel()` method on the worker.
- Ensure the “Run” button is disabled while a group is executing and re-enabled afterward.
- Remove the temporary message boxes that say “Bulk analysis completed” in favour of UI status indicators/log rows.
- Refresh the table model from the store when the worker finishes so status persists after navigation or reloads.

## 4. Update Metrics & Project Status

- Extend `DashboardMetrics` (in `src/new/core/file_tracker.py`) to include bulk-analysis coverage (e.g., documents processed per group) by reusing the existing stats structure—only add the minimal new fields needed.
- Update the welcome screen and workspace counters to display “Bulk analysis X/Y” alongside conversion stats.
- Invoke a metrics refresh when a worker completes so the UI stays in sync.

## 5. Testing & Validation

- Unit tests:
  - `SummaryGroup` save/load/delete hitting the new `bulk_analysis` folder.
  - `BulkAnalysisWorker` processing a small markdown document end-to-end (mocking LLM providers) and writing outputs to the correct directory.
  - Workspace integration tests that simulate a worker run and ensure the table status/progress signals behave correctly.
- Regression test that the Bulk Analysis tab renders by default when `FeatureFlags.summary_groups_enabled` is set to `True`.
- Manual smoke test:
  - Create a sample project with converted markdown.
  - Define a bulk-analysis group with prompts.
  - Run the worker, check output files in `bulk_analysis/<group>/outputs/`, and verify metrics/UI updates.

## 6. Enable the Feature

- Once the worker, storage rename, metrics, and tests are in place, flip `FeatureFlags.summary_groups_enabled` to `True` by default.
- Update release notes/docs to reflect that the Bulk Analysis tab is now part of the standard workflow.
