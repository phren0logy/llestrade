#!/usr/bin/env python3
"""
Test script to verify the debug dashboard functionality.
Tests logging capture, system monitoring, and operation tracking.
"""

import sys
import time
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, QTimer

from src.config.logging_config import ApplicationLogger
from ui.debug_dashboard import DebugDashboard
from ui.workers.base_worker_thread import BaseWorkerThread


class TestWorker(BaseWorkerThread):
    """Test worker that simulates various operations."""
    
    def __init__(self, test_type="normal", parent=None):
        super().__init__(parent, operation_name=f"TestOperation_{test_type}")
        self.test_type = test_type
        
    def run(self):
        """Run the test operation."""
        super().run()
        
        try:
            self.logger.info(f"Starting {self.test_type} test operation")
            
            if self.test_type == "normal":
                # Simulate normal operation
                for i in range(5):
                    if self.is_cancelled():
                        self.logger.warning("Operation cancelled")
                        return
                    time.sleep(1)
                    self.emit_progress(i * 20, f"Processing step {i+1}/5")
                    self.logger.debug(f"Completed step {i+1}")
                self.logger.info("Normal operation completed successfully")
                
            elif self.test_type == "error":
                # Simulate error
                time.sleep(1)
                raise RuntimeError("Simulated error for testing")
                
            elif self.test_type == "long":
                # Simulate long operation
                for i in range(20):
                    if self.is_cancelled():
                        return
                    time.sleep(0.5)
                    self.emit_progress(i * 5, f"Long operation: {i+1}/20")
                    
        except Exception as e:
            self.handle_error(e, {"test_type": self.test_type})
        finally:
            self.cleanup()


class TestMainWindow(QMainWindow):
    """Test main window with debug dashboard."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Debug Dashboard Test")
        self.setMinimumSize(1200, 800)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Test buttons
        self.normal_btn = QPushButton("Test Normal Operation")
        self.normal_btn.clicked.connect(lambda: self.run_test("normal"))
        layout.addWidget(self.normal_btn)
        
        self.error_btn = QPushButton("Test Error Operation")
        self.error_btn.clicked.connect(lambda: self.run_test("error"))
        layout.addWidget(self.error_btn)
        
        self.long_btn = QPushButton("Test Long Operation")
        self.long_btn.clicked.connect(lambda: self.run_test("long"))
        layout.addWidget(self.long_btn)
        
        self.log_btn = QPushButton("Generate Test Logs")
        self.log_btn.clicked.connect(self.generate_test_logs)
        layout.addWidget(self.log_btn)
        
        # Add debug dashboard as dock
        from PySide6.QtWidgets import QDockWidget
        debug_dock = QDockWidget("Debug Dashboard", self)
        self.debug_dashboard = DebugDashboard(self)
        debug_dock.setWidget(self.debug_dashboard)
        self.addDockWidget(Qt.BottomDockWidgetArea, debug_dock)
        
        self.current_worker = None
        
    def run_test(self, test_type):
        """Run a test worker operation."""
        if self.current_worker and self.current_worker.isRunning():
            logging.warning("Another test is already running")
            return
            
        self.current_worker = TestWorker(test_type)
        
        # Connect status signal to debug dashboard
        self.current_worker.status_signal.connect(self.debug_dashboard.register_operation)
        
        # Start worker
        self.current_worker.start()
        
    def generate_test_logs(self):
        """Generate various test log messages."""
        logger = logging.getLogger(__name__)
        
        logger.debug("This is a DEBUG message")
        logger.info("This is an INFO message")
        logger.warning("This is a WARNING message")
        logger.error("This is an ERROR message")
        
        # Test different loggers
        llm_logger = logging.getLogger("llm.providers")
        llm_logger.info("LLM provider initialized")
        llm_logger.debug("LLM debug information")
        
        worker_logger = logging.getLogger("ui.workers")
        worker_logger.info("Worker thread started")
        worker_logger.warning("Worker thread warning")
        
        # Generate some rapid logs
        QTimer.singleShot(100, lambda: logger.info("Delayed log message 1"))
        QTimer.singleShot(200, lambda: logger.info("Delayed log message 2"))
        QTimer.singleShot(300, lambda: logger.info("Delayed log message 3"))


def main():
    """Main test function."""
    # Setup logging
    logger_config = ApplicationLogger()
    logger_config.setup(debug=True)
    
    logger = logging.getLogger(__name__)
    logger.info("Starting debug dashboard test")
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Debug Dashboard Test")
    
    # Create and show test window
    window = TestMainWindow()
    window.show()
    
    # Generate initial logs
    logger.info("Test window created and shown")
    logger.debug("Debug dashboard should be visible at the bottom")
    
    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    print("Debug Dashboard Test")
    print("=" * 50)
    print("This tests the debug dashboard functionality including:")
    print("- Real-time log capture")
    print("- System statistics monitoring")
    print("- Operation tracking")
    print("- Export functionality")
    print()
    
    main()