# Placeholder Reference

This document describes how placeholders work across the Llestrade dashboard. Use it as the canonical guide when updating prompts, building new workspace flows, or diagnosing preview and validation issues.


## Why placeholders matter

- They let every project capture client- and matter-specific details once and reuse them everywhere the UI formats prompts.
- They provide per-run context (for example, the original PDF’s filename) so bulk and report jobs can keep traceability back to the source material.
- They power the prompt preview experience: the analyser highlights missing substitutions, flags required keys, and drives the warning dialogs shown before long-running jobs.


## Placeholder flavors

### Project placeholders

- Stored on the project and edited through the new project wizard or the project settings dialog.
- Keys must be `snake_case`; values are free-form text (they can be long documents).
- Entries are persisted in the project file and included in `ProjectManager.placeholder_mapping()`.
- System keys appear beside user-created keys but are read-only; they are regenerated whenever metadata changes.

### System placeholders

Generated automatically by `src/app/core/placeholders/system.py` and merged into the project map everywhere prompts are rendered.

| Key | Populated with | Notes |
| --- | --- | --- |
| `project_name` | Current project/case name | Always read-only |
| `timestamp` | ISO-8601 UTC timestamp captured when a run starts | Changes per job |
| `source_pdf_filename` | Name of the PDF tied to the current markdown document | Set per document during bulk map runs |
| `source_pdf_relative_path` | Project-relative path to that PDF | Requires the conversion metadata to contain `sources` |
| `source_pdf_absolute_path` | Absolute path to the PDF | Useful for linking back to the original evidence |
| `source_pdf_absolute_url` | URL-encoded absolute path | Safe to embed in `x-callback-url` flows (spaces become `%20`, slashes remain `/`) |
| `reduce_source_list` | Markdown bullet list of inputs used in a combined run | Only populated for combined/bulk-reduce jobs |
| `reduce_source_table` | Markdown table (filename, relative path, absolute path) | Lets prompts reference structured lists |
| `reduce_source_count` | Stringified count of combined inputs | |

System keys are injected in three layers:

1. `ProjectManager.placeholder_mapping()` provides `project_name` and a fresh `timestamp` every call.
2. `BulkAnalysisWorker` augments the map per document with source metadata.
3. `BulkReduceWorker` adds combined-input summaries; `ReportWorker` keeps the run timestamp and project metadata.

Dynamic placeholders such as `{document_content}` are not stored on the project. Workers supply them at runtime when formatting prompts or when the preview dialog truncates converted content.


## Placeholder sets and storage locations

Placeholder lists are managed just like prompts and templates:

- Bundled lists live under the application resources (the repository provides `resources/placeholder_sets`). They are synced into the user workspace at `~/Documents/llestrade/placeholder_sets/bundled`.
- User-authored lists live in `~/Documents/llestrade/placeholder_sets/custom`.
- Each list is a Markdown file. Every non-empty line (with or without Markdown bullets) becomes a key. Lines must contain a single `snake_case` token; defaults and sample values are not supported.
- `PlaceholderSetRegistry` merges the two directories. Custom files override bundled ones when names clash.

Example `matter_defaults.md`:

```markdown
# Keys used for Jones v WA
- client_name
- opposing_counsel
- incident_summary
- document_contents  <!-- keep for map runs -->
```

The UI surfaces the registry anywhere a placeholder set picker appears. Creating or importing new files writes to the `custom` directory so they can be checked into source control or shared between team members if desired.


## Editing placeholders in the UI

### New Project dialog

1. Choose a bundled or custom placeholder set. The combo-box mirrors the prompt/template “Settings” pattern, and you can refresh it after dropping new files on disk.
2. Add/remove keys with the `+`/`Remove` buttons. Entries follow the ordering in the grid and are validated as you edit.
3. Import a Markdown list or export the current table for documentation.
4. System placeholders (project name, timestamp, etc.) are locked but visible so users understand what will be available later.

### Project Settings dialog

Accessible from the project workspace, the settings dialog hosts the same `PlaceholderEditorWidget`. Teams can revisit and update values without recreating the project. Edits are immediately persisted to the `.frpd` file.

Validation rules baked into the editor:

- Keys must be `snake_case`, start with a letter, and cannot contain spaces or punctuation.
- Values are plain text. No substitution is performed until a worker renders a prompt.
- Duplicate keys are de-duplicated automatically.


## Prompt previews and analysis

The preview dialog (`PromptPreviewDialog`) is shared by bulk groups, report flows, and any future workspace panels. It provides:

- **Raw view** – shows the template with placeholders highlighted. Green = substituted, red = missing, bold = required.
- **Preview view** – shows the final text with values substituted. Missing placeholders render as a red-highlighted blank.
- **Usage sidebar** – lists used vs. unused placeholders, indicates which are required, and displays warnings for missing required/optional values.
- **Toggle between system/user prompts** side by side.

