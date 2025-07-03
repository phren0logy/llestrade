"""
Document import stage for the new UI.
Handles importing PDFs, DOCs, and text files.
"""

import logging
import mimetypes
from pathlib import Path
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QGroupBox, QProgressBar, QWidget, QSplitter,
    QTextEdit, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QMimeData, QTimer, QSize
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon

from src.new.core import BaseStage


class DocumentImportStage(BaseStage):
    """Stage for importing documents into the project."""
    
    # Additional signal for import progress
    import_progress = Signal(int, int)  # current, total
    
    def __init__(self, project=None):
        super().__init__(project)
        self.logger = logging.getLogger(__name__)
        self.imported_files: List[Path] = []
        self.pending_files: List[Path] = []
        
    def setup_ui(self):
        """Create the UI for document import."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # Title
        title = QLabel("Import Documents")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        
        # Description
        desc = QLabel("Import PDF, Word documents, or text files for analysis.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666;")
        layout.addWidget(desc)
        
        # Main content area with splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # Left side - file import area
        import_widget = self._create_import_widget()
        splitter.addWidget(import_widget)
        
        # Right side - preview area
        preview_widget = self._create_preview_widget()
        splitter.addWidget(preview_widget)
        
        # Set initial splitter sizes (60/40)
        splitter.setSizes([600, 400])
        
        layout.addWidget(splitter)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Action buttons
        button_widget = self._create_button_widget()
        layout.addWidget(button_widget)
        
    def _create_import_widget(self) -> QWidget:
        """Create the file import widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Drop zone
        drop_group = QGroupBox("Drop Files Here")
        drop_layout = QVBoxLayout(drop_group)
        
        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self._handle_dropped_files)
        self.drop_zone.setMinimumHeight(150)
        drop_layout.addWidget(self.drop_zone)
        
        # Browse button
        browse_layout = QHBoxLayout()
        browse_layout.addStretch()
        browse_btn = QPushButton("Browse Files...")
        browse_btn.clicked.connect(self._browse_files)
        browse_layout.addWidget(browse_btn)
        browse_layout.addStretch()
        drop_layout.addLayout(browse_layout)
        
        layout.addWidget(drop_group)
        
        # File list
        list_group = QGroupBox("Selected Files")
        list_layout = QVBoxLayout(list_group)
        
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.file_list.itemSelectionChanged.connect(self._on_selection_changed)
        list_layout.addWidget(self.file_list)
        
        # List controls
        controls_layout = QHBoxLayout()
        
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self._remove_selected)
        controls_layout.addWidget(self.remove_btn)
        
        controls_layout.addStretch()
        
        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.setEnabled(False)
        self.clear_btn.clicked.connect(self._clear_all)
        controls_layout.addWidget(self.clear_btn)
        
        list_layout.addLayout(controls_layout)
        layout.addWidget(list_group)
        
        return widget
    
    def _create_preview_widget(self) -> QWidget:
        """Create the file preview widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)
        
        # File info
        self.file_info_label = QLabel("Select a file to preview")
        self.file_info_label.setStyleSheet("color: #666; padding: 10px;")
        preview_layout.addWidget(self.file_info_label)
        
        # Preview text
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("File preview will appear here...")
        preview_layout.addWidget(self.preview_text)
        
        layout.addWidget(preview_group)
        
        # Import options
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout(options_group)
        
        self.convert_pdf_check = QCheckBox("Convert PDFs to text during import")
        self.convert_pdf_check.setChecked(True)
        options_layout.addWidget(self.convert_pdf_check)
        
        self.preserve_structure_check = QCheckBox("Preserve document structure")
        self.preserve_structure_check.setChecked(True)
        options_layout.addWidget(self.preserve_structure_check)
        
        layout.addWidget(options_group)
        
        return widget
    
    def _create_button_widget(self) -> QWidget:
        """Create the action buttons."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # File count label
        self.file_count_label = QLabel("No files selected")
        self.file_count_label.setStyleSheet("color: #666;")
        layout.addWidget(self.file_count_label)
        
        layout.addStretch()
        
        # Import button
        self.import_btn = QPushButton("Import Documents")
        self.import_btn.setObjectName("primary")
        self.import_btn.setStyleSheet("""
            QPushButton#primary {
                background-color: #1976d2;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 4px;
            }
            QPushButton#primary:hover {
                background-color: #1565c0;
            }
            QPushButton#primary:disabled {
                background-color: #ccc;
            }
        """)
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self._import_documents)
        layout.addWidget(self.import_btn)
        
        return widget
    
    def _browse_files(self):
        """Browse for files to import."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Documents to Import",
            str(Path.home() / "Documents"),
            "Documents (*.pdf *.doc *.docx *.txt *.md);;All Files (*.*)"
        )
        
        if files:
            self._add_files([Path(f) for f in files])
    
    def _handle_dropped_files(self, files: List[str]):
        """Handle files dropped on the drop zone."""
        self._add_files([Path(f) for f in files])
    
    def _add_files(self, files: List[Path]):
        """Add files to the import list."""
        added_count = 0
        
        for file_path in files:
            if not file_path.exists():
                continue
                
            # Check if already added
            already_added = False
            for i in range(self.file_list.count()):
                item = self.file_list.item(i)
                if item.data(Qt.UserRole) == str(file_path):
                    already_added = True
                    break
            
            if already_added:
                continue
            
            # Validate file type
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if mime_type and not any(t in mime_type for t in ['pdf', 'word', 'text', 'document']):
                if file_path.suffix.lower() not in ['.txt', '.md', '.pdf', '.doc', '.docx']:
                    continue
            
            # Add to list
            item = QListWidgetItem(file_path.name)
            item.setData(Qt.UserRole, str(file_path))
            item.setToolTip(str(file_path))
            
            # Add file size
            size_mb = file_path.stat().st_size / (1024 * 1024)
            item.setText(f"{file_path.name} ({size_mb:.1f} MB)")
            
            self.file_list.addItem(item)
            added_count += 1
        
        if added_count > 0:
            self._update_ui_state()
    
    def _remove_selected(self):
        """Remove selected files from the list."""
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
        
        self._update_ui_state()
    
    def _clear_all(self):
        """Clear all files from the list."""
        self.file_list.clear()
        self._update_ui_state()
    
    def _on_selection_changed(self):
        """Handle file selection change."""
        selected = self.file_list.selectedItems()
        self.remove_btn.setEnabled(len(selected) > 0)
        
        # Show preview of first selected file
        if selected:
            file_path = Path(selected[0].data(Qt.UserRole))
            self._show_preview(file_path)
        else:
            self._clear_preview()
    
    def _show_preview(self, file_path: Path):
        """Show preview of a file."""
        # Update file info
        stat = file_path.stat()
        size_mb = stat.st_size / (1024 * 1024)
        self.file_info_label.setText(
            f"<b>{file_path.name}</b><br>"
            f"Size: {size_mb:.1f} MB<br>"
            f"Type: {file_path.suffix.upper()[1:] if file_path.suffix else 'Unknown'}"
        )
        
        # Show preview based on file type
        if file_path.suffix.lower() in ['.txt', '.md']:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read(5000)  # First 5KB
                    if len(content) == 5000:
                        content += "\n\n... (preview truncated)"
                    self.preview_text.setPlainText(content)
            except Exception as e:
                self.preview_text.setPlainText(f"Error reading file: {str(e)}")
        elif file_path.suffix.lower() == '.pdf':
            self.preview_text.setPlainText(
                "PDF Document\n\n"
                "PDF files will be converted to text during import using Azure Document Intelligence.\n\n"
                "Note: Large PDFs may take several minutes to process."
            )
        elif file_path.suffix.lower() in ['.doc', '.docx']:
            self.preview_text.setPlainText(
                "Word Document\n\n"
                "Word documents will be converted to text during import.\n\n"
                "Formatting and tables will be preserved where possible."
            )
        else:
            self.preview_text.setPlainText("Preview not available for this file type.")
    
    def _clear_preview(self):
        """Clear the preview area."""
        self.file_info_label.setText("Select a file to preview")
        self.preview_text.clear()
    
    def _update_ui_state(self):
        """Update UI state based on file list."""
        count = self.file_list.count()
        self.import_btn.setEnabled(count > 0)
        self.clear_btn.setEnabled(count > 0)
        
        if count == 0:
            self.file_count_label.setText("No files selected")
        elif count == 1:
            self.file_count_label.setText("1 file selected")
        else:
            self.file_count_label.setText(f"{count} files selected")
        
        # Update validation
        self._validate()
    
    def _import_documents(self):
        """Import the selected documents."""
        # Collect files
        self.pending_files = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            self.pending_files.append(Path(item.data(Qt.UserRole)))
        
        if not self.pending_files:
            return
        
        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.pending_files))
        self.progress_bar.setValue(0)
        
        # Disable controls during import
        self.import_btn.setEnabled(False)
        self.drop_zone.setEnabled(False)
        self.file_list.setEnabled(False)
        
        # Start import process
        QTimer.singleShot(100, self._process_next_file)
    
    def _process_next_file(self):
        """Process the next file in the queue."""
        if not self.pending_files:
            # Import complete
            self._import_complete()
            return
        
        # Get next file
        file_path = self.pending_files.pop(0)
        current_index = len(self.imported_files) + 1
        total_files = len(self.imported_files) + len(self.pending_files) + 1
        
        self.progress_bar.setValue(current_index)
        self.import_progress.emit(current_index, total_files)
        
        # Copy file to project
        try:
            dest_path = self.project.get_project_file("source_documents", file_path.name)
            
            # Handle duplicate names
            if dest_path.exists():
                base = dest_path.stem
                suffix = dest_path.suffix
                counter = 1
                while dest_path.exists():
                    dest_path = dest_path.parent / f"{base}_{counter}{suffix}"
                    counter += 1
            
            # Copy file
            import shutil
            shutil.copy2(file_path, dest_path)
            
            self.imported_files.append(dest_path)
            self.logger.info(f"Imported: {file_path.name} -> {dest_path.name}")
            
        except Exception as e:
            self.logger.error(f"Failed to import {file_path.name}: {e}")
            QMessageBox.warning(
                self,
                "Import Error",
                f"Failed to import {file_path.name}:\n{str(e)}"
            )
        
        # Process next file
        QTimer.singleShot(50, self._process_next_file)
    
    def _import_complete(self):
        """Handle import completion."""
        # Hide progress
        self.progress_bar.setVisible(False)
        
        # Re-enable controls
        self.drop_zone.setEnabled(True)
        self.file_list.setEnabled(True)
        
        # Show summary
        if self.imported_files:
            QMessageBox.information(
                self,
                "Import Complete",
                f"Successfully imported {len(self.imported_files)} document(s)."
            )
            
            # Clear the file list
            self.file_list.clear()
            self._update_ui_state()
            
            # Save import data
            results = {
                "imported_files": [str(f) for f in self.imported_files],
                "convert_pdf": self.convert_pdf_check.isChecked(),
                "preserve_structure": self.preserve_structure_check.isChecked()
            }
            
            # Save state and emit completion
            self.save_state()
            self.completed.emit(results)
        else:
            self.import_btn.setEnabled(True)
    
    def validate(self) -> tuple[bool, str]:
        """Check if stage can proceed."""
        if not self.imported_files:
            return False, "Import at least one document to proceed"
        return True, ""
    
    def save_state(self):
        """Save current state to project."""
        if not self.project:
            return
        
        state = {
            "imported_files": [str(f) for f in self.imported_files],
            "pending_files": [str(f) for f in self.pending_files],
            "convert_pdf": self.convert_pdf_check.isChecked(),
            "preserve_structure": self.preserve_structure_check.isChecked()
        }
        
        self.project.save_stage_data("import", state)
    
    def load_state(self):
        """Load state from project."""
        if not self.project:
            return
        
        state = self.project.get_stage_data("import")
        if not state:
            return
        
        # Restore imported files
        self.imported_files = [Path(f) for f in state.get("imported_files", [])]
        
        # Restore options
        self.convert_pdf_check.setChecked(state.get("convert_pdf", True))
        self.preserve_structure_check.setChecked(state.get("preserve_structure", True))
        
        # Update UI
        self._update_ui_state()
        
        # Show imported files info
        if self.imported_files:
            self.file_count_label.setText(f"{len(self.imported_files)} documents imported")


class DropZone(QLabel):
    """Widget that accepts file drops."""
    
    files_dropped = Signal(list)  # List of file paths
    
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #ccc;
                border-radius: 8px;
                padding: 20px;
                background-color: #f9f9f9;
            }
            QLabel:hover {
                border-color: #1976d2;
                background-color: #e3f2fd;
            }
        """)
        self.setText("Drag and drop files here\nor click Browse Files")
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter event."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("""
                QLabel {
                    border: 2px solid #1976d2;
                    border-radius: 8px;
                    padding: 20px;
                    background-color: #e3f2fd;
                }
            """)
    
    def dragLeaveEvent(self, event):
        """Handle drag leave event."""
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #ccc;
                border-radius: 8px;
                padding: 20px;
                background-color: #f9f9f9;
            }
            QLabel:hover {
                border-color: #1976d2;
                background-color: #e3f2fd;
            }
        """)
    
    def dropEvent(self, event: QDropEvent):
        """Handle drop event."""
        files = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                files.append(url.toLocalFile())
        
        if files:
            self.files_dropped.emit(files)
        
        # Reset style
        self.dragLeaveEvent(None)