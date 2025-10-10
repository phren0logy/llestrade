# Project Placeholder Unification & Prompt Preview Plan

## Goals
- Replace fixed project metadata with editable key/value placeholders sourced from markdown lists.
- Provide a unified placeholder registry leveraged by project creation, project settings, prompt previews, and both map/reduce bulk jobs.
- Highlight placeholder coverage in the UI, warn (but not block) when prompts reference empty placeholders, and render previews with inline colour cues.
- Standardise system placeholders (project metadata, timestamps, source file details) and support aggregated placeholders for combined bulk operations.
- Update automated tests to reflect the new behaviours; drop legacy tests tied to fixed placeholder sets.

## Non-Goals / Constraints
- No backward compatibility layer for legacy project files; new structure is breaking.
- Prompt/template locations remain unchanged.
- No provenance tracking between user-defined and system placeholders; all entries share a single namespace.

## Terminology
- **Placeholder set**: Markdown file containing one placeholder key per line (bulleted or plain, snake_case).
- **Project placeholders**: The editable list of keys/values stored inside a project file.
- **System placeholders**: Automatically provided keys (read-only in the UI) such as `{project_name}`, `{timestamp}`, `{source_pdf_filename}`.
- **Map job**: Bulk action run per document.
- **Reduce job**: Combined bulk action that consumes multiple documents at once.

## Phase 1 – Resource & Settings Foundation
1. **Bundled assets**
   - Create `src/app/resources/placeholder_sets/` with initial markdown files (mirroring prompt/template distribution).
   - Extend any sync scripts (e.g., `sync_prompts.py`) or resource loaders to include placeholder sets.
2. **Workspace settings**
   - Update the settings model to add `placeholder_dirs` (bundled mirror + custom directory).
   - Surface the new preference in the settings UI next to prompts/templates, reusing folder pickers and sync toggles.
3. **Registry service**
   - Implement `PlaceholderSetRegistry` (similar to prompt/template registries) that indexes bundled/custom placeholder files, provides metadata (name, origin), and exposes parsed key lists.
   - Hook registry refresh into existing settings change signals so project creation and settings panels always use the latest directory contents.
4. **Test cover**
   - Add unit tests ensuring the registry discovers bundled and custom markdown sets and de-duplicates names.

## Phase 2 – Parsing & Model Architecture
1. **Markdown parser**
   - Implement a parser that strips leading bullets (`-`, `*`, or digits with dots), trims whitespace, and validates snake_case keys.
   - Reject duplicates within a file; ensure parser returns keys in declaration order.
2. **Project placeholder model**
   - Introduce `ProjectPlaceholders` dataclass (list of entries: key, value, read_only flag).
   - Add serialization helpers for storing in the project JSON (e.g., under `"placeholders": [{"key": "...", "value": "...", "read_only": false}, ...]`).
   - Provide merge utilities to combine project entries with system placeholders at runtime.
3. **System placeholders**
   - Define constants for:
     - `{project_name}`
     - `{timestamp}` (resolve at execution time; ISO 8601 with timezone)
     - `{source_pdf_filename}`, `{source_pdf_relative_path}`, `{source_pdf_absolute_path}`, `{source_pdf_absolute_url}`
     - Aggregated reduce placeholders (e.g., `{reduce_source_table}`, `{reduce_source_list}` – see Phase 5)
   - Ensure system keys are reserved (cannot be added/removed by users).
4. **Tests**
   - Unit tests for parser (bulleted/plain inputs, invalid keys).
   - Tests for project placeholder serialization/deserialization and system key reservation.

## Phase 3 – Project Creation Workflow
1. **Wizard updates**
   - Add a “Placeholders” step in the new project wizard:
     - Dropdown / browser for selecting a bundled or custom placeholder set.
     - Display parsed keys in a table with editable value column.
     - Provide “+” to add custom keys (validate snake_case) and “–” to remove selected user-defined keys.
   - Persist the final list of keys & values into the project file upon creation.
2. **Empty state handling**
   - Allow projects to start with zero placeholders (user can add later).
   - Warn if required fields (e.g., project name) are missing before finish.
3. **Testing**
   - pytest-qt coverage for the wizard: selecting sets, adding/removing keys, validation on save.

## Phase 4 – Project Settings Editing
1. **Settings panel**
   - Embed the same editable table inside project settings:
     - Read-only rows for system placeholders (grayed out, no delete button).
     - Buttons to import another placeholder file (replaces key list; preserve values for keys that still exist) or export current keys as markdown.
   - Ensure changes update the persisted project file immediately (respecting auto-save behaviour).
2. **Access flow**
   - Add entry point from the workspace UI to open project settings for placeholder editing post-creation.
3. **Tests**
   - pytest-qt tests for adding/removing keys, importing markdown, ensuring system keys stay immutable, persistence checks.

## Phase 5 – Prompt Analysis & Placeholder Map
1. **Placeholder analyzer**
   - Build `PromptPlaceholderAnalyzer` that scans prompt text for `{snake_case}` tokens.
   - Provide API returning:
     - `used_keys`: placeholders found in prompt(s).
     - `unused_keys`: project/system keys not referenced.
     - `missing_keys`: used keys with no non-empty value.
2. **Map placeholder assembly**
   - On job execution, merge:
     - Project placeholder values.
     - System placeholders resolved for the current project.
     - Per-file placeholders for map jobs (`{source_pdf_*}` based on the original PDF path associated with the markdown being processed).