The analyser behind the dialog (`PlaceholderAnalysis`) also powers:

- The placeholder column in the bulk analysis table.
- Pre-run warnings when required values are missing.
- The requirements matrix inside the bulk-group editor.


## Placeholder requirements and validation

Bulk analysis groups track a `placeholder_requirements` map. The dialog automatically scans the selected system/user prompts and presents a checklist of discovered placeholders:

- Mark a key as **required** to force a warning (with an override) whenever the map run is missing a value.
- Leave it optional to expose the placeholder in the UI while still allowing empty runs.
- Requirements are saved with the group and surface in the bulk tab tooltip/column so operators know what still needs attention.

The controller enforces additional rules:

- Per-document runs always require `document_content`; it’s injected automatically when previewing but still needs content present in the converted markdown.
- Combined runs expose `reduce_source_*` placeholders as optional because they’re generated dynamically.
- Before executing, the controller shows a confirmation dialog listing any missing required or optional values so users can cancel, edit placeholders, and retry.


## Runtime substitution by worker

### Bulk map (per-document) worker

- Merges project placeholders with system keys and document-specific context.
- Reads the `sources` metadata embedded in converted markdown to recover the original PDF path. If conversion did not populate that metadata, it falls back to the markdown file path.
- Exposes both raw and URL-encoded absolute paths (`source_pdf_absolute_path`, `source_pdf_absolute_url`) so prompts can embed filesystem links or `x-callback-url` targets safely.
- Records the placeholder map in the worker manifest along with the prompt hash, so reruns are skipped if nothing changed.

### Bulk reduce (combined) worker

- Builds aggregate context for every input file: list, table, and count.
- Uses the same system placeholders to enrich the combined prompt so summarised outputs can reference each contributing document.
- Validates placeholder requirements before running so combined prompts still get the values they expect.

### Report worker

- On every run, the worker assembles a base placeholder map (project values + system values + supplied overrides).
- Generation and refinement system prompts are formatted with the map before calling the provider.
- Section prompts, the combined draft, and the refinement step all receive the same map.
- Draft and refined outputs store the placeholder map in their front matter (`extra.placeholders`). This makes it easy to audit which values were active when the report was generated.


## Naming conventions and best practices

- **Snake case only** – enforcement happens in the editor and parser.
- **One key per line** in Markdown files. Bullets (`-`, `*`, numbered) are ignored; the remaining token becomes the key.
- **No default values** in placeholder lists; use the editor to populate defaults on a per-project basis.
- **Keep keys stable** – changing key names breaks existing prompts. Introduce new keys instead, then migrate prompts in one pass.
- **Document dynamic placeholders** (`document_content`, `source_pdf_absolute_url`, `reduce_source_list`, etc.) in prompts, but do not add them to the project list.
- **Treat values as plain text** – workers don’t interpret Markdown or JSON structures unless a prompt explicitly does so.


## Frequently used keys and recommendations

| Scenario | Recommended keys |
| --- | --- |
| Map (per-document) bulk runs | `document_content` (required), `client_name`, `case_number`, any investigation-specific tags |
| Combined bulk runs | `reduce_source_list`, `reduce_source_table`, `reduce_source_count`, plus the same project-level metadata |
| Reports | Project metadata (`client_name`, `case_name`, `matter_summary`), `transcript_notes`, `audience`, etc. These become available to both the generation and refinement prompts. |

Remember to review required keys at the end of each planning phase. If a placeholder must be filled for every project (for example, `client_name`), move it into the project creation checklist so new files are never missing critical context.


## Directory recap

```
~/Documents/llestrade/
├── placeholder_sets/
│   ├── bundled/  # auto-synced from the app bundle
│   └── custom/   # user-authored lists, import/export lives here
├── prompts/
├── templates/
└── ...
```

Placing a new Markdown file in either directory and refreshing the UI is all that’s required to surface a new placeholder set.


## Troubleshooting checklist

- **Missing values before a run** – open the prompt preview to see which keys require attention, then edit the project placeholders or the group’s requirements.
- **Unexpected blank substitution** – ensure the value isn’t longer than expected (the preview truncates only for display) and confirm the placeholder key matches exactly (case-sensitive).
- **System metadata missing** – verify converted markdown front matter includes the `sources` array with `path` or `relative` entries; re-run conversion if necessary.
- **Placeholder set not appearing** – check the Markdown file for duplicate or non-snake-case keys, and ensure it lives in `placeholder_sets/custom` or `bundled`.

For deeper debugging, inspect the worker manifests in the project’s `bulk_analysis/<group>/` folder or review the report draft/refined front matter; both capture the placeholder maps used during execution.
