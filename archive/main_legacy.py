"""
Main application module for the Forensic Psych Report Drafter.
Brings together all UI components and implements the main window functionality.
"""

import os
import sys
import faulthandler

# Enable faulthandler to get Python stack trace on segfault
faulthandler.enable()

# Configure clean startup before other imports
from src.config.startup_config import clean_startup
clean_startup()

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv() # Load default .env file

# macOS Qt plugin fix: set Qt plugin path before loading any Qt modules
# This MUST be done before importing ANY PySide6 modules
if sys.platform == "darwin":  # macOS specific fix
    # Try both venv and system paths
    possible_plugin_paths = []

    # Add potential PySide6 plugin paths
    try:
        import site

        for site_dir in site.getsitepackages():
            qt_path = os.path.join(site_dir, "PySide6", "Qt", "plugins")
            if os.path.exists(qt_path):
                possible_plugin_paths.append(qt_path)
    except ImportError:
        pass

    # Check if we're in a virtual environment
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        venv_path = os.path.join(
            sys.prefix,
            "lib",
            "python" + sys.version[:3],
            "site-packages",
            "PySide6",
            "Qt",
            "plugins",
        )
        if os.path.exists(venv_path):
            possible_plugin_paths.append(venv_path)

    # Set environment variables if we found valid paths
    if possible_plugin_paths:
        os.environ["QT_PLUGIN_PATH"] = os.pathsep.join(possible_plugin_paths)
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.pathsep.join(
            [
                os.path.join(p, "platforms")
                for p in possible_plugin_paths
                if os.path.exists(os.path.join(p, "platforms"))
            ]
        )

import logging
import traceback
import time
from pathlib import Path
from typing import Optional

# Import our new logging and exception handling modules
from src.config.logging_config import ApplicationLogger
from src.core.exception_handler import GlobalExceptionHandler

# Now we can safely import PySide6
from PySide6.QtCore import QCoreApplication, QSize, QUrl, Qt, Signal
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QDockWidget,
)

# Additional plugin path setting using QCoreApplication
if (
    sys.platform == "darwin"
    and "possible_plugin_paths" in locals()
    and possible_plugin_paths
):
    QCoreApplication.setLibraryPaths(possible_plugin_paths)

# Import configuration settings
from src.config.config import APP_TITLE, APP_VERSION, setup_environment_variables

# Import utility modules
from src.common.llm import create_provider
from src.common.llm.tokens import TokenCounter
from src.legacy.ui.analysis_tab import AnalysisTab
from src.legacy.ui.pdf_processing_tab import PDFProcessingTab

# Import UI tab modules
from src.legacy.ui.prompts_tab import PromptsTab
from src.legacy.ui.refinement_tab import RefinementTab
from src.legacy.ui.testing_tab import TestingTab

# Import debug dashboard if running in debug mode
from src.legacy.ui.debug_dashboard import DebugDashboard


