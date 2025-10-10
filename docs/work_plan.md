# Llestrade - Consolidated Work Plan (formerly Forensic Report Drafter)

## Priority 0: Dashboard UI Refactoring (IMMEDIATE)

Transform the current wizard-style UI into a dashboard-based workflow that supports long-running operations, multiple bulk analysis groups, and intelligent file existence checking for resume functionality.

### Design Principles

- **Keep it simple**: Use built-in Qt/PySide6 functionality where possible
- **File-based state**: All state visible as files/folders for debugging
- **Breaking changes OK**: This is pre-release software, no backward compatibility needed
- **No overengineering**: Simple solutions preferred
- **Progressive enhancement**: Build on existing working code

### Phase 1: Core Infrastructure & Dashboard

#### Pre-Flight Foundation Audit

- [x] Identify unused/abandoned modules and move them into `src/archive/`
- [x] Remove obsolete wiring from `main_new.py` and stage imports that will be replaced
- [x] Capture retained legacy behavior in notes/TODOs before deletion *(see "Legacy UI Reference" summary below)*

#### Step 0 - Decommission Wizard Flow

- [x] Refactor stage navigation to support the dashboard model
  - [x] Retire the linear wizard assumptions in `StageManager`
  - [x] Remove unused stages (e.g., `refine`) and decouple welcome from project routing
  - [x] Introduce a `WorkspaceController` (or equivalent) that can manage tabbed dashboards
- [x] Redesign `main_new.py` to host the dashboard shell (sidebar + tabbed workspace)
  - [x] Preserve welcome-screen entry, but swap the stacked wizard for a minimal tab scaffold (welcome + empty workspace)
  - [x] Add temporary feature flag handling so current flows continue to launch
- [x] Stub out `src/new/stages/project_workspace.py` with placeholder tabs to unblock downstream work

#### Legacy UI Reference (Captured 2025-03-11)

- StageManager’s linear gating is intentionally replaced by a scan-driven workflow after project setup
- Project setup keeps evaluator/output guardrails, auto-sanitizes folder name (spaces → dashes), and informs users about folder creation
- Source management pivots to folder-level include/exclude (tree checkboxes) with relative paths; root-level files trigger warnings instead of silent skips
- Conversion helpers remain responsible for PDFs/complex formats; simple text/markdown bypass conversion and duplicates are prevented via in-memory tracking
- Bulk analysis reuses legacy chunking/logging patterns but surface streamlined logs; reports move to a placeholder tab until redesigned

#### Step 1 - Core Infrastructure

- [x] Create FileTracker class (`src/app/core/file_tracker.py`)
  - [x] Implement file existence checking with folder structure preservation
  - [x] Add project statistics calculation
  - [x] Write pytest tests for critical methods
  - [x] Limit initial scope to counts, last-run timestamps, and deterministic reconciliation
- [x] Update ProjectManager (`src/app/core/project_manager.py`)
  - [x] Persist new project layout (create `<parent>/<project-name>/` folder, sanitize name, keep readable)
  - [x] Store source folder configuration as relative paths with include/exclude tree state
  - [x] Record selected conversion helper and per-project conversion preferences
  - [x] Expose lightweight dashboard state (last opened tab, pending job descriptors) instead of `WorkflowState`
  - [x] Surface FileTracker statistics and bulk-analysis metadata for the workspace views
- [x] Add AWS Bedrock support to the Anthropic provider stack (dual cloud/Bedrock options, shared factory wiring)
- [x] Create bulk analysis group system (`src/app/core/bulk_analysis_groups.py`)
- [x] Implement BulkAnalysisGroup dataclass
  - [x] Add config.json serialization for groups
  - [x] Create folder structure management
  - [x] Base mocked responses on fixtures captured from real provider calls
- [x] Extract and consolidate worker threads (implemented under `src/app/workers/`)
  - [x] Move processing/summarization into workers (`ConversionWorker`, `HighlightWorker`, `BulkAnalysisWorker`)
  - [x] Create shared base class for workers (`DashboardWorker`)
  - [x] Set up QThreadPool for parallel operations (max 3 workers) with `WorkerCoordinator`

#### Step 2 - Dashboard Enhancement & Project Setup

- [x] Wire `main_new.py` dashboard shell into welcome + workspace views
  - [ ] Enhance Welcome Stage (`src/app/ui/stages/welcome_stage.py`)
    - [x] Add FileTracker stats to project cards (X/Y converted, X/Y summarized)
    - [x] Implement project deletion
    - [x] Add "Open Folder" action
    - [ ] Test with existing projects (breaking changes OK)
