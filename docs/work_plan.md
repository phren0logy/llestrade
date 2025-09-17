# Forensic Report Drafter - Consolidated Work Plan

## Priority 0: Dashboard UI Refactoring (IMMEDIATE)

Transform the current wizard-style UI into a dashboard-based workflow that supports long-running operations, multiple summary groups, and intelligent file existence checking for resume functionality.

### Design Principles

- **Keep it simple**: Use built-in Qt/PySide6 functionality where possible
- **File-based state**: All state visible as files/folders for debugging
- **Breaking changes OK**: This is pre-release software, no backward compatibility needed
- **No overengineering**: Simple solutions preferred
- **Progressive enhancement**: Build on existing working code

### Phase 1: Core Infrastructure & Dashboard

#### Pre-Flight Foundation Audit

- [ ] Identify unused/abandoned modules and move them into `src/archive/`
- [ ] Remove obsolete wiring from `main_new.py` and stage imports that will be replaced
- [ ] Capture retained legacy behavior in notes/TODOs before deletion

#### Step 0 - Decommission Wizard Flow

- [ ] Refactor stage navigation to support the dashboard model
  - [ ] Retire the linear wizard assumptions in `StageManager`
  - [ ] Remove unused stages (e.g., `refine`) and decouple welcome from project routing
  - [ ] Introduce a `WorkspaceController` (or equivalent) that can manage tabbed dashboards
- [ ] Redesign `main_new.py` to host the dashboard shell (sidebar + tabbed workspace)
  - [ ] Preserve welcome-screen entry, but swap the stacked wizard for a minimal tab scaffold (welcome + empty workspace)
  - [ ] Add temporary feature flag handling so current flows continue to launch
- [ ] Stub out `src/new/stages/project_workspace.py` with placeholder tabs to unblock downstream work

#### Step 1 - Core Infrastructure

- [ ] Create FileTracker class (`src/new/core/file_tracker.py`)
  - [ ] Implement file existence checking with folder structure preservation
  - [ ] Add project statistics calculation
  - [ ] Write pytest tests for critical methods
  - [ ] Limit initial scope to counts, last-run timestamps, and deterministic reconciliation
- [ ] Update ProjectManager (`src/new/core/project_manager.py`)
  - [ ] Bump project format to v2 and emit migration metadata
  - [ ] Rename on-disk folders to `imported_documents/`, `processed_documents/`, and `summaries/`
  - [ ] Add summary-group aware schema (groups array + config pointers)
  - [ ] Replace `WorkflowState` with dashboard/tab state primitives
  - [ ] Provide upgrade path or conversion script for v1 projects
- [ ] Create SummaryGroup system (`src/new/core/summary_groups.py`)
  - [ ] Implement SummaryGroup dataclass
  - [ ] Add config.json serialization for groups
  - [ ] Create folder structure management
  - [ ] Base mocked responses on fixtures captured from real provider calls
- [ ] Extract and consolidate worker threads
  - [ ] Move DocumentProcessorThread to `src/new/workers/`
  - [ ] Create shared base class for workers
  - [ ] Set up QThreadPool for parallel operations (max 3 workers)

#### Step 2 - Dashboard Enhancement & Project Setup

- [ ] Wire `main_new.py` dashboard shell into welcome + workspace views
  - [ ] Enhance Welcome Stage (`src/new/stages/welcome_stage.py`)
    - [ ] Add FileTracker stats to project cards (X/Y converted, X/Y summarized)
    - [ ] Implement project deletion
    - [ ] Add "Open Folder" action
    - [ ] Test with existing projects (breaking changes OK)
- [ ] Simplify project creation
  - [ ] Single-screen setup (name, description, output folder)
  - [ ] Remove multi-stage wizard flow
  - [ ] Initial file import optional (can add later in workspace)

#### Step 3 - Project Workspace

- [ ] Create tabbed workspace (`src/new/stages/project_workspace.py`)
  - [ ] Replace linear stages with QTabWidget
  - [ ] Create Documents, Summary Groups, Progress tabs
  - [ ] Default to Summary Groups tab on open
- [ ] Documents Tab
  - [ ] Import files/folders with folder structure preservation
  - [ ] Smart auto-conversion (skip existing markdown files)
  - [ ] Show numeric status (12/45 converted) not progress bars
  - [ ] Non-blocking batch operations
- [ ] Progress Tab
  - [ ] Combined log from all operations
  - [ ] Simple cancel button for current operation
  - [ ] Error panel at bottom (non-blocking)

### Phase 2: Summary Groups & Integration

#### Step 4 - Summary Groups Implementation

- [ ] Create Summary Groups tab
  - [ ] List of summary groups with stats
  - [ ] "Create Group" button → opens dialog
  - [ ] Edit/Delete actions per group
  - [ ] "Summarize" button per group
