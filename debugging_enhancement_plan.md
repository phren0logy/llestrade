# Debugging & Logging Enhancement Plan

## Implementation Status (as of 2025-07-03)

### ✅ Completed Phases
- **Phase 1: Core Infrastructure** - Centralized logging, crash reporting, and exception handling
- **Phase 2: Worker Thread Enhancements** - Base worker class with retry logic and enhanced error handling
- **Phase 3: Debug Dashboard** - Real-time monitoring and debugging UI with system stats and operation tracking

### 🔄 Remaining Phases
- **Phase 4: Provider-Specific Fixes** - Additional Azure OpenAI optimizations (partially completed)

## Executive Summary

This document outlines a comprehensive plan to improve debugging and logging capabilities in the Forensic Psych Report Drafter application, addressing crashes (particularly with GPT-4.1) and implementing PySide6 best practices.

## Current State Analysis

### Existing Implementation

#### Logging Configuration
- **Basic Setup**: Module-level loggers using `logging.getLogger(__name__)`
- **Startup Config**: `startup_config.py` sets WARNING level by default
- **Environment Variables**: `DEBUG_LLM`, `DEBUG_QT`, `DEBUG` for debug control
- **Issues**: No centralized configuration, no log rotation, inconsistent formatting

#### Error Handling
- **Pattern**: Generic `except Exception as e:` in 43 files
- **Worker Threads**: Basic error_signal emissions without structured context
- **Missing**: No global exception handler, no crash recovery
- **Thread Safety**: Limited QMutex usage, potential race conditions

#### Qt-Specific Features
- **Signals/Slots**: Basic error propagation via signals
- **Memory**: Manual `gc.collect()` calls but no systematic cleanup
- **Debugging**: No Qt-specific debugging tools utilized

### Key Issues Causing Crashes

1. **No Crash Dumps**: When the app crashes, no automatic crash report is generated
2. **Limited Error Context**: Exceptions don't capture model state, token counts, or request details
3. **No Retry Logic**: Network/API failures aren't automatically retried
4. **Thread Safety**: Worker threads may have race conditions during concurrent operations
5. **Memory Management**: Large document processing lacks proper cleanup mechanisms

## Proposed Enhancements

### 1. Centralized Logging System

Create `logging_config.py`:

```python
import logging
import logging.handlers
import sys
from pathlib import Path
from datetime import datetime

class ApplicationLogger:
    """Centralized logging configuration for the application."""
    
    def __init__(self, app_name="forensic_report_drafter"):
        self.app_name = app_name
        self.log_dir = Path.home() / f".{app_name}" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
    def setup(self, debug=False):
        """Configure application-wide logging."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG if debug else logging.INFO)
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / f"{self.app_name}.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO if not debug else logging.DEBUG)
        
        # Formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - '
            '[%(filename)s:%(lineno)d] - %(funcName)s() - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(detailed_formatter)
        
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(simple_formatter)
        
        # Add handlers
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        # Configure specific loggers
        self._configure_module_loggers(debug)
        
        # Add startup message
        root_logger.info(f"Logging initialized - Debug: {debug}, Log dir: {self.log_dir}")
        
    def _configure_module_loggers(self, debug):
        """Configure logging levels for specific modules."""
        module_configs = {
            'llm': logging.DEBUG if debug else logging.INFO,
            'llm.providers': logging.DEBUG if debug else logging.INFO,
            'ui.workers': logging.DEBUG if debug else logging.INFO,
            'app_config': logging.INFO,
            'prompt_manager': logging.INFO,
        }
        
        for module, level in module_configs.items():
            logging.getLogger(module).setLevel(level)
            
        # Suppress noisy libraries
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
```

### 2. Global Exception Handler

Create `exception_handler.py`:

