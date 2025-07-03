"""
Debug dashboard for real-time application monitoring and debugging.
Provides logs, system stats, and active operation tracking.
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPlainTextEdit,
                             QPushButton, QTabWidget, QTableWidget, QTableWidgetItem,
                             QCheckBox, QSpinBox, QLabel, QFileDialog, QDockWidget)
from PySide6.QtCore import QTimer, Qt, Signal, Slot, QMutexLocker, QMutex
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
        self.mutex = QMutex()
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
            with QMutexLocker(self.mutex):
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
        self.process = psutil.Process()
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
        self.log_viewer = QPlainTextEdit()
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
        self.log_level_spin.valueChanged.connect(self._update_log_level)
        
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
        
        # Set initial log level
        self.log_handler.setLevel(self.log_level_spin.value())
        
        # Add handler to root logger
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
        
    def _update_log_level(self, value):
        """Update the log handler's level."""
        if hasattr(self, 'log_handler'):
            self.log_handler.setLevel(value)
            
    def _update_stats(self):
        """Update system statistics."""
        try:
            memory_info = self.process.memory_info()
            
            # Try to get IO counters (may not be available on all platforms)
            try:
                io_counters = self.process.io_counters()
                io_read = f"{io_counters.read_bytes / 1024 / 1024:.1f}"
                io_write = f"{io_counters.write_bytes / 1024 / 1024:.1f}"
            except (AttributeError, psutil.AccessDenied):
                io_read = "N/A"
                io_write = "N/A"
            
            # Try to get open files (may require elevated permissions)
            try:
                open_files = len(self.process.open_files())
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                open_files = "N/A"
                
            # Try to get connections
            try:
                connections = len(self.process.connections())
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                connections = "N/A"
            
            # Update stats table
            stats = [
                f"{memory_info.rss / 1024 / 1024:.1f}",
                f"{self.process.cpu_percent(interval=0.1):.1f}",
                str(self.process.num_threads()),
                str(open_files),
                str(connections),
                io_read,
                io_write,
                str(datetime.now() - datetime.fromtimestamp(self.process.create_time()))
            ]
            
            for i, value in enumerate(stats):
                if i < self.stats_table.rowCount():
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
            
            # Color code by status
            status = details.get('status', '').lower()
            if status == 'error':
                for col in range(4):
                    item = self.operations_table.item(i, col)
                    if item:
                        item.setBackground(QColor(255, 200, 200))
            elif status == 'finished':
                for col in range(4):
                    item = self.operations_table.item(i, col)
                    if item:
                        item.setBackground(QColor(200, 255, 200))
                        
            # Remove finished operations after 60 seconds
            if status == 'finished' and details.get('elapsed_time', 0) > 60:
                del self.active_operations[op_id]
                
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
            logging.info(f"Debug info exported to: {file_path}")
            
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
        
    def closeEvent(self, event):
        """Clean up when closing."""
        # Remove log handler from root logger
        if hasattr(self, 'log_handler'):
            logging.getLogger().removeHandler(self.log_handler)
        super().closeEvent(event)