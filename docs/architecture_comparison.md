# Architecture Comparison: Current vs Simplified

## Current Architecture Issues

### Complex Widget Hierarchy
```
MainWindow
├── QTabWidget (5 tabs always loaded)
│   ├── PromptsTab
│   │   ├── Multiple QThreads
│   │   ├── Complex signal/slot connections
│   │   └── Persistent widgets
│   ├── TestingTab
│   │   ├── PDF viewer widgets
│   │   └── LLM processing threads
│   ├── RefinementTab
│   │   ├── Text editors
│   │   └── Comparison widgets
│   ├── PDFProcessingTab
│   │   ├── File lists
│   │   └── Conversion threads
│   └── AnalysisTab
│       ├── File selectors
│       ├── Summary threads
│       └── Integration threads
└── DebugDashboard (if enabled)
    └── Additional monitoring widgets
```

**Problems:**
- All tabs loaded at startup
- Multiple threads can run concurrently
- Complex parent-child relationships
- Widgets persist even when not in use
- Signal/slot connections accumulate

### Memory Leak Patterns

From the debug output, we see:
1. **Focus Chain Issues**: Widgets repeatedly added/removed from focus chains
2. **Accessibility Cache**: Multiple deletions of invalid interfaces
3. **Widget Lifecycle**: Show/hide operations creating dangling references
4. **Library Unloading**: Qt plugins being "faked" unloaded

## Simplified Architecture

### Linear Stage-Based Design
```
MainWindow
├── ProgressSidebar (lightweight)
├── ContentArea (single active widget)
│   └── [Current Stage Widget Only]
└── NavigationBar (simple prev/next)
```

**Stage Loading Pattern:**
```python
# Only one stage widget exists at a time
Stage1 -> Cleanup -> Stage2 -> Cleanup -> Stage3
   ↓                    ↓                    ↓
[Created]          [Destroyed]          [Created]
```

### Memory-Efficient Patterns

#### 1. Single Thread Management
```python
class StageManager:
    def __init__(self):
        self.current_thread = None
        self.current_widget = None
    
    def transition_to_stage(self, stage_class):
        # 1. Stop current operations
        if self.current_thread:
            self.current_thread.stop()
            self.current_thread.wait()
            self.current_thread.deleteLater()
        
        # 2. Clean up current widget
        if self.current_widget:
            self.current_widget.cleanup()
            self.current_widget.deleteLater()
        
        # 3. Process events to ensure cleanup
        QApplication.processEvents()
        
        # 4. Create new stage
        self.current_widget = stage_class()
        self.content_area.layout().addWidget(self.current_widget)
```

#### 2. Resource Pooling
```python
class ResourcePool:
    """Reuse expensive objects instead of creating/destroying"""
    def __init__(self):
        self.llm_provider = None
        self.token_counter = None
    
    def get_llm_provider(self):
        if not self.llm_provider:
            self.llm_provider = create_provider("auto")
        return self.llm_provider
    
    def cleanup(self):
        # Proper cleanup on app exit
        if self.llm_provider:
            self.llm_provider.cleanup()
```

#### 3. Controlled Signal/Slot Connections
```python
class BaseStageWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.connections = []
    
    def safe_connect(self, signal, slot):
        """Track connections for cleanup"""
        signal.connect(slot)
        self.connections.append((signal, slot))
    
    def cleanup(self):
        """Disconnect all signals"""
        for signal, slot in self.connections:
            try:
                signal.disconnect(slot)
            except:
                pass
        self.connections.clear()
```

## Widget Lifecycle Improvements

### Current Problem Pattern
```
Tab1 Active -> Tab2 Click -> Tab1 Hidden (but alive) -> Tab2 Active
                                    ↓
                            Memory still allocated
                            Signals still connected
                            Threads may still run
```

### Simplified Pattern
```
Stage1 Active -> Next Click -> Stage1 Destroyed -> Stage2 Created -> Stage2 Active
                                    ↓                     ↓
                            Memory freed          Fresh start
                            Signals cleaned       No legacy connections
                            Threads stopped       Single thread only
```

## Thread Safety Improvements

### Current Issues
- Multiple QThreads running simultaneously
- Complex signal routing between threads
- Potential race conditions
- Difficult to track thread lifecycle

### Simplified Approach
```python
class SingleThreadedProcessor:
    def __init__(self):
        self.worker = None
        self.queue = []
    
    def process_item(self, item):
        if self.worker and self.worker.isRunning():
            # Queue for later
            self.queue.append(item)
        else:
            # Start processing
            self.worker = ProcessorThread(item)
            self.worker.finished.connect(self._on_finished)
            self.worker.start()
    
    def _on_finished(self):
        self.worker.deleteLater()
        self.worker = None
        
        # Process next in queue
        if self.queue:
            next_item = self.queue.pop(0)
            self.process_item(next_item)
```

## Benefits Summary

### Memory Management
- **Current**: ~500MB+ with all tabs loaded
- **Simplified**: ~100MB base + current stage only

### Thread Count
- **Current**: Up to 5+ concurrent threads
- **Simplified**: Maximum 1 worker thread

### Widget Count
- **Current**: 100+ persistent widgets
- **Simplified**: 10-20 widgets at any time

### Signal Connections
- **Current**: Accumulate over session
- **Simplified**: Cleaned between stages

### Crash Recovery
- **Current**: Loss of all progress
- **Simplified**: Resume from last saved stage