```python
import sys
import traceback
import logging
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import QMessageBox, QApplication
from PySide6.QtCore import QObject, Signal

class GlobalExceptionHandler(QObject):
    """Global exception handler with crash reporting."""
    
    crash_occurred = Signal(str)  # Signal with crash file path
    
    def __init__(self, crash_dir: Path = None):
        super().__init__()
        self.crash_dir = crash_dir or Path.home() / ".forensic_report_drafter" / "crashes"
        self.crash_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        self._original_hook = sys.excepthook
        
    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """Handle uncaught exceptions globally."""
        # Ignore keyboard interrupts
        if issubclass(exc_type, KeyboardInterrupt):
            self._original_hook(exc_type, exc_value, exc_traceback)
            return
            
        # Log the exception
        self.logger.critical(
            "Uncaught exception occurred",
            exc_info=(exc_type, exc_value, exc_traceback)
        )
        
        # Create crash dump
        crash_file = self._create_crash_dump(exc_type, exc_value, exc_traceback)
        
        # Emit signal for crash handling
        self.crash_occurred.emit(str(crash_file))
        
        # Show user-friendly error dialog if Qt app is running
        if QApplication.instance():
            self._show_crash_dialog(exc_type, exc_value, crash_file)
            
    def _create_crash_dump(self, exc_type, exc_value, exc_traceback):
        """Create a detailed crash dump file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        crash_file = self.crash_dir / f"crash_{timestamp}.txt"
        
        with open(crash_file, 'w', encoding='utf-8') as f:
            f.write(f"Crash Report - {datetime.now()}\n")
            f.write("="*80 + "\n\n")
            
            # Exception details
            f.write("Exception Details:\n")
            f.write(f"Type: {exc_type.__name__}\n")
            f.write(f"Value: {exc_value}\n\n")
            
            # Full traceback
            f.write("Traceback:\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
            f.write("\n")
            
            # System information
            f.write("System Information:\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Platform: {sys.platform}\n")
            
            # Application state (if available)
            if hasattr(sys, '_app_state'):
                f.write("\nApplication State:\n")
                f.write(str(sys._app_state))
                
        return crash_file
        
    def _show_crash_dialog(self, exc_type, exc_value, crash_file):
        """Show user-friendly crash dialog."""
        QMessageBox.critical(
            None,
            "Application Error",
            f"An unexpected error occurred:\n\n"
            f"{exc_type.__name__}: {exc_value}\n\n"
            f"A crash report has been saved to:\n{crash_file}\n\n"
            "Please restart the application and check the logs."
        )
        
    def install(self):
        """Install the global exception handler."""
        sys.excepthook = self.handle_exception
        self.logger.info("Global exception handler installed")
        
    def uninstall(self):
        """Restore original exception handler."""
        sys.excepthook = self._original_hook
```

### 3. Enhanced Worker Thread Base Class

Create `ui/workers/base_worker_thread.py`:

```python
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
import logging
import traceback
import time
import uuid
from typing import Optional, Dict, Any

class BaseWorkerThread(QThread):
    """Enhanced base class for worker threads with robust error handling."""
    
    # Signals
    progress_signal = Signal(int, str)  # progress, message
    error_signal = Signal(str, dict)    # error_message, error_details
    warning_signal = Signal(str)        # warning_message
    debug_signal = Signal(str)          # debug_message
    status_signal = Signal(dict)        # status_dict
    
    def __init__(self, parent=None, operation_name: str = None):
        super().__init__(parent)
        self.operation_name = operation_name or self.__class__.__name__
        self.logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")
        
        # Operation tracking
        self._operation_id = None
        self._start_time = None
        self._is_cancelled = False
        self._mutex = QMutex()
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds
        self.retry_backoff = 2.0  # exponential backoff multiplier
        
    def run(self):
        """Base run method - subclasses should call super().run() first."""
        self._start_time = time.time()
        self._operation_id = f"{self.operation_name}_{uuid.uuid4().hex[:8]}"
        self._is_cancelled = False
        
        self.logger.info(
            f"Starting operation: {self._operation_id}",
            extra={'operation_id': self._operation_id}
        )
        
        try:
            self._emit_status("started")
        except Exception as e:
            self.logger.error(f"Failed to emit start status: {e}")
            
    def cancel(self):
        """Request cancellation of the operation."""
        with QMutexLocker(self._mutex):
            self._is_cancelled = True
        self.logger.info(f"Cancellation requested for {self._operation_id}")
        
    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        with QMutexLocker(self._mutex):
            return self._is_cancelled
            
    def safe_emit(self, signal: Signal, *args):
        """Safely emit a signal with error handling."""
        try:
            if not self.is_cancelled():
                signal.emit(*args)
        except Exception as e:
            self.logger.error(
                f"Error emitting signal {signal}: {e}",
                exc_info=True
            )
            
    def handle_error(self, error: Exception, context: Optional[Dict[str, Any]] = None):
        """Standardized error handling for worker threads."""
        error_details = {
            'type': type(error).__name__,
            'message': str(error),
            'traceback': traceback.format_exc(),
            'operation_id': self._operation_id,
            'operation_name': self.operation_name,
            'elapsed_time': time.time() - self._start_time if self._start_time else 0,
            'context': context or {},
            'timestamp': datetime.now().isoformat()
        }
        
        # Log with full context
        self.logger.error(
            f"Error in {self.operation_name}: {error}",
            extra=error_details,
            exc_info=True
        )
        
        # Emit error signal
        self.safe_emit(self.error_signal, str(error), error_details)
        self._emit_status("error", error_details)
        
    def retry_operation(self, operation, *args, **kwargs):
        """Execute an operation with retry logic."""
        last_error = None
        delay = self.retry_delay
        
        for attempt in range(self.max_retries):
            if self.is_cancelled():
                break
                
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                last_error = e
                self.logger.warning(
                    f"Attempt {attempt + 1}/{self.max_retries} failed: {e}",
                    extra={'operation_id': self._operation_id}
                )
                
                if attempt < self.max_retries - 1:
                    self.safe_emit(
                        self.warning_signal,
                        f"Retrying in {delay}s... (attempt {attempt + 2}/{self.max_retries})"
                    )
                    time.sleep(delay)
                    delay *= self.retry_backoff
                    
        # All retries failed
        raise last_error
        
    def _emit_status(self, status: str, details: Optional[Dict] = None):
        """Emit a status update."""
        status_dict = {
            'status': status,
            'operation_id': self._operation_id,
            'operation_name': self.operation_name,
            'elapsed_time': time.time() - self._start_time if self._start_time else 0,
            'timestamp': datetime.now().isoformat()
        }
        
        if details:
            status_dict.update(details)
            
        self.safe_emit(self.status_signal, status_dict)
        
    def cleanup(self):
        """Cleanup method called when thread finishes."""
        self._emit_status("finished")
        elapsed = time.time() - self._start_time if self._start_time else 0
        self.logger.info(
            f"Operation {self._operation_id} completed in {elapsed:.2f}s",
            extra={'operation_id': self._operation_id, 'elapsed_time': elapsed}
        )
```

### 4. Debug Dashboard

Create `ui/debug_dashboard.py`:

```python
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
                             QPushButton, QTabWidget, QTableWidget, QTableWidgetItem,
                             QCheckBox, QSpinBox, QLabel, QFileDialog)
from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtGui import QTextCursor, QColor
import logging
import psutil
import gc
import json
from datetime import datetime
from pathlib import Path

class QtLogHandler(logging.Handler):
    """Custom log handler that emits to Qt widget."""
    
    def __init__(self, text_widget: QTextEdit):
        super().__init__()
        self.text_widget = text_widget
        self.colors = {
            logging.DEBUG: QColor(128, 128, 128),
            logging.INFO: QColor(0, 0, 0),
            logging.WARNING: QColor(255, 165, 0),
            logging.ERROR: QColor(255, 0, 0),
            logging.CRITICAL: QColor(139, 0, 0)
        }
        
    def emit(self, record):
        """Emit log record to text widget."""
        try:
            msg = self.format(record)
            color = self.colors.get(record.levelno, QColor(0, 0, 0))
            
            # Thread-safe append
            cursor = QTextCursor(self.text_widget.document())
            cursor.movePosition(QTextCursor.End)
            cursor.insertHtml(
                f'<span style="color: {color.name()};">{msg}</span><br>'
            )
            
            # Auto-scroll to bottom
            self.text_widget.verticalScrollBar().setValue(
                self.text_widget.verticalScrollBar().maximum()
            )
        except Exception:
            self.handleError(record)

class DebugDashboard(QWidget):
    """Comprehensive debug dashboard for application monitoring."""
    
    export_requested = Signal(str)  # Export file path
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_operations = {}
        self.setup_ui()
        self.setup_logging()
        self.start_monitoring()
        
    def setup_ui(self):
        """Setup the dashboard UI."""
        layout = QVBoxLayout()
        
        # Tab widget for different debug views
        self.tabs = QTabWidget()
        
        # Logs tab
        self.log_widget = self._create_log_tab()
        self.tabs.addTab(self.log_widget, "Logs")
        
        # System stats tab
        self.stats_widget = self._create_stats_tab()
        self.tabs.addTab(self.stats_widget, "System Stats")
        
        # Active operations tab
        self.operations_widget = self._create_operations_tab()
        self.tabs.addTab(self.operations_widget, "Active Operations")
        
        layout.addWidget(self.tabs)
        
        # Control panel
        control_layout = self._create_control_panel()
        layout.addLayout(control_layout)
        
        self.setLayout(layout)
        self.setMinimumSize(800, 600)
        
    def _create_log_tab(self):
        """Create the logs tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Log viewer
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setMaximumBlockCount(10000)  # Limit log size
        layout.addWidget(self.log_viewer)
        
        # Log controls
        log_controls = QHBoxLayout()
        
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)
        
        self.log_level_spin = QSpinBox()
        self.log_level_spin.setRange(10, 50)  # DEBUG to CRITICAL
        self.log_level_spin.setValue(20)  # INFO
        self.log_level_spin.setSingleStep(10)
        
        log_controls.addWidget(QLabel("Log Level:"))
        log_controls.addWidget(self.log_level_spin)
        log_controls.addWidget(self.auto_scroll)
        log_controls.addStretch()
        
        layout.addLayout(log_controls)
        widget.setLayout(layout)
        return widget
        
    def _create_stats_tab(self):
        """Create the system stats tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Stats table
        self.stats_table = QTableWidget(8, 2)
        self.stats_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.stats_table.horizontalHeader().setStretchLastSection(True)
        
        # Initialize rows
        metrics = [
            "Memory (MB)", "CPU (%)", "Threads", "Open Files",
            "Network Connections", "Disk I/O Read (MB)", 
            "Disk I/O Write (MB)", "Uptime"
        ]
        
        for i, metric in enumerate(metrics):
            self.stats_table.setItem(i, 0, QTableWidgetItem(metric))
            self.stats_table.setItem(i, 1, QTableWidgetItem("--"))
            
        layout.addWidget(self.stats_table)
        widget.setLayout(layout)
        return widget
        
    def _create_operations_tab(self):
        """Create the active operations tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Operations table
        self.operations_table = QTableWidget(0, 4)
        self.operations_table.setHorizontalHeaderLabels([
            "Operation ID", "Name", "Status", "Duration"
        ])
        self.operations_table.horizontalHeader().setStretchLastSection(True)
        
        layout.addWidget(self.operations_table)
        widget.setLayout(layout)
        return widget
        
    def _create_control_panel(self):
        """Create the control panel."""
        layout = QHBoxLayout()
        
        # Clear logs button
        self.clear_btn = QPushButton("Clear Logs")
        self.clear_btn.clicked.connect(self.log_viewer.clear)
        
        # Force GC button
        self.gc_btn = QPushButton("Force GC")
        self.gc_btn.clicked.connect(self._force_gc)
        
        # Export debug info button
        self.export_btn = QPushButton("Export Debug Info")
        self.export_btn.clicked.connect(self._export_debug_info)
        
        # Monitoring interval
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.setValue(5)
        self.interval_spin.setSuffix(" sec")
        self.interval_spin.valueChanged.connect(self._update_monitoring_interval)
        
        layout.addWidget(self.clear_btn)
        layout.addWidget(self.gc_btn)
        layout.addWidget(self.export_btn)
        layout.addStretch()
        layout.addWidget(QLabel("Update Interval:"))
        layout.addWidget(self.interval_spin)
        
        return layout
        
    def setup_logging(self):
        """Setup logging handler to capture logs in UI."""
        self.log_handler = QtLogHandler(self.log_viewer)
        self.log_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        logging.getLogger().addHandler(self.log_handler)
        
    def start_monitoring(self):
        """Start system monitoring timer."""
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self._update_stats)
        self.monitor_timer.start(5000)  # 5 seconds default
        
    @Slot(dict)
    def register_operation(self, status_dict: dict):
        """Register or update an operation."""
        op_id = status_dict.get('operation_id')
        if not op_id:
            return
            
        self.active_operations[op_id] = status_dict
        self._update_operations_table()
        
    def _update_stats(self):
        """Update system statistics."""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            io_counters = process.io_counters()
            
            # Update stats table
            stats = [
                f"{memory_info.rss / 1024 / 1024:.1f}",
                f"{process.cpu_percent(interval=0.1):.1f}",
                str(process.num_threads()),
                str(len(process.open_files())),
                str(len(process.connections())),
                f"{io_counters.read_bytes / 1024 / 1024:.1f}",
                f"{io_counters.write_bytes / 1024 / 1024:.1f}",
                str(datetime.now() - datetime.fromtimestamp(process.create_time()))
            ]
            
            for i, value in enumerate(stats):
                self.stats_table.item(i, 1).setText(value)
                
        except Exception as e:
            logging.error(f"Error updating stats: {e}")
            
    def _update_operations_table(self):
        """Update active operations table."""
        self.operations_table.setRowCount(len(self.active_operations))
        
        for i, (op_id, details) in enumerate(self.active_operations.items()):
            self.operations_table.setItem(i, 0, QTableWidgetItem(op_id))
            self.operations_table.setItem(i, 1, QTableWidgetItem(details.get('operation_name', '')))
            self.operations_table.setItem(i, 2, QTableWidgetItem(details.get('status', '')))
            self.operations_table.setItem(i, 3, QTableWidgetItem(
                f"{details.get('elapsed_time', 0):.2f}s"
            ))
            
    def _force_gc(self):
        """Force garbage collection."""
        collected = gc.collect()
        logging.info(f"Garbage collection: {collected} objects collected")
        
    def _export_debug_info(self):
        """Export debug information to file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Debug Info", 
            f"debug_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON Files (*.json)"
        )
        
        if file_path:
            debug_info = {
                'timestamp': datetime.now().isoformat(),
                'active_operations': self.active_operations,
                'system_stats': self._get_current_stats(),
                'log_entries': self._get_recent_logs()
            }
            
            with open(file_path, 'w') as f:
                json.dump(debug_info, f, indent=2, default=str)
                
            self.export_requested.emit(file_path)
            
    def _get_current_stats(self):
        """Get current system stats as dict."""
        stats = {}
        for i in range(self.stats_table.rowCount()):
            metric = self.stats_table.item(i, 0).text()
            value = self.stats_table.item(i, 1).text()
            stats[metric] = value
        return stats
        
    def _get_recent_logs(self):
        """Get recent log entries."""
        return self.log_viewer.toPlainText().split('\n')[-100:]  # Last 100 lines
        
    def _update_monitoring_interval(self, value):
        """Update monitoring timer interval."""
        self.monitor_timer.setInterval(value * 1000)
```

