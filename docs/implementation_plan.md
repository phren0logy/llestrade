# Implementation Plan: Simplified Architecture Migration

## Overview
This plan outlines the step-by-step migration from the current tab-based architecture to a simplified, stage-based workflow that addresses memory management issues and improves stability.

## Phase 1: Foundation (Week 1)

### 1.1 Project Infrastructure
```python
# src/core/project_manager.py
class ProjectManager:
    """Manages project files and state persistence"""
    
    def create_project(self, path: Path, metadata: dict) -> Project
    def load_project(self, project_file: Path) -> Project
    def save_project(self, project: Project) -> None
    def auto_save(self) -> None  # Called periodically
    
# src/core/project.py
@dataclass
class Project:
    """Project data model"""
    version: str
    project_id: str
    metadata: ProjectMetadata
    settings: ProjectSettings
    workflow_state: WorkflowState
    paths: ProjectPaths
```

### 1.2 Stage Management Framework
```python
# src/ui/stage_manager.py
class StageManager(QObject):
    """Controls stage transitions and lifecycle"""
    
    stage_changed = Signal(str)
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.current_stage = None
        self.stages = {
            'setup': ProjectSetupStage,
            'import': DocumentImportStage,
            'process': DocumentProcessingStage,
            'analyze': AnalysisStage,
            'generate': ReportGenerationStage,
            'refine': RefinementStage
        }
    
    def load_stage(self, stage_name: str) -> None
    def cleanup_current_stage(self) -> None
    def can_proceed(self) -> bool
    def can_go_back(self) -> bool

# src/ui/base_stage.py
class BaseStage(QWidget):
    """Base class for all workflow stages"""
    
    progress = Signal(int, str)
    completed = Signal(dict)
    error = Signal(str)
    
    def __init__(self, project: Project):
        self.project = project
        self.worker = None
        
    def validate(self) -> tuple[bool, str]
    def save_state(self) -> None
    def cleanup(self) -> None
    def stop_operations(self) -> None
```

### 1.3 Simplified Main Window
```python
# main_v2.py (new file for testing)
class SimplifiedMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = None
        self.stage_manager = StageManager(self)
        self.setup_ui()
    
    def setup_ui(self):
        # Simple layout with sidebar and content area
        self.central_widget = QWidget()
        self.main_layout = QHBoxLayout()
        
        # Progress sidebar
        self.progress_sidebar = ProgressSidebar()
        self.main_layout.addWidget(self.progress_sidebar, 1)
        
        # Content area
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.main_layout.addWidget(self.content_area, 4)
        
        # Navigation
        self.nav_bar = NavigationBar()
        self.nav_bar.next_clicked.connect(self.next_stage)
        self.nav_bar.prev_clicked.connect(self.prev_stage)
```

## Phase 2: Core Functionality Migration (Week 2-3)

### 2.1 Document Processing Stage
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

- **Week 1**: Foundation and framework
- **Week 2-3**: Core functionality migration
- **Week 4**: Testing and validation
- **Week 5-6**: UI migration and polish
- **Week 7-8**: Gradual rollout and monitoring

Total estimated time: 8 weeks for complete migration