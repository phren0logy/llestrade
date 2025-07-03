"""
Global exception handler with crash reporting for the Forensic Psych Report Drafter.
Captures uncaught exceptions and generates detailed crash reports.
"""

import sys
import traceback
import logging
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import QMessageBox, QApplication
from PySide6.QtCore import QObject, Signal, QMetaObject, Qt, Q_ARG


class GlobalExceptionHandler(QObject):
    """Global exception handler with crash reporting."""
    
    crash_occurred = Signal(str)  # Signal with crash file path
    show_error_dialog = Signal(str, str, str)  # exc_type, exc_value, crash_file
    
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
            # Use signal to show dialog on main thread
            self.show_error_dialog.emit(
                exc_type.__name__, 
                str(exc_value), 
                str(crash_file)
            )
            
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
        
    def show_crash_dialog_on_main_thread(self, exc_type_name: str, exc_value: str, crash_file: str):
        """Show user-friendly crash dialog on main thread.
        
        This method should be connected to the show_error_dialog signal
        and will be called on the main thread via Qt's signal/slot mechanism.
        """
        QMessageBox.critical(
            None,
            "Application Error",
            f"An unexpected error occurred:\n\n"
            f"{exc_type_name}: {exc_value}\n\n"
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