- [x] Simplify project creation
  - [x] Single-screen setup (name, source folder, output folder)
  - [x] Create `<selected folder>/<project-name>/` (spaces → dashes) and call out folder creation to the user
  - [x] Remove multi-stage wizard flow; initial import deferred to Documents tab
  - [x] Capture conversion helper selection in the setup dialog

#### Step 3 - Project Workspace

- [x] Create tabbed workspace (`src/app/ui/stages/project_workspace.py`)
  - [x] Replace linear stages with QTabWidget
  - [x] Create Documents and Bulk Analysis tabs *(progress feed handled within Bulk Analysis; separate tab descoped)*
  - [x] Provide "home" navigation to return to the welcome screen
  - [ ] Default to Bulk Analysis tab on open once setup is complete
- [x] Documents Tab
  - [x] Source folder picker with tree view checkboxes (folder-level only, default to all selected)
  - [x] Store selections as relative paths and surface manual "Re-scan for new files" action with last-scan timestamp
  - [x] Warn when files exist in the source root but no folders are selected (conversion requires subfolders)
  - [x] Display `X of Y` counts from FileTracker for files converted vs. pending (including converted_documents)
  - [x] Keep batch operations non-blocking and track in-flight conversions to avoid duplicate submissions
- [x] Bulk Analysis Tab
  - [x] List bulk analysis groups with `X of Y` document coverage using FileTracker data
  - [x] Reuse folder tree with greyed-out (tooltip: "Enable in Documents → Sources") entries for folders not selected for conversion *(simplified to converted_documents tree only)*
  - [x] Offer system/user prompt file pickers per group (stored as relative paths)
  - [x] Provide run/stop controls that enqueue work on the shared worker pool and surface concise logs *(uses real workers with cancellation)*
  - [x] Split run actions into "Run Pending" and "Run All" with explicit confirmation for force re-runs
  - [x] Mirror the split controls for combined operations (standard vs. force) with manifest-based skipping
  - [x] Add an inline activity log so bulk-analysis messages remain visible during long runs
- [ ] Progress Tab *(descoped; future activity feed will live in Bulk Analysis tab)*

#### Step 4 - Automated Conversion & Bulk Analysis

- [x] Extend project metadata to capture project root, source-relative folder selections, and conversion helper choice
- [x] Update project creation to gather source folder and output folder (warning about root-level files); helper selection stored in project metadata
- [x] On project open (and when "Re-scan" is pressed), detect new/changed files and prompt for conversion + bulk analysis
- [x] Implement conversion helper registry that handles PDFs/complex formats while skipping simple markdown/plain-text files *(default helper in place; additional helpers TBD)*
- [x] Track in-flight conversions in memory to avoid duplicate submissions during long runs; rely on file existence post-run
- [ ] After conversion, trigger bulk analysis for eligible groups (folders selected in both tabs) using existing chunking for large files
- [x] Provide clear UI to accept/decline runs and surface log output per operation

### Phase 2: Bulk Analysis & Integration

#### Step 4 - Bulk Analysis Groups Implementation

- [x] Create Bulk Analysis tab scaffolding
  - [x] List groups with status chips (`Converted X / Y`, `Bulk Analysis X / Y`)
  - [x] "Create Group" launches modal; inline edit deferred for later polish
  - [x] Delete action triggers confirmation noting all generated outputs will be removed
  - [x] Run button enqueues jobs and streams concise log output
- [ ] Group dialog (`src/app/ui/dialogs/summary_group_dialog.py`)
  - [ ] Group name input with duplicate-name warning
  - [x] Folder tree mirrors Documents tab selections (checkboxes only at folder level, greyed-out nodes blocked with tooltip)
  - [x] System prompt + user prompt file pickers (persisted as relative paths)
  - [x] Model/provider selection leveraging existing configuration helpers
  - [x] Persist include/exclude choices and prompt paths into group `config.json`

#### Step 5 - Integration & Testing

- [ ] Connect bulk analysis workflow to groups
  - [x] Modify worker threads to accept group metadata and prompt file paths
  - [x] Update output structure to use `bulk_analysis/<group_name>/` directories
  - [x] Add skip logic for existing analyses (based on timestamp + prompt hash)
  - [ ] Test with multiple groups and overlapping folders
- [x] Consolidate worker infrastructure under `src/app/workers/`
  - [x] Move document processing/summarization threads into shared base classes
  - [x] Register workers with a `QThreadPool` (max 3) and add cancellation hooks
  - [ ] Emit consistent debug logging (job id + status transitions) for traceability
  - [x] Add unit tests for worker lifecycle and error propagation
