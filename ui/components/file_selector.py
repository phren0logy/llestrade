"""
File selector component for the Forensic Psych Report Drafter.
Provides UI for selecting files or directories with validation.
"""

import os
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QFileDialog,
    QGroupBox,
)


class FileSelector(QGroupBox):
    """
    A reusable component for selecting files or directories.
    Displays a button, a text field with the selected path,
    and handles file dialog interactions.
    """
    
    def __init__(
        self,
        title="File Selection",
        button_text="Select File",
        file_mode=QFileDialog.FileMode.ExistingFile,
        file_filter="All Files (*)",
        placeholder_text=None,
        callback=None,
        recursive_selection=False,
    ):
        """
        Initialize the file selector.
        
        Args:
            title: Title for the group box
            button_text: Text for the selection button
            file_mode: QFileDialog.FileMode (ExistingFile, ExistingFiles, Directory)
            file_filter: Filter string for file types
            placeholder_text: Placeholder text for the path field
            callback: Function to call when selection changes
            recursive_selection: For Directory mode, recursively find all files matching filter
        """
        super().__init__(title)
        
        self.file_mode = file_mode
        self.file_filter = file_filter
        self.callback = callback
        self.selected_path = None
        self.selected_paths = []
        self.placeholder_text = placeholder_text or "No file selected"
        self.button_text = button_text
        self.recursive_selection = recursive_selection
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI components for the file selector."""
        layout = QVBoxLayout()
        
        # Create button and path display in a horizontal layout
        selector_layout = QHBoxLayout()
        
        # Create button
        self.select_button = QPushButton(self.button_text)
        self.select_button.clicked.connect(self.show_file_dialog)
        selector_layout.addWidget(self.select_button)
        
        # Create path display
        self.path_display = QLineEdit()
        self.path_display.setReadOnly(True)
        self.path_display.setPlaceholderText(self.placeholder_text)
        selector_layout.addWidget(self.path_display)
        
        # Add selector layout
        layout.addLayout(selector_layout)
        
        # Add validation message area
        self.validation_label = QLabel("")
        self.validation_label.setStyleSheet("color: red;")
        layout.addWidget(self.validation_label)
        
        self.setLayout(layout)
    
    def show_file_dialog(self):
        """Show the file dialog appropriate for the current mode."""
        dialog = QFileDialog()
        dialog.setFileMode(self.file_mode)
        
        if self.file_mode == QFileDialog.FileMode.Directory:
            selected_path = dialog.getExistingDirectory(
                self, "Select Directory", os.path.expanduser("~")
            )
            if selected_path:
                self.set_selected_path(selected_path)
                
                # If recursive selection is enabled, find all matching files in directory
                if self.recursive_selection and self.callback:
                    # Pass the directory path for the callback to handle recursive search
                    self.callback(selected_path, recursive=True)
        else:
            dialog.setNameFilter(self.file_filter)
            if dialog.exec():
                selected_files = dialog.selectedFiles()
                if self.file_mode == QFileDialog.FileMode.ExistingFiles:
                    self.set_selected_paths(selected_files)
                else:
                    self.set_selected_path(selected_files[0] if selected_files else None)
    
    def set_selected_path(self, path):
        """
        Set the selected path and update the UI.
        
        Args:
            path: Selected path or None to clear
        """
        self.selected_path = path
        self.selected_paths = [path] if path else []
        self.update_ui()
        
        # Call the callback if provided
        if self.callback and self.selected_path:
            self.callback(self.selected_path)
    
    def set_selected_paths(self, paths):
        """
        Set multiple selected paths and update the UI.
        
        Args:
            paths: List of selected paths
        """
        self.selected_paths = paths if paths else []
        self.selected_path = paths[0] if paths else None
        self.update_ui()
        
        # Call the callback if provided
        if self.callback and self.selected_paths:
            self.callback(self.selected_paths)
    
    def update_ui(self):
        """Update the UI based on the current selection."""
        if self.file_mode == QFileDialog.FileMode.ExistingFiles and len(self.selected_paths) > 1:
            self.path_display.setText(f"{len(self.selected_paths)} files selected")
        elif self.selected_path:
            self.path_display.setText(self.selected_path)
        else:
            self.path_display.clear()
    
    def get_selected_path(self):
        """Get the selected path."""
        return self.selected_path
    
    def get_selected_paths(self):
        """Get all selected paths."""
        return self.selected_paths
    
    def set_validation_message(self, message):
        """Set a validation message to display."""
        self.validation_label.setText(message)
    
    def clear_validation_message(self):
        """Clear the validation message."""
        self.validation_label.clear()
