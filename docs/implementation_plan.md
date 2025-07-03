# Implementation Plan: Simplified Architecture Migration

## Overview
This plan outlines the step-by-step migration from the current tab-based architecture to a simplified, stage-based workflow that addresses memory management issues and improves stability.

## Status Update (January 11, 2025)
- ✅ Phase 1 Complete: Foundation infrastructure built
- ✅ Thread safety issues fixed in legacy app
- ✅ Project structure reorganized for parallel development
- 🚧 Phase 2 In Progress: ProjectSetupStage and DocumentImportStage completed

## Phase 1: Foundation (Week 1) ✅ COMPLETED

### 1.1 Project Infrastructure ✅
Implemented in `src/new/core/project_manager.py`:
- **ProjectManager**: Handles .frpd files with auto-save every 60 seconds
- **ProjectMetadata**: Dataclass for case information
- **ProjectCosts**: Tracks costs by provider and stage
- **WorkflowState**: Manages stage progression
- Automatic backup system (keeps last 10 versions)
- Project directory structure creation

### 1.2 Stage Management Framework ✅
Implemented in `src/new/core/stage_manager.py`:
- **StageManager**: Controls stage transitions with proper cleanup
- **BaseStage**: Abstract base class with lifecycle methods
- Dynamic stage registration system
- Navigation state management (can_proceed, can_go_back)
- Signal-based communication for UI updates
- Automatic resource cleanup between stages

### 1.3 Simplified Main Window ✅
Implemented in `main_new.py`:
- **SimplifiedMainWindow**: Clean architecture with menu/toolbar
- Integrated SecureSettings for API key management
- Connected to StageManager for workflow control
- Smart launcher (`main.py`) routes between UIs
- Both UIs run in parallel with `--new-ui` flag

### 1.4 Additional Foundation Components ✅

#### SecureSettings (`src/new/core/secure_settings.py`)
- OS keychain integration for API keys
- Fallback to encrypted file storage
- Window state persistence
- Recent projects management
- Settings import/export

#### ProjectSetupStage (`src/new/stages/setup_stage.py`) ✅
- First functional workflow stage
- Comprehensive form validation
- API key status indicators
- Template selection
- Output directory configuration
- Loading spinner during project creation
- Integration with ProjectManager

#### APIKeyDialog (`src/new/widgets/api_key_dialog.py`) ✅
- Secure API key configuration
- Password field with show/hide toggle
- Direct links to provider dashboards
- Azure-specific settings support

#### DocumentImportStage (`src/new/stages/import_stage.py`) ✅
- Drag-and-drop file interface
- Multiple file selection with validation
- File type support (PDF, DOC, DOCX, TXT, MD)
- Live preview for text files
- Import progress tracking
- Duplicate file handling
- State persistence

## Phase 2: Core Functionality Migration (Week 2-3) 🚧 IN PROGRESS

### 2.1 Document Processing Stage 🔄 NEXT
Migrate PDF processing functionality with improvements:

```python
# src/ui/stages/document_processing.py
class DocumentProcessingStage(BaseStage):
    def __init__(self, project: Project):
        super().__init__(project)
        self.setup_ui()
        self.load_pending_documents()
    
    def process_documents(self):
        # Single-threaded processing
        self.worker = DocumentProcessor(self.project)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_processing_complete)
        self.worker.start()
    
    def cleanup(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait()
            self.worker.deleteLater()
```

### 2.2 Analysis Stage
Simplified analysis with better resource management:

```python
# src/ui/stages/analysis.py
class AnalysisStage(BaseStage):
    def __init__(self, project: Project):
        super().__init__(project)
        self.llm_provider = None
        
    def analyze_documents(self):
        # Lazy load LLM provider
        if not self.llm_provider:
            self.llm_provider = create_provider(
                self.project.settings.llm_provider
            )
        
        # Process one document at a time
        self.worker = AnalysisWorker(
            self.project, 
            self.llm_provider
        )
        self.worker.start()
```

### 2.3 Memory-Safe Worker Pattern
```python
# src/ui/workers/base_worker.py
class BaseWorker(QThread):
    """Memory-safe worker thread base class"""
    
    def __init__(self):
        super().__init__()
        self._is_running = True
        self._mutex = QMutex()
    
    def stop(self):
        self._mutex.lock()
        self._is_running = False
        self._mutex.unlock()
    
    def is_running(self):
        self._mutex.lock()
        running = self._is_running
        self._mutex.unlock()
        return running
    
    def run(self):
        try:
            self.process()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            # Ensure cleanup
            self.cleanup_resources()
```

## Phase 3: Testing and Validation (Week 4)

### 3.1 Memory Profiling Tests
```python
# tests/test_memory_usage.py
def test_stage_transitions():
    """Verify memory is properly released between stages"""
    import tracemalloc
    
    tracemalloc.start()
    app = SimplifiedMainWindow()
    
    # Measure baseline
    baseline = tracemalloc.get_traced_memory()[0]
    
    # Cycle through stages
    for stage in ['setup', 'import', 'process']:
        app.stage_manager.load_stage(stage)
        QApplication.processEvents()
        
        current = tracemalloc.get_traced_memory()[0]
        assert current - baseline < 50_000_000  # 50MB max increase
        
        app.stage_manager.cleanup_current_stage()
        QApplication.processEvents()
```

