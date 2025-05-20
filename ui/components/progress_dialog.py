"""
Progress dialog component for displaying progress of long-running operations.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
)


class ProgressDialog(QDialog):
    """A dialog for displaying progress of long-running operations with detail area."""
    
    def __init__(self, title, description, parent=None):
        """Initialize the progress dialog."""
        super().__init__(parent)
        
        # Set window properties
        self.setWindowTitle(title)
        self.setMinimumSize(600, 400)
        self.setModal(True)
        
        # Create layout
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Add description label
        self.description_label = QLabel(description)
        layout.addWidget(self.description_label)
        
        # Add progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Add status label
        self.status_label = QLabel("Initializing...")
        layout.addWidget(self.status_label)
        
        # Add details area
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setPlaceholderText("Progress details will appear here...")
        layout.addWidget(self.details_text)
        
    def update_progress(self, percentage, status_text):
        """Update the progress and status text."""
        self.progress_bar.setValue(percentage)
        self.status_label.setText(status_text)
        
        # Add the status to the details area
        self.details_text.append(status_text)
        
        # Auto-scroll to the bottom
        scrollbar = self.details_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
        # Process events to update UI
        self.repaint()
