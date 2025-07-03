#!/usr/bin/env python3
"""
Main entry point for the new simplified UI.
"""

import sys
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtCore import Qt, QTimer

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.config.logging_config import setup_logging
from src.config.startup_config import configure_startup_logging
from src.new.core import SecureSettings, ProjectManager, StageManager


class SimplifiedMainWindow(QMainWindow):
    """Main window for the simplified UI."""
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        
        # Core components
        self.settings = SecureSettings()
        self.project_manager = None
        self.stage_manager = StageManager(self)
        
        # Setup UI
        self.setWindowTitle("Forensic Report Drafter")
        self.resize(1200, 800)
        
        # Restore window geometry
        geometry = self.settings.get_window_geometry()
        if geometry:
            self.restoreGeometry(geometry)
        
        # Create basic UI structure
        self._create_ui()
        
        # Show welcome or load recent project
        QTimer.singleShot(100, self._startup)
    
    def _create_ui(self):
        """Create the basic UI structure."""
        # Create menu bar
        self._create_menu_bar()
        
        # Create toolbar
        self._create_toolbar()
        
        # Add status bar with cost widget placeholder
        self.statusBar().showMessage("Ready")
        
    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        file_menu.addAction("New Project", self._new_project)
        file_menu.addAction("Open Project", self._open_project)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        
        # Edit menu
        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction("Settings", self._open_settings)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self._show_about)
    
    def _create_toolbar(self):
        """Create the main toolbar."""
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        
        # Add actions
        toolbar.addAction("New", self._new_project)
        toolbar.addAction("Open", self._open_project)
        toolbar.addSeparator()
        
        # Navigation buttons (will be enabled/disabled by stage manager)
        self.back_action = toolbar.addAction("← Back", self._go_back)
        self.next_action = toolbar.addAction("Next →", self._go_next)
        self.back_action.setEnabled(False)
        self.next_action.setEnabled(False)
    
    def _startup(self):
        """Handle application startup."""
        # Register stages
        from src.new.stages import ProjectSetupStage, DocumentImportStage
        self.stage_manager.register_stage('setup', ProjectSetupStage)
        self.stage_manager.register_stage('import', DocumentImportStage)
        
        # Connect stage manager signals
        self.stage_manager.can_go_back_changed.connect(
            lambda enabled: self.back_action.setEnabled(enabled)
        )
        self.stage_manager.can_proceed_changed.connect(
            lambda enabled: self.next_action.setEnabled(enabled)
        )
        
        # Check for API keys
        providers = ['anthropic', 'gemini', 'azure_openai']
        missing_keys = [p for p in providers if not self.settings.has_api_key(p)]
        
        if missing_keys:
            self.logger.info(f"Missing API keys for: {missing_keys}")
        
        # For now, start with project setup
        self._new_project()
    
    def set_stage_widget(self, widget):
        """Set the current stage widget."""
        # This will be called by StageManager
        self.setCentralWidget(widget)
    
    def _new_project(self):
        """Start a new project."""
        self.logger.info("Starting new project")
        # Load the setup stage
        self.stage_manager.load_stage('setup')
    
    def _open_project(self):
        """Open an existing project."""
        # TODO: Implement project open dialog
        self.logger.info("Open project - not yet implemented")
    
    def _open_settings(self):
        """Open settings dialog."""
        # TODO: Implement settings dialog
        self.logger.info("Settings - not yet implemented")
    
    def _show_about(self):
        """Show about dialog."""
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(
            self,
            "About Forensic Report Drafter",
            "<h3>Forensic Report Drafter</h3>"
            "<p>New simplified UI - Development Version</p>"
            "<p>A professional tool for forensic psychologists to analyze and draft comprehensive reports.</p>"
        )
    
    def _go_back(self):
        """Navigate to previous stage."""
        self.stage_manager.previous_stage()
    
    def _go_next(self):
        """Navigate to next stage."""
        self.stage_manager.next_stage()
    
    def closeEvent(self, event):
        """Handle window close."""
        # Save window geometry
        self.settings.save_window_geometry(self.saveGeometry())
        
        # Close project if open
        if self.project_manager:
            self.project_manager.close_project()
        
        # Cleanup stage manager
        self.stage_manager.cleanup_current_stage()
        
        event.accept()


def main():
    """Main entry point for new UI."""
    # Configure startup logging
    configure_startup_logging()
    
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Forensic Report Drafter (New UI)")
    
    # Create Qt application
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # Set application metadata
    app.setApplicationName("Forensic Report Drafter")
    app.setOrganizationName("Forensic Psychology Tools")
    app.setApplicationDisplayName("Forensic Report Drafter")
    
    # Create and show main window
    window = SimplifiedMainWindow()
    window.show()
    
    # Run application
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())