### 5. Updated main.py Integration

```python
# Add to main.py after imports

from logging_config import ApplicationLogger
from exception_handler import GlobalExceptionHandler
from ui.debug_dashboard import DebugDashboard

def check_for_crashes(crash_dir: Path) -> Optional[Path]:
    """Check for recent crash files."""
    if not crash_dir.exists():
        return None
        
    crash_files = sorted(crash_dir.glob("crash_*.txt"), 
                        key=lambda p: p.stat().st_mtime, 
                        reverse=True)
    
    if crash_files and crash_files[0].stat().st_mtime > (time.time() - 86400):
        return crash_files[0]
    return None

def main():
    # Setup logging first
    logger_config = ApplicationLogger()
    logger_config.setup(debug="--debug" in sys.argv or os.getenv("DEBUG") == "true")
    
    logger = logging.getLogger(__name__)
    logger.info("Starting Forensic Report Drafter")
    
    # Check for recent crashes
    crash_dir = Path.home() / ".forensic_report_drafter" / "crashes"
    recent_crash = check_for_crashes(crash_dir)
    
    # Qt plugin path setup (existing code)
    if platform.system() == "Darwin":
        qt_plugin_path = os.path.join(os.path.dirname(PySide6.__file__), "Qt", "plugins")
        if os.path.exists(qt_plugin_path):
            os.environ['QT_PLUGIN_PATH'] = qt_plugin_path
            
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Forensic Report Drafter")
    
    # Install global exception handler
    exception_handler = GlobalExceptionHandler(crash_dir)
    exception_handler.install()
    
    # Show crash recovery dialog if needed
    if recent_crash:
        reply = QMessageBox.question(
            None,
            "Previous Crash Detected",
            f"The application crashed previously.\n\n"
            f"Would you like to view the crash report?\n{recent_crash}",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(recent_crash)))
    
    # Create main window
    window = MainWindow()
    
    # Add debug dashboard if in debug mode
    if "--debug" in sys.argv or os.getenv("DEBUG") == "true":
        debug_dock = QDockWidget("Debug Dashboard", window)
        debug_dashboard = DebugDashboard(window)
        debug_dock.setWidget(debug_dashboard)
        window.addDockWidget(Qt.BottomDockWidgetArea, debug_dock)
        
        # Connect worker signals to debug dashboard
        window.worker_status_signal.connect(debug_dashboard.register_operation)
    
    window.show()
    
    # Run application
    exit_code = app.exec()
    
    # Cleanup
    exception_handler.uninstall()
    logger.info(f"Application exiting with code {exit_code}")
    
    sys.exit(exit_code)
```

