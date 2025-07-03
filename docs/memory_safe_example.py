#!/usr/bin/env python3
"""
Proof of Concept: Memory-Safe Stage Management
Demonstrates the simplified architecture with proper resource cleanup
"""

import sys
import gc
import weakref
from typing import Optional
from PySide6.QtCore import QObject, QThread, Signal, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QLabel, QTextEdit
)


class SafeWorkerThread(QThread):
    """Thread that properly cleans up resources"""
    progress = Signal(str)
    finished = Signal()
    
    def __init__(self):
        super().__init__()
        self._is_running = True
        # Use weak references to avoid circular dependencies
        self._parent_ref = None
        
    def set_parent_ref(self, parent):
        """Store weak reference to parent"""
        self._parent_ref = weakref.ref(parent) if parent else None
        
    def stop(self):
        """Safely stop the thread"""
        self._is_running = False
        
    def run(self):
        """Simulate work with proper cleanup"""
        for i in range(5):
            if not self._is_running:
                break
            self.progress.emit(f"Processing step {i+1}/5")
            self.msleep(500)  # Simulate work
            
        self.finished.emit()


class BaseStage(QWidget):
    """Base class for workflow stages with cleanup"""
    
    def __init__(self, stage_name: str):
        super().__init__()
        self.stage_name = stage_name
        self.worker: Optional[SafeWorkerThread] = None
        self._connections = []
        self.setup_ui()
        
    def setup_ui(self):
        """Create simple UI"""
        layout = QVBoxLayout()
        
        self.label = QLabel(f"Stage: {self.stage_name}")
        layout.addWidget(self.label)
        
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)
        
        self.start_button = QPushButton("Start Processing")
        self.start_button.clicked.connect(self.start_processing)
        layout.addWidget(self.start_button)
        
        self.setLayout(layout)
        
    def start_processing(self):
        """Start worker thread with proper setup"""
        if self.worker and self.worker.isRunning():
            self.output.append("Already processing...")
            return
            
        self.output.append(f"Starting {self.stage_name} processing...")
        
        # Create new worker
        self.worker = SafeWorkerThread()
        self.worker.set_parent_ref(self)
        
        # Connect signals with tracking
        self._connect_tracked(self.worker.progress, self.on_progress)
        self._connect_tracked(self.worker.finished, self.on_finished)
        
        # Start processing
        self.worker.start()
        self.start_button.setEnabled(False)
        
    def _connect_tracked(self, signal, slot):
        """Connect signal and track for cleanup"""
        signal.connect(slot)
        self._connections.append((signal, slot))
        
    def on_progress(self, message):
        """Handle progress updates"""
        self.output.append(message)
        
    def on_finished(self):
        """Handle completion"""
        self.output.append("Processing complete!")
        self.start_button.setEnabled(True)
        
    def cleanup(self):
        """Comprehensive cleanup method"""
        self.output.append(f"Cleaning up {self.stage_name}...")
        
        # 1. Stop worker thread
        if self.worker:
            if self.worker.isRunning():
                self.worker.stop()
                self.worker.wait(1000)  # Wait up to 1 second
                if self.worker.isRunning():
                    self.worker.terminate()  # Force terminate if needed
                    self.worker.wait()
            
            # Delete worker
            self.worker.deleteLater()
            self.worker = None
            
        # 2. Disconnect all tracked signals
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except:
                pass  # Already disconnected
        self._connections.clear()
        
        # 3. Clear UI references
        self.output.clear()
        
        # 4. Schedule deletion
        self.deleteLater()


class MemorySafeMainWindow(QMainWindow):
    """Main window with single-stage architecture"""
    
    def __init__(self):
        super().__init__()
        self.current_stage: Optional[BaseStage] = None
        self.stage_history = []
        self.setup_ui()
        
        # Monitor memory usage
        self.memory_timer = QTimer()
        self.memory_timer.timeout.connect(self.log_memory_usage)
        self.memory_timer.start(2000)  # Every 2 seconds
        
    def setup_ui(self):
        """Create main UI layout"""
        self.setWindowTitle("Memory-Safe Stage Demo")
        self.setMinimumSize(800, 600)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        main_layout = QVBoxLayout(central)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.stage1_btn = QPushButton("Load Stage 1")
        self.stage1_btn.clicked.connect(lambda: self.load_stage("Stage 1"))
        nav_layout.addWidget(self.stage1_btn)
        
        self.stage2_btn = QPushButton("Load Stage 2")
        self.stage2_btn.clicked.connect(lambda: self.load_stage("Stage 2"))
        nav_layout.addWidget(self.stage2_btn)
        
        self.stage3_btn = QPushButton("Load Stage 3")
        self.stage3_btn.clicked.connect(lambda: self.load_stage("Stage 3"))
        nav_layout.addWidget(self.stage3_btn)
        
        self.cleanup_btn = QPushButton("Force Cleanup")
        self.cleanup_btn.clicked.connect(self.force_cleanup)
        nav_layout.addWidget(self.cleanup_btn)
        
        main_layout.addLayout(nav_layout)
        
        # Content area
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        main_layout.addWidget(self.content_area)
        
        # Status bar
        self.status_label = QLabel("Ready")
        main_layout.addWidget(self.status_label)
        
    def load_stage(self, stage_name: str):
        """Load a new stage with proper cleanup"""
        self.status_label.setText(f"Loading {stage_name}...")
        
        # 1. Cleanup current stage
        if self.current_stage:
            self.cleanup_current_stage()
            
        # 2. Force event processing
        QApplication.processEvents()
        
        # 3. Force garbage collection
        gc.collect()
        
        # 4. Create new stage
        self.current_stage = BaseStage(stage_name)
        self.content_layout.addWidget(self.current_stage)
        
        # 5. Track stage history
        self.stage_history.append(stage_name)
        
        self.status_label.setText(f"{stage_name} loaded")
        
    def cleanup_current_stage(self):
        """Safely cleanup current stage"""
        if not self.current_stage:
            return
            
        # Remove from layout
        self.content_layout.removeWidget(self.current_stage)
        
        # Call cleanup
        self.current_stage.cleanup()
        
        # Clear reference
        self.current_stage = None
        
    def force_cleanup(self):
        """Force cleanup and garbage collection"""
        self.cleanup_current_stage()
        gc.collect()
        self.status_label.setText("Forced cleanup complete")
        
    def log_memory_usage(self):
        """Log current memory usage"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        status = f"Memory: {memory_mb:.1f} MB"
        if self.current_stage:
            status += f" | Current: {self.current_stage.stage_name}"
        status += f" | History: {len(self.stage_history)} stages"
        
        self.setWindowTitle(f"Memory-Safe Demo - {status}")
        
    def closeEvent(self, event):
        """Clean shutdown"""
        self.memory_timer.stop()
        self.cleanup_current_stage()
        event.accept()


def main():
    """Run the demo application"""
    app = QApplication(sys.argv)
    
    # Enable garbage collection debugging
    gc.set_debug(gc.DEBUG_LEAK)
    
    window = MemorySafeMainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()