class ForensicReportDrafterApp(QMainWindow):
    """
    Main application window for the Forensic Psych Report Drafter.
    Provides a tabbed interface for various functionality.
    """
    
    # Signal to track worker operations
    worker_status_signal = Signal(dict)

    def __init__(self):
        """Initialize the main application window."""
        super().__init__()

        # Setup environment variables
        setup_environment_variables()

        # Setup the main window
        self.setWindowTitle(f"{APP_TITLE} - v{APP_VERSION}")
        self.setMinimumSize(1200, 800)

        # Create status bar
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        # Setup the UI
        self.setup_ui()

        # Check API key availability
        self.check_api_key()

    def setup_ui(self):
        """Set up the main application UI."""
        # Create central widget and layout
        self.central_widget = QWidget()
        self.central_layout = QVBoxLayout(self.central_widget)
        self.setCentralWidget(self.central_widget)

        # Create tab widget
        self.tab_widget = QTabWidget()

        # Create tabs
        self.prompts_tab = PromptsTab(self, self.status_bar)
        self.testing_tab = TestingTab(self, self.status_bar)
        self.refinement_tab = RefinementTab(self, self.status_bar)
        self.pdf_processing_tab = PDFProcessingTab(self, self.status_bar)
        self.analysis_tab = AnalysisTab(self, self.status_bar)

        # Add tabs to tab widget
        self.tab_widget.addTab(self.prompts_tab, "Prompts from Template")
        self.tab_widget.addTab(self.testing_tab, "Apply Prompt to PDF")
        self.tab_widget.addTab(self.refinement_tab, "Report Refinement")
        self.tab_widget.addTab(self.pdf_processing_tab, "PDF Processing")
        self.tab_widget.addTab(self.analysis_tab, "Analysis & Integration")

        # Add tab widget to layout
        self.central_layout.addWidget(self.tab_widget)

    def emit_worker_status(self, status_dict):
        """Emit worker status to debug dashboard."""
        self.worker_status_signal.emit(status_dict)

    def check_api_key(self, provider="auto"):
        """Check if the API key is valid by making a test request."""
        try:
            # Create provider with auto provider selection first
            provider_instance = create_provider(provider=provider)

            # Simple test with token counting (minimal API impact)
            response = TokenCounter.count(text="Test connection", provider=provider)

            # Check response
            if response.get("success", False):
                provider_name = getattr(provider_instance, "provider_name", provider)
                self.status_bar.showMessage(
                    f"{provider_name.capitalize()} API key found. Ready to use.", 5000
                )
            else:
                error = response.get("error", "Unknown error")
                QMessageBox.warning(
                    self,
                    "API Connection Issue",
                    f"API connection test failed: {error}\n\n"
                    "Please check your API keys and network connectivity.",
                )
                self.status_bar.showMessage("API connection test failed.", 0)
        except Exception as e:
            QMessageBox.critical(
                self,
                "API Key Error",
                f"Error with API keys: {str(e)}\n\n"
                "Please set the ANTHROPIC_API_KEY or GOOGLE_API_KEY environment variable.",
            )
            self.status_bar.showMessage("API key not found. Please set up API keys.", 0)

    def closeEvent(self, event):
        """Handle the window close event."""
        # Display a confirmation dialog
        reply = QMessageBox.question(
            self,
            "Confirm Exit",
            "Are you sure you want to exit the application?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # If the user confirmed, accept the event
            event.accept()
        else:
            # If the user canceled, ignore the event
            event.ignore()


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
    """Main function to start the application."""
    # Setup logging first
    logger_config = ApplicationLogger()
    logger_config.setup(debug="--debug" in sys.argv or os.getenv("DEBUG") == "true")
    
    logger = logging.getLogger(__name__)
    logger.info("Starting Forensic Report Drafter")
    
    # Check for recent crashes
    crash_dir = Path.home() / ".forensic_report_drafter" / "crashes"
    recent_crash = check_for_crashes(crash_dir)
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Forensic Report Drafter")
    
    # Install global exception handler
    exception_handler = GlobalExceptionHandler(crash_dir)
    exception_handler.install()
    
    # Connect the signal to show error dialogs on main thread
    exception_handler.show_error_dialog.connect(
        exception_handler.show_crash_dialog_on_main_thread,
        Qt.ConnectionType.QueuedConnection  # Ensure it runs on main thread
    )
    
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
        
        # Delete the crash file after showing the dialog (whether Yes or No)
        try:
            recent_crash.unlink()
            logger.info(f"Deleted crash report: {recent_crash}")
        except Exception as e:
            logger.warning(f"Could not delete crash report {recent_crash}: {e}")
    
    # Create main window
    main_window = ForensicReportDrafterApp()
    
    # Add debug dashboard if in debug mode
    if "--debug" in sys.argv or os.getenv("DEBUG") == "true":
        debug_dock = QDockWidget("Debug Dashboard", main_window)
        debug_dashboard = DebugDashboard(main_window)
        debug_dock.setWidget(debug_dashboard)
        main_window.addDockWidget(Qt.BottomDockWidgetArea, debug_dock)
        
        # Connect worker signals to debug dashboard
        main_window.worker_status_signal.connect(debug_dashboard.register_operation)
        
        logger.info("Debug dashboard enabled")
    
    main_window.show()
    
    # Run application
    exit_code = app.exec()
    
    # Cleanup
    exception_handler.uninstall()
    logger.info(f"Application exiting with code {exit_code}")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
