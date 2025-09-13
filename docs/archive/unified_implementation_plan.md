# Unified Implementation Plan: Forensic Report Drafter UI Rewrite

## Executive Summary

This document unifies the simplified workflow design and implementation plan for migrating the Forensic Report Drafter from its current tab-based architecture to a streamlined, stage-based workflow. The new design addresses memory management issues, improves stability, and provides a more intuitive user experience while maintaining full compatibility with the existing application during the transition.

### Key Goals
- Zero disruption to current users
- Reduce memory footprint from 500MB+ to under 200MB
- Implement project-based workflow with automatic state persistence
- Follow PySide6 best practices throughout
- Prepare for professional distribution

### Timeline
- **Total Duration**: 10 weeks
- **Parallel Development**: Both UIs operational throughout
- **Gradual Rollout**: Feature flags enable safe transition

## Table of Contents
1. [Transition Strategy](#transition-strategy)
2. [Architecture Overview](#architecture-overview)
3. [Project Structure](#project-structure)
4. [Implementation Phases](#implementation-phases)
5. [Feature Integration](#feature-integration)
6. [PySide6 Best Practices](#pyside6-best-practices)
7. [Testing Strategy](#testing-strategy)
8. [Distribution Plan](#distribution-plan)

## Transition Strategy

### Smart Launcher System
The application now uses a smart launcher (`main.py`) that routes to either UI:

```python
# main.py - Smart launcher
import os
import sys

def main():
    use_new_ui = (
        "--new-ui" in sys.argv 
        or os.getenv("USE_NEW_UI", "").lower() in ("true", "1", "yes")
    )
    
    if use_new_ui:
        from main_new import main as new_main
        return new_main()
    else:
        from main_legacy import main as legacy_main
        return legacy_main()
```

### Directory Structure
```
project/
├── main.py              # Smart launcher (NEW)
├── main_legacy.py       # Current application (RENAMED)
├── main_new.py          # New simplified UI (CREATED)
├── src/
│   ├── legacy/          # Current UI code (MOVED)
│   ├── new/             # New UI implementation (IN PROGRESS)
│   │   ├── core/        # Project management, settings
│   │   ├── stages/      # Stage-based components
│   │   ├── widgets/     # Reusable widgets
│   │   └── workers/     # Thread workers
│   └── common/          # Shared utilities (llm/, core utilities)
└── tests/
    ├── test_legacy/     # Tests for current UI
    └── test_new/        # Tests for new UI
```

## Architecture Overview

### Current Architecture (Legacy)
```
MainWindow
├── QTabWidget (5 tabs always loaded)
│   ├── PromptsTab (Complex signal/slot connections)
│   ├── TestingTab (PDF viewer widgets)
│   ├── RefinementTab (Text editors)
│   ├── PDFProcessingTab (File lists)
│   └── AnalysisTab (Multiple threads)
└── DebugDashboard (Additional widgets)
```

**Issues**:
- All tabs loaded at startup (high memory usage)
- Multiple concurrent threads
- Complex widget hierarchies
- Accumulating signal/slot connections

### New Architecture
```
SimplifiedMainWindow
├── MenuBar (File, Edit, Settings, Help)
├── ToolBar (Common actions)
├── MainContent
│   ├── ProgressSidebar (Lightweight workflow indicator)
│   └── StageContainer (Single active stage)
└── StatusBar (Progress, costs, status)
```

**Benefits**:
- Single active stage (minimal memory)
- Sequential processing
- Clear resource cleanup
- Simple widget hierarchy

## Project Structure

### Project File Format (.frpd)
```json
{
  "version": "1.0",
  "project_id": "uuid-string",
  "created_date": "2025-07-03T10:00:00Z",
  "last_modified": "2025-07-03T14:30:00Z",
  "metadata": {
    "case_name": "Smith v. Jones",
    "case_number": "2025-CV-1234",
    "subject_name": "John Smith",
    "date_of_birth": "1985-03-15",
    "evaluation_date": "2025-06-15",
    "evaluator": "Dr. Jane Doe",
    "case_description": "Detailed case background..."
  },
  "costs": {
    "total": 12.45,
    "by_provider": {
      "anthropic": 8.20,
      "azure_openai": 4.25
    },
    "by_stage": {
      "document_analysis": 6.50,
      "report_generation": 5.95
    }
  },
  "settings": {
    "llm_provider": "anthropic",
    "llm_model": "claude-sonnet-4-20250514",
    "template_id": "standard_competency"
  },
  "workflow_state": {
    "current_stage": "document_processing",
    "completed_stages": ["project_setup", "document_import"],
    "stage_data": {...}
  }
}
```

## Implementation Phases

### Phase 0: Setup Parallel Development (Week 1)
1. **Repository Restructuring**
   - [x] Rename main.py to main_legacy.py
   - [x] Create smart launcher main.py
   - [x] Move current UI code to src/legacy/
   - [x] Create src/new/ structure
   - [x] Update imports in legacy code

2. **Build System Updates**
   - [x] Update run scripts for both UIs (run_new_ui.sh, run_app.sh)
   - [ ] Configure pytest for parallel testing
   - [ ] Setup feature flags

3. **Critical Bug Fixes** (NEW - Completed 2025-01-11)
   - [x] Fix thread safety issues in worker threads
   - [x] Replace direct UI access with Qt signals
   - [x] Update LLMSummaryThread to use status_signal
   - [x] Update IntegratedAnalysisThread to use status_signal
   - [x] Remove status_panel parameters from constructors
   - [x] Update test files for new signatures

### Phase 1: Core Infrastructure (Week 2-3)

#### 1.1 Secure Settings System
```python
# src/new/core/secure_settings.py
import keyring
from PySide6.QtCore import QObject, Signal

class SecureSettings(QObject):
    """Manages application settings with OS keychain integration."""
    
    settings_changed = Signal()
    
    SERVICE_NAME = "ForensicReportDrafter"
    
    def __init__(self):
        super().__init__()
        self._cache = {}
        
    def set_api_key(self, provider: str, api_key: str):
        """Store API key securely in OS keychain."""
        keyring.set_password(
            self.SERVICE_NAME,
            f"api_key_{provider}",
            api_key
        )
        self.settings_changed.emit()
        
    def get_api_key(self, provider: str) -> str:
        """Retrieve API key from OS keychain."""
        if provider in self._cache:
            return self._cache[provider]
            
        key = keyring.get_password(
            self.SERVICE_NAME,
            f"api_key_{provider}"
        )
        if key:
            self._cache[provider] = key
        return key
```

#### 1.2 Project Manager
```python
# src/new/core/project_manager.py
from PySide6.QtCore import QObject, Signal, QTimer
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
import uuid

@dataclass
class ProjectMetadata:
    case_name: str
    case_number: str
    subject_name: str
    date_of_birth: str
    evaluation_date: str
    evaluator: str
    case_description: str

@dataclass
class ProjectCosts:
    total: float = 0.0
    by_provider: dict = None
    by_stage: dict = None
    
    def __post_init__(self):
        if self.by_provider is None:
            self.by_provider = {}
        if self.by_stage is None:
            self.by_stage = {}

class ProjectManager(QObject):
    """Manages project files with auto-save and state persistence."""
    
    project_changed = Signal()
    auto_saved = Signal()
    
    def __init__(self, project_path: Optional[Path] = None):
        super().__init__()
        self.project_path = project_path
        self.project_data = {}
        self._auto_save_timer = QTimer()
        self._auto_save_timer.timeout.connect(self.auto_save)
        self._auto_save_timer.setInterval(60000)  # 1 minute
        
        if project_path:
            self.load_project()
            
    def create_project(self, path: Path, metadata: ProjectMetadata):
        """Create new project with initial structure."""
        self.project_path = path / f"{metadata.case_name}.frpd"
        self.project_data = {
            "version": "1.0",
            "project_id": str(uuid.uuid4()),
            "created_date": datetime.now().isoformat(),
            "metadata": asdict(metadata),
            "costs": asdict(ProjectCosts()),
            "settings": {
                "llm_provider": "anthropic",
                "llm_model": "claude-sonnet-4-20250514"
            },
            "workflow_state": {
                "current_stage": "project_setup",
                "completed_stages": [],
                "stage_data": {}
            }
        }
        
        # Create directory structure
        (path / "source_documents").mkdir(parents=True, exist_ok=True)
        (path / "processed_documents").mkdir(exist_ok=True)
        (path / "summaries").mkdir(exist_ok=True)
        (path / "reports").mkdir(exist_ok=True)
        (path / "logs").mkdir(exist_ok=True)
        
        self.save_project()
        self._auto_save_timer.start()
        self.project_changed.emit()
```

#### 1.3 Stage Management Framework
```python
# src/new/core/stage_manager.py
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget
from typing import Dict, Optional

class StageManager(QObject):
    """Controls stage transitions and lifecycle."""
    
    stage_changed = Signal(str)
    can_proceed_changed = Signal(bool)
    can_go_back_changed = Signal(bool)
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.current_stage: Optional[BaseStage] = None
        self.current_stage_name: str = ""
        self.stages = self._initialize_stages()
        
    def _initialize_stages(self) -> Dict[str, type]:
        """Import and register all stage classes."""
        from src.new.stages import (
            ProjectSetupStage,
            DocumentImportStage,
            DocumentProcessingStage,
            AnalysisStage,
            ReportGenerationStage,
            RefinementStage
        )
        
        return {
            'setup': ProjectSetupStage,
            'import': DocumentImportStage,
            'process': DocumentProcessingStage,
            'analyze': AnalysisStage,
            'generate': ReportGenerationStage,
            'refine': RefinementStage
        }
        
    def load_stage(self, stage_name: str):
        """Load a new stage with proper cleanup."""
        if self.current_stage:
            self.cleanup_current_stage()
            
        # Force event processing
        QApplication.processEvents()
        
        # Create new stage
        stage_class = self.stages.get(stage_name)
        if not stage_class:
            raise ValueError(f"Unknown stage: {stage_name}")
            
        self.current_stage = stage_class(self.main_window.project)
        self.current_stage_name = stage_name
        
        # Connect signals
        self.current_stage.completed.connect(self._on_stage_completed)
        self.current_stage.validation_changed.connect(self._update_navigation)
        
        # Add to main window
        self.main_window.set_stage_widget(self.current_stage)
        
        self.stage_changed.emit(stage_name)
        self._update_navigation()
```

### Phase 2: Feature Migration (Week 4-5)

#### 2.1 Cost Tracking Integration
```python
# src/new/widgets/cost_tracker.py
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout
from PySide6.QtCore import Signal, Slot

class CostTracker(QWidget):
    """Widget to display running costs in status bar."""
    
    def __init__(self, project_manager):
        super().__init__()
        self.project_manager = project_manager
        self.setup_ui()
        
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.cost_label = QLabel("Cost: $0.00")
        layout.addWidget(self.cost_label)
        
    @Slot(str, float)
    def add_cost(self, provider: str, amount: float):
        """Add cost to project tracking."""
        costs = self.project_manager.project_data.get("costs", {})
        costs["total"] = costs.get("total", 0) + amount
        
        by_provider = costs.get("by_provider", {})
        by_provider[provider] = by_provider.get(provider, 0) + amount
        costs["by_provider"] = by_provider
        
        self.project_manager.project_data["costs"] = costs
        self.project_manager.save_project()
        
        self.update_display()
        
    def update_display(self):
        """Update the cost display."""
        total = self.project_manager.project_data.get("costs", {}).get("total", 0)
        self.cost_label.setText(f"Cost: ${total:.2f}")
```

#### 2.2 Model Auto-Discovery
```python
# src/new/widgets/model_discovery.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QTableWidget, QTableWidgetItem
)
from PySide6.QtCore import Signal, QThread

class ModelDiscoveryThread(QThread):
    """Background thread for discovering available models."""
    
    model_discovered = Signal(str, str, dict)  # provider, model, capabilities
    discovery_complete = Signal()
    
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        
    def run(self):
        """Discover models for each configured provider."""
        providers = ["anthropic", "gemini", "azure_openai"]
        
        for provider in providers:
            api_key = self.settings.get_api_key(provider)
            if not api_key:
                continue
                
            try:
                # Use the LLM factory to test connection
                from llm import create_provider
                provider_instance = create_provider(provider)
                
                # Get model info
                models = self._get_provider_models(provider, provider_instance)
                for model_name, capabilities in models.items():
                    self.model_discovered.emit(provider, model_name, capabilities)
                    
            except Exception as e:
                print(f"Failed to discover models for {provider}: {e}")
                
        self.discovery_complete.emit()
```

#### 2.3 Template Gallery
```python
# src/new/widgets/template_gallery.py
from PySide6.QtWidgets import (
    QWidget, QListWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QTextEdit,
    QSplitter, QListWidgetItem
)
from PySide6.QtCore import Signal, Qt
import json
from pathlib import Path

class TemplateGallery(QWidget):
    """Browse and select report templates."""
    
    template_selected = Signal(str, dict)  # template_id, template_data
    
    def __init__(self):
        super().__init__()
        self.templates = {}
        self.setup_ui()
        self.load_templates()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Splitter for list and preview
        splitter = QSplitter(Qt.Horizontal)
        
        # Template list
        self.template_list = QListWidget()
        self.template_list.currentItemChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.template_list)
        
        # Preview pane
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        preview_layout.addWidget(self.preview_text)
        
        # Action buttons
        button_layout = QHBoxLayout()
        self.use_button = QPushButton("Use Template")
        self.use_button.clicked.connect(self._use_template)
        self.import_button = QPushButton("Import...")
        button_layout.addWidget(self.use_button)
        button_layout.addWidget(self.import_button)
        preview_layout.addLayout(button_layout)
        
        splitter.addWidget(preview_widget)
        layout.addWidget(splitter)
        
    def load_templates(self):
        """Load available templates."""
        template_dir = Path(__file__).parent.parent / "templates"
        for template_file in template_dir.glob("*.json"):
            with open(template_file) as f:
                template_data = json.load(f)
                self.templates[template_file.stem] = template_data
                
                item = QListWidgetItem(template_data.get("name", template_file.stem))
                item.setData(Qt.UserRole, template_file.stem)
                self.template_list.addItem(item)
```

#### 2.4 Enhanced Progress Indicators
```python
# src/new/widgets/enhanced_progress.py
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QProgressBar,
    QLabel, QPushButton, QTextEdit
)
from PySide6.QtCore import Signal, Slot, QTimer
import time

class EnhancedProgressDialog(QDialog):
    """Progress dialog with pause/resume and detailed info."""
    
    pause_requested = Signal()
    resume_requested = Signal()
    cancel_requested = Signal()
    
    def __init__(self, title="Processing...", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.start_time = time.time()
        self.is_paused = False
        self.setup_ui()
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_time)
        self.update_timer.start(1000)
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Main progress
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # Status text
        self.status_label = QLabel("Initializing...")
        layout.addWidget(self.status_label)
        
        # Detailed info
        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)
        
        # Token count
        self.token_label = QLabel("Tokens: 0")
        layout.addWidget(self.token_label)
        
        # Time elapsed
        self.time_label = QLabel("Time: 0:00")
        layout.addWidget(self.time_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self._toggle_pause)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        
        button_layout.addWidget(self.pause_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        self.resize(400, 200)
        
    @Slot(int, str)
    def update_progress(self, value: int, status: str):
        """Update progress and status."""
        self.progress_bar.setValue(value)
        self.status_label.setText(status)
        
        # Estimate time remaining
        if value > 0:
            elapsed = time.time() - self.start_time
            rate = value / elapsed
            remaining = (100 - value) / rate if rate > 0 else 0
            eta_text = f"ETA: {int(remaining)}s"
            self.detail_label.setText(eta_text)
            
    @Slot(int)
    def update_tokens(self, count: int):
        """Update token count display."""
        self.token_label.setText(f"Tokens: {count:,}")
```

### Phase 3: UI Components (Week 6-7)

#### Base Stage Class
```python
# src/new/stages/base_stage.py
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal
from abc import abstractmethod
from typing import Optional, Tuple

class BaseStage(QWidget):
    """Base class for all workflow stages."""
    
    # Signals
    progress = Signal(int, str)  # percent, message
    completed = Signal(dict)     # results
    error = Signal(str)          # error message
    validation_changed = Signal(bool)  # can proceed
    
    def __init__(self, project):
        super().__init__()
        self.project = project
        self.worker: Optional[QThread] = None
        self._is_valid = False
        self.setup_ui()
        self.load_state()
        
    @abstractmethod
    def setup_ui(self):
        """Create the UI for this stage."""
        pass
        
    @abstractmethod
    def validate(self) -> Tuple[bool, str]:
        """Check if stage can proceed."""
        pass
        
    @abstractmethod
    def save_state(self):
        """Save current state to project."""
        pass
        
    @abstractmethod
    def load_state(self):
        """Load state from project."""
        pass
        
    def cleanup(self):
        """Clean up resources when leaving stage."""
        self.stop_operations()
        
        # Disconnect all signals
        try:
            self.progress.disconnect()
            self.completed.disconnect()
            self.error.disconnect()
            self.validation_changed.disconnect()
        except:
            pass
            
        # Clear any heavy resources
        if hasattr(self, 'llm_provider'):
            self.llm_provider = None
            
        # Schedule for deletion
        self.deleteLater()
        
    def stop_operations(self):
        """Stop any running operations."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)  # Wait up to 5 seconds
            if self.worker.isRunning():
                self.worker.terminate()
            self.worker.deleteLater()
            self.worker = None
```

## Recent Improvements

### 2025-01-11 - Phase 1 Complete

### Thread Safety Fixes
Fixed critical memory crashes caused by direct UI access from worker threads:

1. **LLMSummaryThread**:
   - Added `_safe_emit_status()` method for thread-safe UI updates
   - Replaced all direct `status_panel` calls with signal emissions
   - Removed `status_panel` parameter from constructor
   - Connected `status_signal` to handler in `analysis_tab.py`

2. **IntegratedAnalysisThread**:
   - Applied same pattern as LLMSummaryThread
   - Replaced 32 instances of direct UI access
   - All UI updates now go through Qt signal/slot mechanism

3. **Test Updates**:
   - Updated test files to match new constructor signatures
   - Fixed token counting function references
   - All tests passing with new thread-safe implementation

These fixes ensure all UI updates happen on the main thread, preventing the malloc double-free errors observed on macOS.

### Directory Reorganization
1. **Completed Structure**:
   - Moved UI code to `src/legacy/ui/`
   - Moved LLM code to `src/common/llm/`
   - Created `src/new/` hierarchy
   - Updated all imports using automated script
   - Created symlinks for backward compatibility

2. **Foundation Classes Created**:
   - **SecureSettings**: Manages API keys with OS keychain integration
   - **ProjectManager**: Handles .frpd project files with auto-save
   - **StageManager**: Controls workflow stages and transitions
   - **BaseStage**: Abstract base for all workflow stages

3. **New UI Entry Point**:
   - `main_new.py` created and functional
   - Basic window with status message
   - Both UIs accessible via smart launcher

## PySide6 Best Practices

### 1. Signal/Slot Patterns
```python
# ✅ Good: Type-safe, new-style signals
class MyWidget(QWidget):
    data_changed = Signal(dict)
    progress_updated = Signal(int, str)
    
    def __init__(self):
        super().__init__()
        # New-style connection
        self.button.clicked.connect(self.on_button_clicked)
        
# ❌ Bad: Old-style string-based
self.connect(button, SIGNAL("clicked()"), self.on_click)
```

### 2. Thread Safety
```python
# ✅ Good: Proper thread communication
class Worker(QThread):
    result_ready = Signal(dict)
    
    def run(self):
        # Do work in thread
        result = self.process_data()
        # Emit signal to update UI from main thread
        self.result_ready.emit(result)
        
# ❌ Bad: Direct UI access from thread
class BadWorker(QThread):
    def run(self):
        self.parent().label.setText("Done")  # Will crash!
```

### 3. Resource Management
```python
# ✅ Good: Proper parent-child relationships
class StageWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Children automatically deleted with parent
        self.layout = QVBoxLayout(self)
        self.label = QLabel("Stage", self)
        
# ✅ Good: Explicit cleanup
def cleanup(self):
    if self.worker:
        self.worker.stop()
        self.worker.deleteLater()
        self.worker = None
```

### 4. Layout Management
```python
# ✅ Good: Responsive layouts
layout = QVBoxLayout()
layout.setContentsMargins(8, 8, 8, 8)
layout.setSpacing(4)

# Use stretch factors for responsive design
layout.addWidget(sidebar, 1)  # 1/5 of space
layout.addWidget(content, 4)  # 4/5 of space

# ❌ Bad: Fixed positioning
widget.move(100, 50)  # Will break on different screens
```

### 5. Style Management
```python
# ✅ Good: Centralized styling
class AppStyle:
    @staticmethod
    def apply(app: QApplication):
        app.setStyle("Fusion")  # Cross-platform style
        
        # Define palette
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(240, 240, 240))
        app.setPalette(palette)
        
        # Global style sheet
        app.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 0.5em;
                padding-top: 0.5em;
            }
        """)
```

### 6. Event Handling
```python
# ✅ Good: Proper event handling
class CustomWidget(QWidget):
    def event(self, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.close()
                return True
        return super().event(event)
        
    def closeEvent(self, event):
        # Cleanup before closing
        if self.has_unsaved_changes():
            reply = QMessageBox.question(...)
            if reply == QMessageBox.No:
                event.ignore()
                return
        event.accept()
```

## Testing Strategy

### 1. Parallel Testing Structure
```
tests/
├── conftest.py          # Shared fixtures
├── test_legacy/         # Current UI tests
│   ├── test_tabs.py
│   └── test_integration.py
└── test_new/           # New UI tests
    ├── test_stages.py
    ├── test_memory.py
    └── test_integration.py
```

### 2. Memory Profiling Tests
```python
# tests/test_new/test_memory.py
import tracemalloc
import gc
from PySide6.QtWidgets import QApplication
import pytest

def test_stage_memory_cleanup():
    """Verify stages properly release memory."""
    tracemalloc.start()
    
    app = QApplication.instance() or QApplication([])
    window = SimplifiedMainWindow()
    
    # Baseline
    gc.collect()
    baseline = tracemalloc.get_traced_memory()[0]
    
    # Cycle through all stages
    stages = ['setup', 'import', 'process', 'analyze', 'generate', 'refine']
    
    for stage in stages:
        window.stage_manager.load_stage(stage)
        QApplication.processEvents()
        
        # Check memory didn't grow too much
        current = tracemalloc.get_traced_memory()[0]
        growth = current - baseline
        assert growth < 50_000_000, f"Memory grew by {growth/1e6:.1f}MB at {stage}"
        
        # Cleanup
        window.stage_manager.cleanup_current_stage()
        gc.collect()
        QApplication.processEvents()
    
    tracemalloc.stop()
```

### 3. Integration Tests
```python
def test_full_workflow():
    """Test complete workflow from project creation to report."""
    app = QApplication.instance() or QApplication([])
    window = SimplifiedMainWindow()
    
    # Create project
    project_data = {
        "case_name": "Test Case",
        "subject_name": "John Doe",
        # ... other metadata
    }
    window.create_project(Path("/tmp/test_project"), project_data)
    
    # Progress through stages
    assert window.stage_manager.current_stage_name == "setup"
    
    # Simulate document import
    window.stage_manager.load_stage("import")
    # ... test each stage
```

## Distribution Plan

### 1. Build Configuration
```python
# forensic_report_drafter.spec
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('prompt_templates', 'prompt_templates'),
        ('resources', 'resources'),
        ('src', 'src'),  # Include source for both UIs
    ],
    hiddenimports=[
        'tiktoken',
        'keyring.backends',
        'keyring.backends.macOS',
        'keyring.backends.Windows',
        'keyring.backends.SecretService',
        'llm.providers.anthropic',
        'llm.providers.gemini',
        'llm.providers.azure_openai',
    ],
    hookspath=['build_hooks'],
    runtime_hooks=['build_hooks/runtime_select_ui.py'],
    excludes=['tkinter'],
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ForensicReportDrafter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='resources/icon.ico'
)
```

### 2. Platform-Specific Builds
- **macOS**: Universal binary, code signing, notarization
- **Windows**: NSIS installer, code signing
- **Linux**: AppImage for broad compatibility

### 3. Auto-Update System
```python
# src/common/updater.py
class AutoUpdater(QObject):
    """Check for and apply updates."""
    
    update_available = Signal(str)  # version
    update_downloaded = Signal()
    
    def __init__(self):
        super().__init__()
        self.update_url = "https://api.forensicreportdrafter.com/updates"
        
    def check_for_updates(self):
        """Check if newer version available."""
        # Implementation details...
```

## Timeline and Milestones

### Week 1-2: Foundation
- [x] Create smart launcher system
- [x] Fix critical thread safety issues
- [x] Reorganize directory structure
- [ ] Setup parallel testing
- [x] Create base infrastructure classes

### Week 3-4: Core Features
- [x] Implement secure settings (SecureSettings class)
- [x] Create project manager (ProjectManager class)
- [x] Build stage framework (StageManager class)
- [ ] Add cost tracking widget

### Week 5-6: UI Components
- [ ] Create all stage widgets
- [ ] Implement enhanced progress
- [ ] Add template gallery
- [ ] Build model discovery

### Week 7-8: Integration & Testing
- [ ] Full integration testing
- [ ] Memory profiling
- [ ] Performance optimization
- [ ] Bug fixes

### Week 9-10: Polish & Release
- [ ] UI polish and refinement
- [ ] Documentation
- [ ] Build distribution packages
- [ ] Beta testing
- [ ] Gradual rollout

## Success Metrics

### Performance
- Memory usage < 200MB normal operation
- Stage transitions < 1 second
- No memory growth over 8-hour session

### Stability  
- Zero crashes in normal use
- Graceful error handling
- Successful crash recovery

### User Experience
- Intuitive workflow progression
- Clear status/progress at all times
- Responsive during long operations

## Risk Mitigation

### Development Risks
- **Risk**: Breaking existing functionality
- **Mitigation**: Parallel development, comprehensive tests

### User Adoption
- **Risk**: Users resist change
- **Mitigation**: Gradual rollout, easy switching, familiar concepts

### Technical Debt
- **Risk**: Accumulating complexity
- **Mitigation**: Clean architecture, best practices, regular refactoring

## Next Steps (January 2025)

### Immediate Priorities

#### 1. Create First Stage - ProjectSetupStage (2-3 days)
```python
# src/new/stages/setup_stage.py
class ProjectSetupStage(BaseStage):
    """Initial project setup and metadata collection."""
    
    def setup_ui(self):
        # Case information form
        # Subject details
        # Output directory selection
        # API key configuration check
```

Key features:
- Form validation with real-time feedback
- Recent projects dropdown
- Template selection
- API key status indicators

#### 2. Build Workflow Sidebar (2 days)
- Visual progress indicator showing all stages
- Clickable stages (when accessible)
- Completion checkmarks
- Current stage highlighting
- Time estimates per stage

#### 3. Implement Cost Tracking Widget (1 day)
- Real-time cost display in status bar
- Breakdown by provider and stage
- Export cost report functionality
- Cost estimation before operations

#### 4. Create Welcome Screen (2 days)
- Recent projects grid with thumbnails
- Quick start wizard
- API key configuration status
- What's new section
- Tutorial/help links

### Testing Priorities

1. **Memory Leak Testing**
   - Create test that cycles through stages repeatedly
   - Monitor memory usage over time
   - Verify proper cleanup between stages

2. **API Key Security**
   - Test keyring integration on all platforms
   - Verify fallback to encrypted file storage
   - Test key rotation scenarios

3. **Project File Integrity**
   - Test auto-save functionality
   - Verify backup creation
   - Test recovery from corrupted files

### Architecture Decisions

1. **Worker Thread Pattern**
   - All stages will use the same worker thread pattern
   - Standardized progress reporting
   - Consistent error handling
   - Proper cancellation support

2. **State Management**
   - Each stage responsible for its own state
   - Project manager as single source of truth
   - Automatic state persistence on changes

3. **UI Consistency**
   - Material Design inspired components
   - Consistent color scheme
   - Responsive layouts
   - Accessibility considerations

## Conclusion

This unified plan provides a clear path to modernize the Forensic Report Drafter while maintaining stability for existing users. By following PySide6 best practices and implementing a clean architecture, we'll deliver a professional application ready for distribution to forensic psychologists worldwide.