- [x] Normalize highlight color outputs
  - [x] Write color aggregates to `highlights/colors` instead of `highlights/documents/colors`
  - [x] Migrate legacy color files on extraction and clean up obsolete folders
  - [x] Add regression tests covering the migration and color aggregate writes
- [x] Standardize Markdown metadata
  - [x] Introduce shared front matter helper (`src/common/markdown/frontmatter_utils.py`) backed by python-frontmatter
  - [x] Apply helper to conversion, highlight, bulk analysis, and report workers with project/sources/prompt metadata
- [ ] Phoenix integration for LLM calls
  - [ ] Keep existing observability.py setup
  - [ ] Add bulk analysis group context to traces
  - [ ] Use fixture export for test mocks
- [ ] Business logic testing with pytest
  - [x] Test FileTracker functionality
  - [x] Test bulk analysis group CRUD operations
  - [ ] Test document conversion with folder preservation
  - [ ] Reuse existing tests where applicable
  - [x] Stand up `tests/new_ui/` for dashboard logic (FileTracker, bulk analysis, project lifecycle)
  - [ ] Add mocked smoke tests driven by recorded fixtures (no live API calls)
  - [ ] Maintain a separate, optional live suite for provider calls using dedicated credentials
  - [ ] Audit codebase for "summary" terminology and update to "bulk analysis" where appropriate

#### Step 6 - Polish & Cleanup

- [ ] Settings & UI Polish
  - [ ] Add minimize on close setting
  - [ ] Test resume after restart functionality
  - [ ] Verify error handling (panel at bottom)
  - [ ] Cost tracking stub (implementation deferred)
- [ ] Code cleanup
  - [ ] Archive legacy UI to `src/archive/legacy/`
  - [ ] Update `main.py` to drop legacy entry points
  - [ ] Clean settings/tests that reference legacy-only classes
  - [ ] Document archival status + reference path in README

### Folder Structure After Refactoring

```
project_dir/
├── project.frpd                # Project metadata (relative source paths, helper, UI state)
├── sources.json                # Serialized tree of included folders (+ warnings for root files)
├── converted_documents/        # Markdown outputs mirroring selected folder structure
│   ├── medical_records/
│   │   ├── report1.md
│   │   └── report2.md
│   └── legal_docs/
│       └── case_summary.md
├── highlights/                 # Highlight outputs mirroring converted_documents (PDF-only)
│   ├── medical_records/
│   │   ├── report1.highlights.md
│   │   └── report2.highlights.md
│   └── legal_docs/
│       └── case_summary.highlights.md
├── bulk_analysis/
│   ├── clinical_records/
│   │   ├── config.json         # Prompts, model, folder subset
│   │   └── outputs/
│   │       ├── medical_records/
│   │       │   ├── report1.md
│   │       │   └── report2.md
│   │       └── legal_docs/
│   │           └── case_summary.md
│   └── legal_documents/
│       ├── config.json
│       └── outputs/
│           └── legal_docs/
│               └── case_summary.md
└── backups/
    └── 2025-01-01T120000Z/    # Snapshot copies created by the app
```

> Original source files remain in their external locations; the project stores only relative references and derived outputs. Highlight files exist only for PDFs and mirror the converted_documents tree. When no highlights are found, a placeholder `.highlights.md` is written with a timestamped note.

### Success Criteria for Priority 0

- [x] Users can create multiple bulk analysis groups (shared converted docs)
- [x] Files can belong to multiple groups without duplication
- [ ] Scan-on-open + manual re-scan convert new files with user confirmation
- [x] Dashboard shows accurate `X of Y` conversion and bulk-analysis counts with root-level warnings where needed
- [x] Converted/bulk output mirrors folder structure via relative paths
- [x] Worker operations remain non-blocking with safe shutdown
- [x] Breaking changes implemented cleanly
- [x] Business logic tests passing
- [ ] Phoenix tracing working for LLM calls with group context

- [x] Documentation: add `highlights/` to the folder structure diagram; clarify that highlight counts use PDFs only.
- [ ] Highlights UX: add "Re-extract highlights" action and surface reasons when a file remains pending.

Note: Highlights denominator uses PDFs only (pending/highlights reflect PDF-eligible files).

## Current Project Status

### Application Architecture

- **Technology**: PySide6 desktop application targeting macOS, Windows, and Linux
- **UI Transition**:
  - **Legacy UI**: Fully functional, to be archived after dashboard implementation
  - **New UI**: Moving from wizard-style to dashboard + tabbed workspace

### Testing Status