- [ ] Create group dialog (`src/new/dialogs/summary_group_dialog.py`)
  - [ ] Group name input
  - [ ] Tree view with checkboxes (preserve folder structure)
  - [ ] "Select all in folder" functionality
  - [ ] Prompt template selection (scan prompt_templates/)
  - [ ] LLM model selection per group
  - [ ] No overlap validation (files can be in multiple groups)

#### Step 5 - Integration & Testing

- [ ] Connect summarization to groups
  - [ ] Modify worker threads to accept group parameter
  - [ ] Update file paths to use summaries/[group_name]/ folders
  - [ ] Add skip logic for existing summaries
  - [ ] Test with multiple groups
- [ ] Consolidate worker infrastructure under `src/new/workers/`
  - [ ] Move document processing/summarization threads into shared base classes
  - [ ] Register workers with a `QThreadPool` (max 3) and add cancellation hooks
  - [ ] Emit consistent debug logging (job id + status transitions) for traceability
  - [ ] Add unit tests for worker lifecycle and error propagation
- [ ] Phoenix integration for LLM calls
  - [ ] Keep existing observability.py setup
  - [ ] Add summary group context to traces
  - [ ] Use fixture export for test mocks
- [ ] Business logic testing with pytest
  - [ ] Test FileTracker functionality
  - [ ] Test summary group CRUD operations
  - [ ] Test document conversion with folder preservation
  - [ ] Reuse existing tests where applicable
  - [ ] Stand up `tests/new_ui/` for dashboard logic (FileTracker, summary groups, project migration)
  - [ ] Add mocked smoke tests driven by recorded fixtures (no live API calls)
  - [ ] Maintain a separate, optional live suite for provider calls using dedicated credentials

#### Step 6 - Polish & Cleanup

- [ ] Settings & UI Polish
  - [ ] Add minimize on close setting
  - [ ] Test resume after restart functionality
  - [ ] Verify error handling (panel at bottom)
  - [ ] Cost tracking stub (implementation deferred)
- [ ] Code cleanup
  - [ ] Archive old UI files to `src/archive/`
  - [ ] Delete unused stage files
  - [ ] Remove wizard/linear flow code
  - [ ] Update main.py and main_new.py
  - [ ] Freeze legacy maintenance once dashboard feature parity is confirmed

### Folder Structure After Refactoring

```
project_dir/
├── project.frpd (v2 format with summary groups)
├── imported_documents/  # Original files with preserved structure
│   ├── medical_records/
│   │   ├── report1.pdf
│   │   └── report2.docx
│   └── legal_docs/
│       └── case_summary.pdf
├── processed_documents/ # Markdown files with same structure
│   ├── medical_records/
│   │   ├── report1.md
│   │   └── report2.md
│   └── legal_docs/
│       └── case_summary.md
└── summaries/
    ├── clinical_records/  # User-named summary group
    │   ├── config.json
    │   ├── medical_records/
    │   │   ├── report1_summary.md
    │   │   └── report2_summary.md
    │   └── legal_docs/
    │       └── case_summary_summary.md
    └── legal_documents/  # Another summary group
        ├── config.json
        └── legal_docs/
            └── case_summary_summary.md
```

### Success Criteria for Priority 0

- [ ] Users can create multiple summary groups
- [ ] Files can exist in multiple groups (no overlap restriction)
- [ ] App skips already processed/summarized files
- [ ] Dashboard shows accurate counts
- [ ] Folder structure preserved throughout pipeline
- [ ] All operations are non-blocking
- [ ] Breaking changes implemented cleanly
- [ ] Business logic tests passing
- [ ] Phoenix tracing working for LLM calls

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

**Langfuse Integration (Dev-only)**:

```python
# Example wrapper for LLM calls
if settings.DEVELOPMENT_MODE:
    from langfuse import Langfuse
    langfuse = Langfuse()

    @langfuse.observe()
    def generate_summary(text, model):
        # Track costs, latency, token usage
        pass
```

Benefits:

- Track all LLM calls and costs
- Debug prompt effectiveness
- Monitor token usage patterns
- Analyze performance bottlenecks

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

1. Begin Priority 0 Dashboard UI Refactoring
2. Create FileTracker and SummaryGroup classes
3. Set up QThreadPool for parallel operations
4. Transform wizard UI to dashboard + tabs
5. Archive/delete old UI code when complete

## Notes

- Breaking changes are acceptable (no backward compatibility needed)
- Focus on simple, reliable solutions over complex engineering
- Preserve folder structure throughout document pipeline
- Use QThreadPool for parallel operations (max 3 workers)
- Test business logic with pytest, defer GUI testing
- Phoenix for LLM observability only
- Archive old code after dashboard implementation
