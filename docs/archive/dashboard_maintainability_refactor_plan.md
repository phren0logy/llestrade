# Dashboard Maintainability Refactor Plan

## Goals & Guardrails
- Deliver a maintainable, testable dashboard codebase by replacing legacy monolith widgets and services with focused modules.
- Prefer clean breaks over compatibility shims; existing projects will be migrated once via a scripted tool.
- Expand structured logging and Phoenix tracing so long-running operations (conversion, highlights, bulk, reports) surface context-rich telemetry.
- Validate behaviour continuously: run targeted pytest suites (plus manual smoke tests against a sample project) after each major change set.

## Assumptions & Dependencies
- Only two legacy project bundles require migration; we can manually stage them for QA.
- Phoenix client and logging utilities already exist; we will extend them rather than introduce new observability stacks.
- Worker pool and Qt event plumbing stay in place; refactors focus on boundaries and responsibilities.

## Phase 1 – Project Workspace Decomposition (Highest Priority)
**Objectives**
- Split `ProjectWorkspace` (src/app/ui/stages/project_workspace.py) into dedicated tab widgets and controllers.
- Replace view-driven business logic with injected services for file tracking, bulk group orchestration, reporting, and prompt selection.

**Steps**
1. Establish `src/app/ui/workspace/` package.
   - Introduce `workspace_shell.py` containing the high-level container (signals + tab registration).
   - Stub submodules (`documents_tab.py`, `highlights_tab.py`, `reports_tab.py`, `bulk_tab.py`) with current UI surfaces.
2. Move tab-specific widget construction and signal wiring from the monolith into the new classes.
   - Keep public methods predictable (`refresh()`, `set_project(ProjectSession)`, `bind_actions()`).
   - Add slim dataclasses where UI needs to pass state (e.g., `HighlightTabState`).
3. Extract controller/services:
   - `workspace_sources.py`: manage root selection, rescan prompts, and tree state updates (currently `_refresh_file_tracker`, `_prompt_for_new_directories`, etc.).
   - `workspace_reports.py`: encapsulate template/prompt selection, validation, and worker invocation (mirrors `_start_report_job` block).
   - `workspace_bulk.py`: coordinate group runs, cancellations, and combined execution.
4. Rewrite `ProjectWorkspace` as a facade that composes shell + controllers.
   - Ensure all UI slots delegate to controllers.
   - Keep cross-tab coordination (e.g., workspace metrics updates) centralized.
5. Update imports across the app (welcome stage, main window, tests) to use the new workspace API.

**Testing / Verification**
- Add pytest-qt tests targeting each tab widget to confirm signal emission and state refresh.
- Run manual regression flows for:
  - New project creation → import → highlights.
  - Bulk group run (map + combined).
  - Report generation with custom prompt selections.

**Observability Enhancements**
- Instrument controllers with structured logger contexts (job id, project slug).
- Attach Phoenix spans around operations triggered from tabs, correlating with worker spans for full trace coverage.

## Phase 2 – Project Management & Metrics Services
**Objectives**
- Slim `ProjectManager` by extracting persistence, metrics, and bulk group repositories.
- Introduce a `ProjectSession` abstraction shared by UI and workers.

**Steps**
1. Create `src/app/core/project_state/` package:
   - Move dataclasses (`ProjectMetadata`, `ProjectCosts`, etc.) into dedicated modules.
   - Provide serialization helpers (`to_dict`/`from_dict`).
2. Carve out `ProjectStore` (read/write `.frpd`, manage auto-save timer).
   - `ProjectManager` delegates persistence, focusing on high-level orchestration.
3. Introduce `WorkspaceMetricsService` encapsulating calls to `FileTracker` and bulk repositories.
   - Expose explicit methods (`compute_dashboard_metrics`, `compute_group_metrics`).
4. Extract bulk-group management into `BulkGroupRepository` (load/save/delete/prune).
5. Refactor `ProjectManager` to compose store + repositories + metrics service.
   - Update worker and UI callers to use the new surface.