- **487 test cases** for legacy UI
- **NO tests** for new UI components (17 files untested)
- **No coverage reporting** currently configured

### Codebase Health

- **Minimal langchain usage** (only MarkdownHeaderTextSplitter) ✓
- **Standard file operations** (pathlib, shutil) ✓
- **Large files needing refactoring**:
  - `analysis_tab.py` (1501 lines)
  - `record_review_tab.py` (1382 lines)
  - `llm_summary_thread.py` (847 lines)

## Phase 1: Deep Code Analysis & Cleanup (Week 1-2)

### 1.1 Add Development Dependencies

```toml
[dependency-groups]
dev = [
    "pytest>=8.4.1",
    "pytest-cov>=5.0.0",      # Coverage reporting
    "pytest-qt>=4.4.0",        # Qt testing support
    "langfuse>=2.0.0",         # LLM observability
    "rich>=13.0.0",            # Better console output
]
```

### 1.2 Dead Code Elimination

- [ ] Remove FastAPI/Electron references from documentation
- [ ] Delete commented-out code blocks
- [ ] Remove unused imports and functions
- [ ] Clean up abandoned architectural experiments
- [ ] Remove duplicate implementations

### 1.3 File Organization & Refactoring

**Files to Split (>800 lines)**:

- [ ] `src/legacy/ui/analysis_tab.py` → Split into:
  - `analysis_tab_ui.py` (UI components)
  - `analysis_tab_logic.py` (business logic)
  - `analysis_tab_handlers.py` (event handlers)
- [ ] `src/legacy/ui/record_review_tab.py` → Split into:
  - `record_review_ui.py`
  - `record_review_logic.py`
  - `record_review_handlers.py`

**Project Structure Review**:

- [ ] Evaluate consolidating `src/legacy/` and `src/new/` after cleanup
- [ ] Review `src/common/` for proper shared components
- [ ] Identify redundant modules for consolidation

### 1.4 Leverage PySide6 Components Better

**Components to Adopt**:

- [ ] Migrate from custom JSON settings to `QSettings`
- [ ] Replace individual `QThread` usage with `QThreadPool` where appropriate
- [ ] Implement `QUndoStack` for editors (refinement stage)
- [ ] Use `QProgressDialog` consistently instead of custom progress widgets
- [ ] Add `QFileSystemWatcher` for file monitoring instead of polling

### 1.5 Add LLM Observability

Moved to "Proposed Additions (For Review Later)" to align with Phoenix/OpenInference instrumentation direction.

## Phase 2: Business Logic Testing (Week 2-3)

### 2.1 Core Component Tests (Non-GUI Focus)

**LLM Integration Layer**:

- [ ] Test provider abstraction (`src/common/llm/`)
- [ ] Test chunking strategies
- [ ] Test token counting accuracy
- [ ] Test error handling and retries
- [ ] Test cost calculation

**Document Processing Pipeline**:

- [ ] Test PDF conversion logic
- [ ] Test Word document handling
- [ ] Test markdown generation
- [ ] Test file validation
- [ ] Test batch processing

**Project Management**:

- [ ] Test ProjectManager CRUD operations
- [ ] Test auto-save functionality
- [ ] Test backup creation
- [ ] Test state persistence
- [ ] Test migration between stages

### 2.2 Worker Thread Tests

**Thread Safety**:

- [ ] Verify signal/slot communication
- [ ] Test thread cleanup on cancellation
- [ ] Test resource management
- [ ] Test error propagation
- [ ] Test concurrent operations

### 2.3 Security & Data Flow

**API Key Management**:

- [ ] Test SecureSettings encryption
- [ ] Test keyring integration
- [ ] Test fallback mechanisms
- [ ] Test key rotation

## Phase 3: Smart Refactoring (Week 3-4)

### 3.1 Replace Custom Code with Libraries

**PySide6 Optimizations**:

- [ ] Replace custom settings with `QSettings`
- [ ] Use `QStateMachine` for stage management
- [ ] Leverage `QCompleter` for form auto-completion
- [ ] Use built-in validators (`QRegularExpressionValidator`, etc.)

**Potential Additions** (evaluate carefully):

- [ ] Consider `watchdog` for file system monitoring
- [ ] Evaluate `structlog` for structured logging
- [ ] Consider `pydantic` for data validation

### 3.2 Code Consolidation

**Merge Similar Functionality**:

- [ ] Consolidate progress dialog implementations
- [ ] Unify error handling patterns
- [ ] Standardize worker thread base class
- [ ] Merge duplicate file utilities

**Extract Common Patterns**:

- [ ] Create base classes for common UI patterns
- [ ] Extract shared validation logic
- [ ] Centralize configuration management

## Phase 4: REMOVED - Replaced by Dashboard UI Refactoring

_The wizard-style UI with linear stages has been replaced by the dashboard approach in Priority 0._

## Phase 5: Stabilization (Week 5-6)

### 5.1 Performance Optimization

- [ ] Memory profiling (target: <200MB)
- [ ] Optimize stage transitions (<1 second)
- [ ] Improve LLM response streaming
- [ ] Reduce startup time

### 5.2 Cross-Platform Testing

- [ ] Test on macOS (primary)
- [ ] Test on Windows
- [ ] Test on Linux
- [ ] Fix platform-specific issues

### 5.3 Documentation

- [ ] Update README.md with accurate status
- [ ] Create user guide for new UI
- [ ] Document API for developers
- [ ] Add inline code documentation

## Distribution & Packaging

- [x] Centralize resource lookup for frozen bundles (`app_resource_root`, prompt/resource helpers)
- [x] Add PyInstaller spec for the dashboard (`scripts/build_dashboard.spec`)
- [x] Provide per-platform build wrappers (`scripts/build_macos.sh`, `scripts/build_linux.sh`, `scripts/build_windows.ps1`)
- [ ] Validate macOS bundle end-to-end (launch, highlights, bulk analysis)
- [ ] Produce and validate Windows bundle
- [ ] Produce and validate Linux bundle
- [ ] Add packaging jobs to CI with artifact uploads
- [ ] Plan code signing / notarization strategy per platform

## Success Metrics

### Code Quality

- [ ] Test coverage >80% for business logic
- [ ] No files >800 lines
- [ ] All functions <50 lines
- [ ] Cyclomatic complexity <10

### Performance

- [ ] Memory usage <200MB normal operation
- [ ] Stage transitions <1 second
- [ ] No memory leaks over 8-hour session
- [ ] Startup time <3 seconds

### Maintainability

- [ ] Clear separation of concerns
- [ ] Consistent patterns throughout
- [ ] Comprehensive test suite
- [ ] Well-documented code

## Future Considerations (Deferred)

### Enhanced Features

- Cost tracking with comprehensive reporting
- Template gallery system
- Model auto-discovery
- Advanced progress indicators with pause/resume
- Session management and recovery

### Distribution

- Package as standalone executables
- Auto-update system
- Code signing for trusted distribution
- Professional installers (MSI, DMG, AppImage)

### Enterprise Features

- Multi-user support
- LDAP/Active Directory integration
- Audit logging
- HIPAA compliance features
- Cloud deployment options

### AI Enhancements

- Custom fine-tuned models
- Local LLM support (Ollama)
- Intelligent document classification
- Automated quality checks

### Collaboration

- Real-time collaboration
- Comment and annotation system
- Change tracking
- Approval workflows

## Immediate Next Steps

- [x] Surface conversion helper selection in the new project dialog and plumb helper-specific options
- [x] Extend Documents tab counts/logging to show converted vs. pending documents after each run
- [ ] Add automatic hand-off from conversion completion to bulk-analysis job scheduling where configured
- [x] Build out the Bulk Analysis tab actions (folder gating, prompt pickers, run + delete flows)
- [x] Enhance Welcome Stage with per-project stats/open-folder action; UI polish for legacy cleanup remains
- [x] Wire project placeholders end-to-end: editor, preview highlighting, bulk/report validation, and worker substitution

## Proposed Additions (For Review Later)

- Summary group migration helper: upgrade `bulk_analysis/*/config.json` from version 1 to 2 with validation.
- Documentation: add `highlights/` to the folder structure diagram; clarify that highlight counts use PDFs only.
- Auto hand-off: optionally kick off bulk analysis after conversions complete when configured per group.
- Skip logic: avoid re-processing existing bulk outputs using timestamp + prompt hash.
- Observability: instrument LLM calls with Phoenix/OpenInference and attach group context; update dev deps snippet accordingly.
- Worker traceability: add consistent job identifiers in logs and progress signals.
- Highlights UX: add "Re-extract highlights" action and surface reasons when a file remains pending.
- Welcome polish: finish remaining legacy cleanup messaging and small UI tweaks.

## Notes

- Breaking changes are acceptable (no backward compatibility needed)
- Focus on simple, reliable solutions over complex engineering
- Preserve folder structure throughout document pipeline
- Use QThreadPool for parallel operations (max 3 workers)
- Test business logic with pytest, defer GUI testing
- Phoenix for LLM observability only
- Archive old code after dashboard implementation