### 6. GPT-4.1 Specific Enhancements

Update `llm/providers/azure_openai.py`:

```python
# Add to AzureOpenAIProvider class

async def _make_request_with_retry(self, messages, **kwargs):
    """Make API request with enhanced error handling and retry logic."""
    retry_errors = (
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.RateLimitError,
        openai.InternalServerError
    )
    
    for attempt in range(self.max_retries):
        try:
            # Log request details for debugging
            self.logger.debug(
                f"Making request to Azure OpenAI",
                extra={
                    'attempt': attempt + 1,
                    'deployment': self.deployment_name,
                    'model': kwargs.get('model', self.default_model),
                    'messages_count': len(messages),
                    'total_tokens': sum(self.count_tokens(m['content']) for m in messages)
                }
            )
            
            # Set timeout
            kwargs['timeout'] = kwargs.get('timeout', 60.0)
            
            # Make request
            response = await self.client.chat.completions.create(
                messages=messages,
                **kwargs
            )
            
            # Log successful response
            self.logger.info(
                f"Request successful",
                extra={
                    'usage': response.usage.dict() if response.usage else None,
                    'model': response.model,
                    'finish_reason': response.choices[0].finish_reason
                }
            )
            
            return response
            
        except retry_errors as e:
            self.logger.warning(
                f"Retryable error on attempt {attempt + 1}: {e}",
                extra={'error_type': type(e).__name__}
            )
            
            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (self.retry_backoff ** attempt)
                await asyncio.sleep(delay)
            else:
                # Final attempt failed
                self.logger.error(
                    f"All retry attempts failed",
                    extra={'final_error': str(e)}
                )
                raise
                
        except Exception as e:
            # Non-retryable error
            self.logger.error(
                f"Non-retryable error: {e}",
                exc_info=True,
                extra={
                    'error_type': type(e).__name__,
                    'deployment': self.deployment_name
                }
            )
            raise
```

## Implementation Timeline

### Phase 1: Core Infrastructure (Week 1) ✅ COMPLETED
1. ✅ Implement `logging_config.py`
2. ✅ Implement `exception_handler.py`
3. ✅ Update `main.py` with crash detection
4. ✅ Test basic logging and exception handling

**Completion Notes:**
- Successfully implemented centralized logging with rotation (10MB max, 5 backups)
- Global exception handler creates detailed crash reports in `~/.forensic_report_drafter/crashes/`
- Main application now checks for recent crashes on startup and offers recovery
- Created comprehensive test script `test_logging_and_exceptions.py`
- Verified integration with existing application startup

### Phase 2: Worker Thread Enhancements (Week 2) ✅ COMPLETED
1. ✅ Implement `base_worker_thread.py`
2. ✅ Update existing worker threads to inherit from new base (partially)
3. ✅ Add retry logic to LLM provider calls
4. ✅ Test thread safety and cancellation

**Completion Notes:**
- Created `base_worker_thread.py` with enhanced error handling, retry logic, and operation tracking
- Updated `llm_summary_thread.py` to inherit from base class with improved logging
- Partially updated `integrated_analysis_thread.py` as demonstration
- Enhanced Azure OpenAI provider with retry logic for transient errors
- Added detailed error logging with context for GPT-4.1 debugging
- Created `test_worker_enhancements.py` to verify functionality
- Remaining worker threads can be migrated gradually as needed

