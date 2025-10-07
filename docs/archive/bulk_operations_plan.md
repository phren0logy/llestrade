# Bulk Operations Plan — Per‑document and Combined

Date: 2025-09-29

## Goals

- Introduce two first‑class bulk operation types:
  - Per‑document: apply one prompt to many markdown files (current behavior)
  - Combined: merge many files, then apply a single prompt once
- Allow multiple independent Combined operations with per‑folder and per‑file selection from:
  - Converted documents
  - Outputs from any Per‑document operation(s)
- Keep FileTracker semantics unchanged (map/per‑document coverage). Track Combined status separately (latest artifact, stale flag) without a database.
- Add page markers and source metadata to conversion outputs to enable future deep links to original PDFs.

## Terminology (UI)

- Operation types shown to users:
  - Per‑document
  - Combined
- Replace “summary/summaries” wording in labels with “Per‑document” or “Combined.”

## Directory & Artifacts

- Per‑document outputs (unchanged): `bulk_analysis/<group.slug>/outputs/<relative>.md`
- Combined outputs (new): `bulk_analysis/<group.slug>/reduce/combined_YYYYMMDD-HHMM.md`
- Combined manifest (new): `bulk_analysis/<group.slug>/reduce/combined_YYYYMMDD-HHMM.manifest.json`

Notes:
- Timestamp format is local time with dash: `YYYYMMDD-HHMM`.
- Manifests record the input set and file mtimes for “stale” detection.

## Data Model Changes

File: `src/app/core/bulk_analysis_groups.py`

- Add fields:
  - `operation: Literal["per_document", "combined"] = "per_document"`
  - Combined input sets:
    - `combine_converted_files: list[str] = []`
    - `combine_converted_directories: list[str] = []`
    - `combine_map_groups: list[str] = []`            # slugs
    - `combine_map_files: list[str] = []`             # `group_slug/rel/path.md`
    - `combine_map_directories: list[str] = []`       # `group_slug/rel/dir`
  - Combined options:
    - `combine_order: Literal["path", "mtime"] = "path"`
    - `combine_output_template: str = "combined_{timestamp}.md"`
    - `use_reasoning: bool = False`  # if true, may set temperature=1.0 for thinking models
- Version bump: `SUMMARY_GROUP_VERSION` incremented. On version mismatch, surface a reusable error:
  - “This operation uses an invalid or unsupported format. Please recreate it using the latest UI.”
- Backward compatibility: not supported (explicit choice).

## UI Changes

### Group Dialog — `src/app/ui/dialogs/summary_group_dialog.py`

- Add Operation selector: `Per‑document | Combined`.
- When Combined is selected:
  - “Converted Documents” tree with folder+file checkboxes (reused from existing Documents tab logic).
  - “Per‑document Outputs” tree rooted at `bulk_analysis/<slug>/outputs/` with per‑group top‑level nodes; folder+file selection within each.
  - Prompt pickers for system and user prompts (same behavior as Per‑document).
  - Options:
    - Order: `by path` | `by modified time`
    - Output filename template (defaults to `combined_{timestamp}.md`)
    - “Use reasoning” checkbox (see Provider Behavior)
  - Preview: display estimated combined token count using existing TokenCounter.

### Workspace — `src/app/ui/stages/project_workspace.py`

- Table row additions:
  - Type chip: `Per‑document` or `Combined`.
  - For Combined operations, show:
    - Actions: `Run Combined`, `Cancel`, `Open Folder`, `Open Latest`, `Delete`
    - Status text: `Inputs: N`, `Last run: <time>`
    - “Stale” chip when any selected input changed since the last run

## Workers

### BulkReduceWorker — `src/app/workers/bulk_reduce_worker.py` (new)

- Input resolution:
  - Expand `combine_converted_*` paths under `converted_documents/`.
  - Expand `combine_map_*` under `bulk_analysis/<slug>/outputs/`.
  - Allow both per‑folder and per‑file selection; include exactly what the user selected (no deduping).
