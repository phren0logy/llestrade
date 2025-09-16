# Forensic Report Drafter - Consolidated Work Plan

## Priority 0: Systematic Testing & New UI Completion (IMMEDIATE)

### 0.1 Complete Refinement Stage (Day 1)
- [x] Replace Langfuse with Arize Phoenix for observability
- [ ] Create minimal `src/new/stages/refinement_stage.py`
- [ ] Implement basic text editor with save functionality  
- [ ] Reuse RefinementThread from legacy UI
- [ ] Register in stage manager and main_new.py

### 0.2 Systematic Testing Infrastructure (Days 2-3)
- [ ] Create `tests/test_new/` directory structure
- [ ] Write project creation and management tests (TOP PRIORITY)
- [ ] Write PDF conversion tests (SECOND PRIORITY)
- [ ] Create Phoenix-based test fixtures from live API calls
- [ ] Implement both mocked and live API test suites

### 0.3 Fix GUI Blocking Issues (Days 3-4)
- [ ] Test and document all GUI issues preventing project creation
- [ ] Fix form validation errors
- [ ] Fix state persistence between stages
- [ ] Ensure navigation works correctly
- [ ] Add proper error dialogs

### Success Criteria
- [ ] Can complete full workflow from project creation to report export
- [ ] 60% test coverage for new UI
- [ ] All critical path tests passing
- [ ] Phoenix tracing working for debugging

## Current Project Status

### Application Architecture
- **Technology**: PySide6 desktop application targeting macOS, Windows, and Linux
- **Two UIs Running in Parallel**:
  - **Legacy UI**: Fully functional with recent thread safety fixes
  - **New UI**: 6 of 7 stages complete (missing Refinement stage)

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

## Phase 4: Complete New UI (Week 4-5)

### 4.1 Implement Refinement Stage
- [ ] Create `src/new/stages/refinement_stage.py`
- [ ] Add markdown editor with syntax highlighting
- [ ] Implement LLM-powered refinement suggestions
- [ ] Add version history tracking
- [ ] Include citation verification

### 4.2 Polish & Integration
- [ ] Ensure all 7 stages work seamlessly
- [ ] Add comprehensive error handling
- [ ] Implement keyboard shortcuts
- [ ] Add context-sensitive help
- [ ] Complete accessibility features

### 4.3 Testing New UI
- [ ] Create `tests/test_new/` directory
- [ ] Test each stage independently
- [ ] Test stage transitions
- [ ] Test project lifecycle
- [ ] Test error recovery

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

1. Install development dependencies (pytest-cov, pytest-qt, langfuse)
2. Set up coverage reporting
3. Begin refactoring large files
4. Start writing business logic tests
5. Implement Langfuse for development debugging

## Notes

- Focus on code cleanup and testing before adding new features
- Prioritize maintainability over new functionality
- Ensure cross-platform compatibility at each step
- Keep both UIs functional during transition
- Document decisions and patterns as we go