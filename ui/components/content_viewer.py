"""
Content viewer component for the Forensic Psych Report Drafter.
Provides a simple text viewer without the file tree.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QTextEdit, QWidget, QVBoxLayout

from src.config.config import DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE


class ContentViewer(QWidget):
    """
    A simple content viewer without a file tree.
    Used for tabs that don't need the file/status/size tree view.
    """
    
    def __init__(self, placeholder_text=None):
        """
        Initialize the content viewer.
        
        Args:
            placeholder_text: Placeholder text for the content viewer
        """
        super().__init__()
        
        # Default values
        self.placeholder_text = placeholder_text or "Content will appear here"
        
        # Set up UI
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI components for the content viewer."""
        # Create layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create content viewer
        self.content_viewer = QTextEdit()
        self.content_viewer.setReadOnly(True)
        self.content_viewer.setFont(QFont(DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE))
        self.content_viewer.setPlaceholderText(self.placeholder_text)
        
        # Add to layout
        layout.addWidget(self.content_viewer)
        self.setLayout(layout)
    
    def set_content(self, text):
        """Set the content of the viewer."""
        self.content_viewer.setPlainText(text)
    
    def set_markdown(self, markdown_text):
        """Set markdown content in the viewer.
        
        This is a convenience method that formats markdown as HTML for better rendering.
        For now, it's a simple wrapper around set_content, but could be enhanced
        with proper markdown rendering in the future.
        """
        self.content_viewer.setPlainText(markdown_text)
        # Future enhancement: Use a markdown renderer here
    
    def append_content(self, text):
        """Append text to the content viewer."""
        self.content_viewer.append(text)
    
    def clear_content(self):
        """Clear the content viewer."""
        self.content_viewer.clear()