- Ordering: by path (lexicographic) or by file mtime.
- Combined markdown assembly:
  - Do not inject new markdown headings. Use HTML comments to delimit sections so we don’t change document structure:
    - Section start: `<!--- section-begin: <project_relative_path> --->`
    - Section end: `<!--- section-end --->`
  - Include a short source reference line within comments only; visible markdown content remains faithful to inputs.
  - Preserve per‑file page markers (see Conversion Updates) to enable later deep links.
- Prompt execution (single pass): reuse existing bulk-analysis pipeline utilities (`load_prompts`, `render_system_prompt`, `render_user_prompt`, `should_chunk`, `generate_chunks`, `combine_chunk_summaries`).
- Reasoning toggle: if `use_reasoning` and provider/model indicates a thinking model, set `temperature=1.0`, else `0.1`.
- Outputs:
  - Write combined markdown to `reduce/combined_YYYYMMDD-HHMM.md`.
  - Write `reduce/combined_YYYYMMDD-HHMM.manifest.json` with inputs + mtimes, prompt paths + hashes, provider/model, temperature, and timestamp.
- Signals and cancellation: mirror existing worker patterns (progress is aggregate text updates rather than per-file counts).

## Staleness & Metrics

- FileTracker remains unchanged; it continues to count Per‑document outputs only.
- Combined status per operation (computed on demand):
  - Identify latest combined artifact and manifest in `bulk_analysis/<slug>/reduce/`.
  - Re-resolve current selection set:
    - If any selected file’s current mtime > recorded mtime in manifest → Stale
    - If selection set differs from manifest’s input list (added/removed) → Stale
    - Missing selected files → Stale
  - Expose `latest_reduce_at`, `latest_reduce_path`, and `stale: bool` to the workspace row without affecting the Per‑document X/Y coverage.

## Conversion Updates (Source Metadata & Page Markers)

Files: `src/app/workers/conversion_worker.py`, `src/core/pdf_utils.py`

- Prepend YAML front‑matter to produced `.md` for PDFs and DOCX:
  - `source_path`: absolute path
  - `source_rel`: project‑relative path
  - `source_format`: `pdf|docx|md|txt`
  - `source_mtime`: ISO timestamp
  - `page_count`: for PDFs (via PyMuPDF)
- Replace current page markers with HTML comments (project‑relative):
  - Exactly: `<!--- <source_rel>.pdf#page=N --->`
- Update both local and Azure DI markdown rendering paths to emit the new comment format.

## Provider Behavior (Reasoning)

- Defaults: `temperature=0.1`, chunking heuristics as in Per‑document.
- “Use reasoning” checkbox:
  - If enabled and provider/model indicates a thinking model (e.g., Anthropic “thinking” variants), set `temperature=1.0`.
  - Else, remain at `0.1`.
  - Implement as a small helper for easy refinement.

## Testing Plan

- Selection resolution:
  - Combined inputs from converted + map outputs; folder+file picks; mixed sources.
  - Ordering by path and by mtime.
- Worker behavior:
  - Creates timestamped combined file + manifest; cancellation flow; logs.
  - Reasoning toggle sets temperature appropriately.
- Staleness detection:
  - Fresh run → not stale; touch a selected input → stale; adjust selection set → stale; remove selected file → stale.
- UI:
  - Dialog fields persist; token preview renders; action buttons wired.
  - Workspace row chips (Type, Stale), status texts, Open Latest.
- Regression:
  - Existing Per‑document flows and tests unchanged.

## Implementation Order

1) Data model: add fields + version bump; surface reusable “invalid/unsupported format” error on mismatch.
2) Group Dialog: Combined selectors/trees + options + reasoning checkbox + token preview.
3) BulkReduceWorker: input resolution, assembly with section comments, prompt call, outputs + manifest.
4) Staleness computation: compute and display status + “Stale” chip; add Open Latest.
5) Conversion updates: YAML front‑matter + HTML comment page markers (project‑relative); adapt local/Azure paths.
6) Tests: unit + UI integration for the above.

## Status Update — 2025-09-29

