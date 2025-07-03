#!/usr/bin/env python3
"""
Test script to verify the enhanced worker thread functionality.
Tests base worker thread features, error handling, and retry logic.
"""

import sys
import time
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QTextEdit, QLabel
from PySide6.QtCore import Signal, Slot

from src.config.logging_config import ApplicationLogger
from ui.workers.base_worker_thread import BaseWorkerThread


class TestWorker(BaseWorkerThread):
    """Test worker that demonstrates enhanced features."""
    
    result_signal = Signal(str)
    
    def __init__(self, test_type="normal", parent=None):
        super().__init__(parent, operation_name=f"TestWorker_{test_type}")
        self.test_type = test_type
        
    def run(self):
        """Run the test operation."""
        super().run()
        
        try:
            if self.test_type == "normal":
                self._test_normal_operation()
            elif self.test_type == "error":
                self._test_error_handling()
            elif self.test_type == "retry":
                self._test_retry_logic()
            elif self.test_type == "cancel":
                self._test_cancellation()
            else:
                raise ValueError(f"Unknown test type: {self.test_type}")
                
        except Exception as e:
            self.handle_error(e, {"test_type": self.test_type})
        finally:
            self.cleanup()
            
    def _test_normal_operation(self):
        """Test normal operation with progress updates."""
        self.emit_progress(0, "Starting normal operation")
        
        for i in range(5):
            if self.is_cancelled():
                self.emit_warning("Operation cancelled by user")
                return
                
            time.sleep(0.5)
            progress = (i + 1) * 20
            self.emit_progress(progress, f"Processing step {i + 1}/5")
            self.emit_debug(f"Debug: Completed step {i + 1}")
            
        self.result_signal.emit("Normal operation completed successfully!")
        
    def _test_error_handling(self):
        """Test error handling."""
        self.emit_progress(25, "Testing error handling")
        time.sleep(0.5)
        
        # Simulate an error
        raise RuntimeError("This is a test error to demonstrate error handling")
        
    def _test_retry_logic(self):
        """Test retry logic."""
        self.emit_progress(0, "Testing retry logic")
        
        def flaky_operation():
            """Simulates an operation that fails twice then succeeds."""
            if not hasattr(self, '_retry_count'):
                self._retry_count = 0
            self._retry_count += 1
            
            if self._retry_count < 3:
                raise ConnectionError(f"Simulated connection error (attempt {self._retry_count})")
            
            return "Success after retries!"
            
        # Use retry logic
        result = self.retry_operation(flaky_operation)
        self.result_signal.emit(f"Retry test result: {result}")
        
    def _test_cancellation(self):
        """Test cancellation handling."""
        self.emit_progress(0, "Testing cancellation - cancel within 3 seconds!")
        
        for i in range(30):  # 3 seconds
            if self.is_cancelled():
                self.emit_warning("Operation cancelled successfully")
                self.result_signal.emit("Cancellation test passed!")
                return
                
            time.sleep(0.1)
            self.emit_progress(i * 3, f"Waiting for cancellation... {i/10:.1f}s")
            
        self.result_signal.emit("Cancellation test failed - operation completed without cancellation")