### 3.2 Thread Safety Tests
```python
# tests/test_thread_safety.py
def test_single_worker_constraint():
    """Ensure only one worker thread at a time"""
    stage = DocumentProcessingStage(mock_project)
    
    # Start first operation
    stage.process_documents()
    assert stage.worker.isRunning()
    
    # Try to start second operation
    stage.process_documents()  # Should queue or reject
    
    # Verify still only one worker
    assert threading.active_count() == 2  # Main + 1 worker
```

## Phase 4: UI Migration (Week 5-6)

### 4.1 Component Library
Create reusable components following Qt best practices:

```python
# src/ui/components/
- progress_indicator.py    # Unified progress widget
- document_list.py        # Efficient list with virtual scrolling
- markdown_editor.py      # Lightweight markdown editor
- status_panel.py         # Consistent status display
```

### 4.2 Styling and Polish
```python
# src/ui/styles/app_style.py
class AppStyle:
    """Centralized styling for consistency"""
    
    STAGE_COMPLETED = "QWidget { background-color: #e8f5e9; }"
    STAGE_ACTIVE = "QWidget { background-color: #e3f2fd; }"
    STAGE_PENDING = "QWidget { background-color: #f5f5f5; }"
```

## Phase 5: Gradual Rollout (Week 7-8)

### 5.1 Feature Flag System
```python
# src/config/features.py
FEATURES = {
    'use_simplified_ui': os.getenv('USE_SIMPLIFIED_UI', 'false').lower() == 'true',
    'enable_auto_save': True,
    'single_thread_mode': True
}

# main.py
if FEATURES['use_simplified_ui']:
    from main_v2 import SimplifiedMainWindow
    window = SimplifiedMainWindow()
else:
    window = ForensicReportDrafterApp()  # Current version
```

### 5.2 Migration Tools
```python
# scripts/migrate_to_project.py
"""Convert existing work to project format"""

def migrate_directory(old_dir: Path, project_name: str):
    # Create project structure
    # Move files to appropriate locations
    # Generate project.frpd file
```

## Success Metrics

### Performance
- [ ] Memory usage stays under 200MB during normal operation
- [ ] No memory growth over extended sessions
- [ ] Stage transitions complete in < 1 second

### Stability
- [ ] No crashes during 8-hour usage sessions
- [ ] Graceful handling of all error conditions
- [ ] Successful recovery from unexpected termination

### User Experience
- [ ] Clear progress indication at all times
- [ ] Responsive UI during long operations
- [ ] Intuitive navigation between stages

## Risk Mitigation

### Parallel Development
- Keep current version functional during migration
- Use feature flags for gradual rollout
- Maintain backward compatibility for existing users

### Testing Strategy
- Unit tests for each new component
- Integration tests for stage transitions
- Memory profiling in CI/CD pipeline
- Beta testing with volunteer users

### Rollback Plan
- Feature flag to instantly revert to old UI
- Keep old code in separate modules
- Document all breaking changes

## Timeline Summary

- **Week 1**: Foundation and framework ✅ COMPLETED
- **Week 2-3**: Core functionality migration 🚧 IN PROGRESS
- **Week 4**: Testing and validation
- **Week 5-6**: UI migration and polish
- **Week 7-8**: Gradual rollout and monitoring

Total estimated time: 8 weeks for complete migration

## Immediate Next Steps (Priority Order)

### 1. Complete ProjectSetupStage Integration (1 day) ✅
- [x] Hook up form submission to ProjectManager.create_project()
- [x] Implement project directory creation
- [x] Add loading spinner during project creation
- [x] Navigate to next stage on completion

### 2. Create DocumentImportStage (2-3 days) ✅
- [x] File drag-and-drop interface
- [x] Multiple file selection
- [x] File type validation (PDF, DOC, TXT)
- [x] Preview of imported documents
- [x] Batch import progress

### 3. Build Workflow Sidebar (2 days) 🔄 NEXT
- [ ] Visual progress indicator
- [ ] Stage status (completed/current/pending)
- [ ] Clickable navigation (when allowed)
- [ ] Time estimates per stage

### 4. Implement Welcome Screen (1-2 days)
- [ ] Recent projects grid
- [ ] New project button
- [ ] Open project functionality
- [ ] API key status summary
- [ ] Quick start guide

### 5. Create Document Processing Stage (2-3 days)
- [ ] Convert PDFs with Azure Document Intelligence
- [ ] Process Word documents
- [ ] Handle text file imports
- [ ] Show processing progress
- [ ] Error handling and retry logic

## Technical Debt to Address

### High Priority
- [ ] Install keyring module for secure API storage
- [ ] Add pytest fixtures for new UI components
- [ ] Create integration tests for stage transitions
- [ ] Document new architecture in README

### Medium Priority  
- [ ] Implement proper logging for new UI
- [ ] Add telemetry for usage patterns
- [ ] Create user preferences dialog
- [ ] Build help system with tooltips
- [ ] Integrate Langfuse for LLM observability and cost tracking

### Low Priority
- [ ] Add theme support (light/dark)
- [ ] Implement keyboard shortcuts
- [ ] Create onboarding tutorial
- [ ] Add export templates

## Deferred Items (Pending Dependencies)

### Cost Tracking Widget (Deferred until Langfuse integration)
- [ ] Real-time cost display in status bar
- [ ] Provider breakdown tooltip
- [ ] Stage-by-stage cost tracking
- [ ] Export cost report
- [ ] Integration with ProjectCosts in ProjectManager

**Note**: Cost tracking functionality is deferred until Langfuse is integrated, as it will provide:
- Automatic cost calculation based on token usage
- Built-in pricing for all major LLM providers
- Historical cost analytics and reporting
- More accurate token counting across providers