Completed
- Data model
  - Added `operation` (per_document | combined) and all Combined selection/options fields to `BulkAnalysisGroup`.
  - Bumped `SUMMARY_GROUP_VERSION` to 2; invalid/unsupported configs are skipped with a clear log message.
- UI
  - Group Dialog: operation selector; Converted-docs tree; Per‑document outputs tree; Combined options (order, output template); “Use reasoning” checkbox.
  - Workspace: Coverage shows “Combined – Inputs: N”; actions include “Run Combined” and “Open Latest”; status shows “Stale” when applicable.
- Workers
  - Implemented `BulkReduceWorker` to assemble Combined inputs (comment‑delimited sections), run a single prompt with chunking, and write timestamped outputs + manifest.
  - Standardised Markdown metadata across conversion, highlight, bulk-analysis, and report outputs using the shared front matter helper (python-frontmatter).
- Metrics & Staleness
  - Extended workspace metrics to compute Combined input count, latest combined artifact, and `stale` flag without altering FileTracker map coverage.
- Conversion pipeline
  - Inject standardised front matter using the shared markdown helper: `project_path`, `generator`, structured `sources` (absolute path, relative path, checksum, role), conversion-specific extras (`source_format`, `source_mtime`, `pages_detected`, `pages_pdf`, `converter`).
  - Azure DI: parse `<!-- PageBreak -->` and insert absolute page markers `<!--- <project_rel>#page=N --->`.
  - Local: convert legacy “--- Page N ---” to absolute comment markers.
  - Large PDFs: added chunked Azure DI (1000 pages with 5‑page overlap) with robust merge and PageBreak interleaving.
  - Log a warning if `pages_detected != pages_pdf`.
- Tests
  - Added unit tests to verify Azure PageBreak → marker conversion and page mismatch logging. Existing bulk‑analysis UI tests still pass.

Deviations from original plan (intentional)
- “Type” column in table: surfaced Combined via Coverage string instead of a new column to keep layout stable; can revisit if needed.
- JSON output for chunked Azure path is omitted; only Markdown is required downstream. We can emit a lightweight manifest if needed later.

## Suggested Next Steps

High‑value next
- Add UI “Stale” chip with tooltip listing the first few changed inputs (path + last modified) for Combined operations.
- Add UI affordance to open the latest Combined manifest for quick diagnostics.
- Expand tests:
  - Verify YAML includes both `pages_detected` and `pages_pdf` and logs mismatch warnings end‑to‑end (tiny PDF + synthesized PageBreaks).
  - Add Combined UI flow tests: create combined operation, run, ensure output exists, status transitions, and “Open Latest.”
  - Add worker tests for Combined manifest content and staleness resolution after touching inputs.

Refinements
- Per‑document outputs tree: add folder‑level tri‑state nodes (like Converted tree) for bulk selection; currently file‑only.
- Provide a clickable link to the latest Combined artifact path directly in the table status tooltip.
- Reasoning toggle: expand provider/model detection beyond a simple “thinking” substring when docs are available (keep checkbox UX).
- Chunked Azure DI: add a minimal runtime capability check log (“using pages param” vs “pre‑split fallback”) and simple telemetry counters.

Future
- Optional: small JSON manifest alongside Combined output noting chunk ranges and merge stats (for large documents triage).
- Optional: header‑aware merging if Azure boundaries need semantic continuity (deferred until we see quality issues).

## Risks & Mitigations

- Large combined inputs may exceed context window:
  - Mitigate via chunking + combine pass (existing utilities), and surface a friendly UI message if truncated.
- Mixed inputs (converted + map outputs) may duplicate content:
  - Respect “exactly as selected” (per requirements); document best practices in a tooltip.
- Legacy operations:
  - Fail fast with reusable “invalid/unsupported format” error; instruct users to recreate.

## Out of Scope

- Database for artifact/index tracking (file‑based only for now).
- Symlinks/aliases for “latest” artifacts (explicitly not desired).
- Renaming internal modules away from “summary” (to be revisited after stabilization).

## Notes

- Paths in HTML comments and manifest are project‑relative to disambiguate similarly named files.
- All time comparisons are second‑granularity (adequate for these operations).
