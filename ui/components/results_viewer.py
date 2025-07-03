"""
Results viewer component for the Forensic Psych Report Drafter.
Provides a split view with a file tree and content viewer.
"""

import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QSplitter, QTreeWidget, QTreeWidgetItem, QTextEdit

from src.config.config import DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE


class ResultsViewer(QSplitter):
    """
    A reusable component that provides a split view with a
    file tree on the left and a content viewer on the right.
    """
    
    # Signal emitted when an item is selected in the tree
    item_selected = Signal(QTreeWidgetItem, int)
    
    def __init__(self, header_labels=None, placeholder_text=None):
        """
        Initialize the results viewer.
        
        Args:
            header_labels: Column header labels for the tree view
            placeholder_text: Placeholder text for the content viewer
        """
        super().__init__(Qt.Orientation.Horizontal)
        
        # Default values
        self.header_labels = header_labels or ["Files", "Status", "Size"]
        self.placeholder_text = placeholder_text or "Select an item to view its content"
        
        # Set up UI
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI components for the results viewer."""
        # Create tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(self.header_labels)
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumWidth(300)
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        
        # Create content viewer
        self.content_viewer = QTextEdit()
        self.content_viewer.setReadOnly(True)
        self.content_viewer.setFont(QFont(DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE))
        self.content_viewer.setPlaceholderText(self.placeholder_text)
        
        # Add widgets to splitter
        self.addWidget(self.tree)
        self.addWidget(self.content_viewer)
        
        # Set the initial sizes
        self.setSizes([300, 500])
    
    def clear_tree(self):
        """Clear all items from the tree."""
        self.tree.clear()
    
    def add_tree_item(self, parent, text, data=None, **kwargs):
        """
        Add an item to the tree.
        
        Args:
            parent: Parent item or None for root item
            text: Text for the first column
            data: Optional data to attach to the item
            **kwargs: Additional column texts
        
        Returns:
            The created QTreeWidgetItem
        """
        # Create item with text for first column
        if isinstance(text, list):
            item = QTreeWidgetItem(parent, text)
        else:
            item = QTreeWidgetItem(parent, [text])
        
        # Set additional column texts
        for col, col_text in kwargs.items():
            if col.isdigit():
                item.setText(int(col), col_text)
        
        # Set item data if provided
        if data is not None:
            item.setData(0, Qt.ItemDataRole.UserRole, data)
        
        # If no parent, add to root
        if parent is None:
            self.tree.addTopLevelItem(item)
        
        return item
    
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
    
    def get_content(self):
        """Get the current content of the viewer."""
        return self.content_viewer.toPlainText()
    
    def clear(self):
        """Clear both the tree and content viewer."""
        self.clear_tree()
        self.clear_content()
    
    def set_detail_widget(self, widget):
        """
        Replace the content viewer with a custom widget.
        
        Args:
            widget: Any QWidget to display in the detail pane
        """
        # Remove the current content viewer
        old_widget = self.widget(1)
        if old_widget:
            old_widget.setParent(None)
        
        # Add the new widget
        self.insertWidget(1, widget)
        
        # Update the content_viewer reference
        self.content_viewer = widget
        
        # Reset the sizes
        self.setSizes([300, 500])
    
    def _on_tree_item_clicked(self, item, column):
        """Handle tree item click events."""
        # Emit the item selected signal
        self.item_selected.emit(item, column)