3. **Reduce placeholder assembly**
   - Define aggregated placeholder outputs for combined jobs:
     - `{reduce_source_list}`: newline-delimited `- <relative_path>` entries.
     - `{reduce_source_table}`: markdown table with columns (Filename, Relative Path, Absolute Path).
     - `{reduce_source_count}`: integer count of files combined.
   - Include `{source_pdf_*}` placeholders only if a single document is selected; otherwise leave blank.
4. **Tests**
   - Unit tests for the analyzer and preview helpers (`tests/app/core/test_placeholders_analyzer.py`).
   - Coverage for map/reduce placeholder assembly (`tests/app/core/test_bulk_analysis_runner.py`, `tests/app/core/test_project_placeholder_mapping.py`).
5. **Required vs optional classification**
   - During prompt selection, present a control (e.g., checkbox or dropdown) to mark each used placeholder as required or optional; default to `required` for keys declared by the prompt author via metadata (future enhancement) or previously saved user preference.
   - Enforce that `{document_contents}` is required for map jobs (cannot be unchecked); warn if a prompt omits it.
   - Persist placeholder requirement choices alongside project prompt configuration for re-use.
   - Validation rules:
     - Missing values for required placeholders trigger blocking warnings (user must override to proceed).
     - Missing optional placeholders continue to show non-blocking warnings.
   - Extend analyzer outputs to include `required_missing` vs `optional_missing` sets.

## Phase 6 – Prompt Selection & Preview UI
1. **UI layout**
   - In the prompt selection dialog/panel:
     - Add a preview toggle: “Raw” (original file text) vs “Preview” (values substituted).
     - Inline highlighting using rich text:
       - Green span when a placeholder has a value.
       - Red span when value is empty/missing.
     - Side panel listing:
       - Used placeholders (with status icons/colour).
       - Unused placeholders.
       - Clicking a key opens/focuses the placeholder editor in project settings.
2. **Behaviour**
   - In preview mode, render missing values as empty strings (no `{placeholder}` text) but keep the red highlight to signal absence.
   - Support long placeholder values; ensure the preview scrolls gracefully.
3. **Warning UX**
   - On job kickoff, if analyzer reports missing values, show a non-blocking warning dialog summarising missing keys with options:
     - “Edit placeholders” (opens project settings).
     - “Proceed anyway”.
   - Distinguish required vs optional placeholders in the dialog; required defaults to “Proceed anyway” being disabled until the user ticks an “Override” confirmation.
4. **Tests**
   - pytest-qt tests verifying toggles, highlighting logic (inspect generated HTML), warning dialog behaviour.

## Phase 7 – Runtime Integration
1. **Controller updates**
   - Modify workspace controllers to request the merged placeholder map from `ProjectSession` at execution time.
   - Ensure timestamp placeholder resolves per run.
2. **Worker integration**
   - Centralise placeholder substitution in workers (reports, highlights, bulk) to consume the map before handing prompts to LLM providers. ✔️ `BulkAnalysisWorker`, `BulkReduceWorker`, and `ReportWorker` now consume project/system placeholders.
   - Confirm bulk workers receive file-specific metadata; reduce workers receive aggregated placeholders. ✔️ Implemented via YAML front-matter parsing and `system_placeholder_map`.
3. **Bulk action reconfiguration**
   - When a user launches an existing bulk action (from the bulk tab table or history), route them back to the original configuration screen with all settings prefilled (prompt selection, placeholder requirements, file/folder selection).
   - Allow users to modify the target files/folders (including newly added directories) before resuming; persist the changes to the bulk group definition.
   - After saving modifications, display a confirmation dialog summarising the differences (added/removed sources, prompt changes) and warn that prior outputs may be stale; require explicit confirmation before overwriting the stored configuration.
   - Update bulk metadata timestamps/status so dashboards reflect the change.
   - Tests: pytest-qt coverage ensuring the configuration dialog loads with previous selections, supports edits, persists updates, and emits the warning.
4. **Telemetry**
   - Extend logging to record which prompts/placeholder sets are used (no values logged).
   - Optional: add Phoenix spans around placeholder assembly for debugging.
5. **Tests**
   - Add integration-style worker tests (still outstanding) covering placeholder substitution end-to-end.

## Phase 8 – Cleanup & Documentation
1. **Remove obsolete code**
   - Delete legacy placeholder constants, fixed project fields, and superseded tests.
2. **Docs**
   - Update user docs/work_plan to describe placeholder sets, editing workflow, and prompt previews.
   - Add developer notes on the placeholder registry and system keys.
3. **QA Checklist**
   - Manual verification: create project with bundled placeholders, run map/reduce jobs, inspect previews and outputs. (pending)
   - Bulk run verifying aggregated placeholders render links to original PDFs. (pending)

## Open Questions / Follow-ups
- Decide on default bundled placeholder sets and their contents.
- Confirm formatting for `{reduce_source_table}` (column headers, alignment) before implementation.
- Consider future enhancements (e.g., placeholder value templates, autofill suggestions).
- Post-implementation, review all placeholders marked as required; if they represent static project attributes, ensure they surface in the project setup step rather than solely in prompt selection. (Dynamic placeholders such as `{document_contents}` remain excluded from project setup.)
