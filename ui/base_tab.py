"""
Base tab module for the Forensic Psych Report Drafter.
Provides a common interface for all tab implementations.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QStatusBar, QLabel


class BaseTab(QWidget):
    """
    Base class for all application tabs.
    Provides common functionality and interface.
    """
    
    def __init__(self, parent=None, status_bar: QStatusBar = None):
        """
        Initialize the base tab with common elements.
        
        Args:
            parent: Parent widget
            status_bar: Application status bar for displaying messages
        """
        super().__init__(parent)
        self.status_bar = status_bar
        self.layout = QVBoxLayout(self)
        self.status_label = QLabel("")
        
        # Set the tab layout
        self.setup_ui()
        self.setLayout(self.layout)
    
    def setup_ui(self):
        """
        Set up the UI components for the tab.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement setup_ui method")
    
    def show_status(self, message: str, timeout: int = 0):
        """
        Display a status message in the tab's status label.
        
        Args:
            message: Message to display
            timeout: Timeout in milliseconds (0 for no timeout)
        """
        self.status_label.setText(message)
    
    def show_status_bar_message(self, message: str, timeout: int = 3000):
        """
        Display a message in the application status bar.
        
        Args:
            message: Message to display
            timeout: Timeout in milliseconds (0 for no timeout)
        """
        if self.status_bar:
            self.status_bar.showMessage(message, timeout)
    
    def clear_status(self):
        """Clear the status message."""
        self.status_label.clear()
    
    def reset(self):
        """
        Reset the tab to its initial state.
        Should be implemented by subclasses if needed.
        """
        pass
