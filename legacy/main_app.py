"""
Main application module for the Forensic Psych Report Drafter.
Brings together all UI components and implements the main window functionality.
"""

import os
import sys
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QStatusBar,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import QSize

# Import configuration settings
from config import APP_TITLE, APP_VERSION, setup_environment_variables

# Import UI tab modules
from ui.prompts_tab import PromptsTab
from ui.testing_tab import TestingTab
from ui.refinement_tab import RefinementTab

# Import utility modules
from llm_utils import LLMClient


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
        
        # Add tabs to tab widget
        self.tab_widget.addTab(self.prompts_tab, "Template Generation")
        self.tab_widget.addTab(self.testing_tab, "PDF Analysis")
        self.tab_widget.addTab(self.refinement_tab, "Report Refinement")
        
        # Add tab widget to layout
        self.central_layout.addWidget(self.tab_widget)
    
    def check_api_key(self):
        """Check if the Anthropic API key is available."""
        try:
            # Create a temporary client to check API key
            LLMClient()
            self.status_bar.showMessage("API key found. Ready to use.", 5000)
        except ValueError as e:
            QMessageBox.critical(
                self,
                "API Key Error",
                f"Error with Anthropic API key: {str(e)}\n\n"
                "Please set the ANTHROPIC_API_KEY environment variable.",
            )
            self.status_bar.showMessage("API key not found. Set ANTHROPIC_API_KEY.", 0)
    
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
