"""
Main application module for the Forensic Psych Report Drafter.
Brings together all UI components and implements the main window functionality.
"""

import os
import sys

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
from pathlib import Path

# Now we can safely import PySide6
from PySide6.QtCore import QCoreApplication, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# Additional plugin path setting using QCoreApplication
if (
    sys.platform == "darwin"
    and "possible_plugin_paths" in locals()
    and possible_plugin_paths
):
    QCoreApplication.setLibraryPaths(possible_plugin_paths)

# Import configuration settings
from config import APP_TITLE, APP_VERSION, setup_environment_variables

# Import utility modules
from llm_utils import LLMClientFactory, cached_count_tokens
from ui.analysis_tab import AnalysisTab
from ui.pdf_processing_tab import PDFProcessingTab

# Import UI tab modules
from ui.prompts_tab import PromptsTab
from ui.refinement_tab import RefinementTab
from ui.testing_tab import TestingTab


class ForensicReportDrafterApp(QMainWindow):
    """
    Main application window for the Forensic Psych Report Drafter.
    Provides a tabbed interface for various functionality.
    """

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

    def check_api_key(self, provider="auto"):
        """Check if the API key is valid by making a test request."""
        try:
            # Create client with auto provider selection first
            client = LLMClientFactory.create_client(provider=provider)

            # Simple test with token counting (minimal API impact)
            response = cached_count_tokens(client, text="Test connection")

            # Check response
            if response.get("success", False):
                provider = getattr(client, "provider", "auto")
                self.status_bar.showMessage(
                    f"{provider.capitalize()} API key found. Ready to use.", 5000
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


def main():
    """Main function to start the application."""
    app = QApplication(sys.argv)
    main_window = ForensicReportDrafterApp()
    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