**Testing / Verification**
- Add isolated tests for `ProjectStore` (create, load, version mismatch paths).
- Extend existing bulk-group tests to cover repository edge cases.
- Re-run workspace tab tests ensuring new interfaces integrate cleanly.

**Observability Enhancements**
- Ensure `ProjectStore` logs structured events on read/write/auto-save with project id.
- Emit Phoenix spans for metrics computations to highlight expensive filesystem walks.

## Phase 3 – File Tracker & Metrics Pipeline
**Objectives**
- Separate snapshot models from scanning logic; clarify highlight/PDF rules.
- Reuse status derivations across UI and workers.

**Steps**
1. Split `src/app/core/file_tracker.py`:
   - `snapshots.py` (snapshot/dataclasses), `scanner.py` (load/scan), `workspace_metrics.py` (builders).
2. Implement `HighlightIndex` managing normalization, PDF eligibility, and pending counts.
3. Move combined-run status parsing into `bulk_status.py` shared with bulk workers.
4. Update `WorkspaceMetricsService` to use the new modules.

**Testing / Verification**
- Extend snapshot tests to cover highlight edge cases (PDF vs non-PDF).
- Add tests for `HighlightIndex` and bulk status parsing.
- Run regression suite on workspace metrics display.

**Observability Enhancements**
- Log scanner duration and discovered counts.
- Add Phoenix spans around `scan()` and `build_workspace_metrics()` for traceability.

## Phase 4 – Worker Pipelines (Report & Bulk Reduce)
**Objectives**
- Restructure workers into composable pipelines with reusable metadata and prompt utilities.

**Steps**
1. Introduce shared helpers under `src/app/workers/common/`:
   - `prompt_loader.py` consolidating validation and caching.
   - `metadata_writer.py` building document frontmatter.
   - `phoenix_span.py` context managers for instrumentation.
2. Refactor `ReportWorker`:
   - Split `_run` into stages (prepare inputs → draft → refine → persist).
   - Allow dependency injection for provider factory and token counter to simplify tests.
3. Refactor `BulkReduceWorker` similarly (plan → gather inputs → execute → persist).
   - Move manifest/signature helpers into `bulk_reduce/manifest.py`.
4. Update controllers to use the new helper APIs (minimizing duplicate validation).

**Testing / Verification**
- Unit test each pipeline stage with fixtures.
- Add integration-style worker tests using stub providers.
- Manual QA: run bulk + report jobs, inspect artefacts and logs.

**Observability Enhancements**
- Ensure each stage emits Phoenix spans (prepare, execute, persist) with group/report identifiers.
- Align log formats across workers to simplify troubleshooting.

## Phase 5 – Migration & Cleanup
**Objectives**
- Provide a one-off script to upgrade the two legacy projects to the new structure.
- Remove deprecated code paths and update documentation.

**Steps**
1. Author `scripts/migrate_workspace_v2.py`:
   - Detect old project layout, update metadata format, relocate files if necessary.
   - Write before/after summary and back up originals to `backups/legacy/<timestamp>/`.
2. Update docs (README, work_plan) to reference the new architecture and script usage.
3. Delete obsolete modules after successful migration and QA sign-off.

**Testing / Verification**
- Dry-run migration script against a copy of legacy projects; capture logs.
- Post-migration, exercise dashboard flows to confirm compatibility.

**Observability Enhancements**
- Log migration operations with project identifiers.
- Optionally emit a Phoenix trace for each migration run.

## Testing & Release Checklist
- [x] Run `uv run pytest tests/` after each phase before merging.
- [x] Maintain a manual smoke checklist (new project, conversion, highlights, bulk map+reduce, report).
- [x] Capture Phoenix trace screenshots for documentation after instrumentation updates.
- [x] Validate linting/formatting and update `docs/work_plan.md` progress.
- [x] Communicate breaking change impact to stakeholders and schedule migration script execution.
