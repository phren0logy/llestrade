"""
Status panel component for the Forensic Psych Report Drafter.
Provides a collapsible panel for displaying status and log information.
"""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGroupBox, QLabel, QTextEdit, QVBoxLayout

from config import DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE


class StatusPanel(QGroupBox):
    """
    A collapsible status panel that displays processing status
    and detailed log information.
    """
    
    def __init__(self, title="Processing Status", max_height=100):
        """
        Initialize the status panel.
        
        Args:
            title: Title for the group box
            max_height: Maximum height for the details area
        """
        super().__init__(title)
        
        # Make the group box collapsible
        self.setCheckable(True)
        self.setChecked(True)  # Start expanded
        
        # Set up UI
        self.max_height = max_height
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI components for the status panel."""
        layout = QVBoxLayout()
        
        # Status summary label
        self.summary_label = QLabel("Ready to begin")
        self.summary_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.summary_label)
        
        # Detailed status text area
        self.details_area = QTextEdit()
        self.details_area.setReadOnly(True)
        self.details_area.setMaximumHeight(self.max_height)
        self.details_area.setFont(QFont(DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE))
        self.details_area.setPlaceholderText("Processing status and details will appear here")
        layout.addWidget(self.details_area)
        
        self.setLayout(layout)
    
    def update_summary(self, text):
        """Update the summary label text."""
        self.summary_label.setText(text)
    
    def append_details(self, text):
        """Append text to the details area."""
        self.details_area.append(text)
        # Auto-scroll to the bottom
        self.details_area.ensureCursorVisible()
    
    def clear_details(self):
        """Clear the details area."""
        self.details_area.clear()
    
    def set_details(self, text):
        """Set the entire content of the details area."""
        self.details_area.setPlainText(text)
    
    def append_error(self, text):
        """Append error text to the details area with error formatting."""
        self.append_details(text)
    
    def append_warning(self, text):
        """Append warning text to the details area with warning formatting."""
        self.append_details(text)
