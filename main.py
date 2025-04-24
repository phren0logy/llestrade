"""
Main application module for the Forensic Psych Report Drafter.
Brings together all UI components and implements the main window functionality.
"""

import os
import sys
# macOS Qt plugin fix: set Qt plugin path before loading any Qt modules
try:
    import PyQt6
    plugin_root = os.path.join(os.path.dirname(PyQt6.__file__), "Qt6", "plugins")
    platforms_path = os.path.join(plugin_root, "platforms")
    os.environ["QT_PLUGIN_PATH"] = plugin_root
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platforms_path
    from PyQt6.QtCore import QCoreApplication
    # include both plugin root and platforms directory for Qt plugin loading
    QCoreApplication.setLibraryPaths([plugin_root, platforms_path])
except Exception:
    pass

import logging
import traceback
from pathlib import Path

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# Import configuration settings
from config import APP_TITLE, APP_VERSION, setup_environment_variables

# Import utility modules
from llm_utils import LLMClientFactory, cached_count_tokens

# Import UI tab modules
from ui.prompts_tab import PromptsTab
from ui.refinement_tab import RefinementTab
from ui.testing_tab import TestingTab
from ui.pdf_processing_tab import PDFProcessingTab
from ui.analysis_tab import AnalysisTab


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
                self.status_bar.showMessage(f"{provider.capitalize()} API key found. Ready to use.", 5000)
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