class TestWindow(QWidget):
    """Test window for worker thread testing."""
    
    def __init__(self):
        super().__init__()
        self.current_worker = None
        self.init_ui()
        
    def init_ui(self):
        """Initialize the test UI."""
        self.setWindowTitle("Worker Thread Enhancement Test")
        self.setMinimumSize(800, 600)
        
        layout = QVBoxLayout()
        
        # Info label
        info_label = QLabel("Test the enhanced worker thread features:")
        layout.addWidget(info_label)
        
        # Test buttons
        self.normal_btn = QPushButton("Test Normal Operation")
        self.normal_btn.clicked.connect(lambda: self.run_test("normal"))
        layout.addWidget(self.normal_btn)
        
        self.error_btn = QPushButton("Test Error Handling")
        self.error_btn.clicked.connect(lambda: self.run_test("error"))
        layout.addWidget(self.error_btn)
        
        self.retry_btn = QPushButton("Test Retry Logic")
        self.retry_btn.clicked.connect(lambda: self.run_test("retry"))
        layout.addWidget(self.retry_btn)
        
        self.cancel_btn = QPushButton("Test Cancellation")
        self.cancel_btn.clicked.connect(lambda: self.run_test("cancel"))
        layout.addWidget(self.cancel_btn)
        
        self.stop_btn = QPushButton("Stop Current Operation")
        self.stop_btn.clicked.connect(self.stop_worker)
        self.stop_btn.setEnabled(False)
        layout.addWidget(self.stop_btn)
        
        # Output display
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)
        
        self.setLayout(layout)
        
    def run_test(self, test_type):
        """Run a specific test."""
        if self.current_worker and self.current_worker.isRunning():
            self.output.append("⚠️ Another test is already running!")
            return
            
        self.output.append(f"\n{'='*50}")
        self.output.append(f"Starting {test_type} test...")
        
        # Create and configure worker
        self.current_worker = TestWorker(test_type)
        
        # Connect signals
        self.current_worker.progress_signal.connect(self.on_progress)
        self.current_worker.error_signal.connect(self.on_error)
        self.current_worker.warning_signal.connect(self.on_warning)
        self.current_worker.debug_signal.connect(self.on_debug)
        self.current_worker.status_signal.connect(self.on_status)
        self.current_worker.result_signal.connect(self.on_result)
        self.current_worker.finished.connect(self.on_finished)
        
        # Enable/disable buttons
        self.stop_btn.setEnabled(True)
        self.set_test_buttons_enabled(False)
        
        # Start worker
        self.current_worker.start()
        
    def stop_worker(self):
        """Stop the current worker."""
        if self.current_worker:
            self.output.append("🛑 Requesting cancellation...")
            self.current_worker.cancel()
            
    @Slot(int, str)
    def on_progress(self, progress, message):
        """Handle progress updates."""
        self.output.append(f"📊 Progress: {progress}% - {message}")
        
    @Slot(str, dict)
    def on_error(self, message, details):
        """Handle error signals."""
        self.output.append(f"❌ ERROR: {message}")
        self.output.append(f"   Details: Operation={details.get('operation_id', 'unknown')}")
        
    @Slot(str)
    def on_warning(self, message):
        """Handle warning signals."""
        self.output.append(f"⚠️ WARNING: {message}")
        
    @Slot(str)
    def on_debug(self, message):
        """Handle debug signals."""
        self.output.append(f"🔍 DEBUG: {message}")
        
    @Slot(dict)
    def on_status(self, status):
        """Handle status updates."""
        self.output.append(f"📋 Status: {status.get('status')} (elapsed: {status.get('elapsed_time', 0):.2f}s)")
        
    @Slot(str)
    def on_result(self, result):
        """Handle result signals."""
        self.output.append(f"✅ RESULT: {result}")
        
    @Slot()
    def on_finished(self):
        """Handle worker finished."""
        self.output.append("🏁 Worker finished")
        self.stop_btn.setEnabled(False)
        self.set_test_buttons_enabled(True)
        
    def set_test_buttons_enabled(self, enabled):
        """Enable/disable test buttons."""
        self.normal_btn.setEnabled(enabled)
        self.error_btn.setEnabled(enabled)
        self.retry_btn.setEnabled(enabled)
        self.cancel_btn.setEnabled(enabled)


def main():
    """Main test function."""
    # Setup logging
    logger_config = ApplicationLogger()
    logger_config.setup(debug="--debug" in sys.argv)
    
    logger = logging.getLogger(__name__)
    logger.info("Starting worker thread enhancement tests")
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Worker Thread Test")
    
    # Create and show test window
    window = TestWindow()
    window.show()
    
    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    print("Worker Thread Enhancement Test")
    print("This tests the new base worker thread features including:")
    print("- Progress tracking with unique operation IDs")
    print("- Enhanced error handling with context")
    print("- Retry logic with exponential backoff")
    print("- Proper cancellation support")
    print()
    
    main()