### Phase 3: Debug Dashboard (Week 3) ✅ COMPLETED
1. ✅ Implement `debug_dashboard.py`
2. ✅ Integrate with main window
3. ✅ Connect worker signals to dashboard
4. ✅ Test real-time monitoring

**Completion Notes:**
- Created `ui/debug_dashboard.py` with comprehensive monitoring capabilities
- Integrated as dockable widget in main window when running with `--debug` or `DEBUG=true`
- Real-time log capture with color-coded severity levels
- System statistics monitoring (memory, CPU, threads, I/O)
- Active operation tracking with unique IDs and duration
- Export functionality for debug information (JSON format)
- Created `test_debug_dashboard.py` to verify all functionality
- Thread-safe implementation with proper Qt signal/slot connections

### Phase 4: Provider-Specific Fixes (Week 4) 🔄 PARTIALLY COMPLETED
1. ✅ Enhanced error handling in Azure OpenAI provider
2. ✅ Add request/response logging
3. ⏳ Implement connection pooling
4. ⏳ Test with large documents

**Completed Improvements for GPT-4.1:**
- Added retry logic with exponential backoff for transient errors
- Enhanced error messages with deployment name and endpoint context
- Added helpful hints for common GPT-4.1 configuration issues
- Improved request logging with token counts and timing
- Better error categorization (retryable vs non-retryable)

## Testing Strategy

### Unit Tests
- Test exception handler with various error types
- Test worker thread retry logic
- Test logging configuration

### Integration Tests
- Test crash recovery on startup
- Test debug dashboard with real operations
- Test GPT-4.1 with network interruptions

### Performance Tests
- Monitor memory usage during large document processing
- Measure logging overhead
- Test thread pool efficiency

## Success Metrics

1. **Crash Reduction**: 90% reduction in unexplained crashes
2. **Debug Time**: 50% reduction in time to diagnose issues
3. **Recovery Rate**: 95% successful recovery from transient errors
4. **Performance Impact**: <5% overhead from logging/monitoring

## Maintenance Considerations

1. **Log Rotation**: Automatic cleanup of old logs (>30 days)
2. **Crash Reports**: Privacy-conscious crash reporting
3. **Performance Monitoring**: Regular profiling of debug overhead
4. **Documentation**: Keep debug features documented

This comprehensive plan addresses the current debugging limitations and provides robust tools for diagnosing and preventing crashes, particularly with the GPT-4.1 provider.

## Key Achievements (Phases 1, 2 & 3)

### Improved Debugging Capabilities
- **Centralized Logging**: All logs now go to `~/.forensic_report_drafter/logs/` with automatic rotation
- **Crash Reports**: Automatic crash dumps saved to `~/.forensic_report_drafter/crashes/`
- **Operation Tracking**: Each worker operation has a unique ID for tracing
- **Enhanced Error Context**: Errors include deployment info, token counts, and timing data

### Better Reliability
- **Automatic Retry**: Transient network errors are retried with exponential backoff
- **Graceful Degradation**: Better error messages help users understand and fix issues
- **Thread Safety**: Standardized cancellation and signal emission patterns

### GPT-4.1 Specific Improvements
- **Retry Logic**: Handles timeout, connection, and rate limit errors automatically
- **Better Error Messages**: Clear indication when deployment name is incorrect
- **Request Logging**: Token counts and timing help identify performance issues
- **Context Preservation**: Error logs include all relevant Azure configuration

### Developer Experience
- **Debug Mode**: Run with `--debug` or `DEBUG=true` for detailed logging
- **Test Scripts**: `test_logging_and_exceptions.py`, `test_worker_enhancements.py`, and `test_debug_dashboard.py`
- **Modular Design**: Easy to extend base classes for new functionality
- **Debug Dashboard**: Real-time monitoring UI available in debug mode

### Debug Dashboard Features (Phase 3)
- **Live Log Viewer**: Color-coded logs with adjustable verbosity level
- **System Monitor**: Real-time CPU, memory, thread, and I/O statistics
- **Operation Tracker**: View active operations with unique IDs and durations
- **Export Capability**: Save debug snapshots for offline analysis
- **Dock Widget**: Resizable and movable debug panel in main window