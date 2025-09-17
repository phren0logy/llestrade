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
    QGroupBox, QProgressBar, QWidget, QCheckBox, QTreeWidget,
    QTreeWidgetItem, QDialog, QDialogButtonBox, QSplitter,
    QTextEdit
)
from PySide6.QtCore import Qt, Signal, QMimeData, QTimer, QSize
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon

from src.new.core import BaseStage


class DocumentImportStage(BaseStage):
    """Stage for importing documents into the project."""
    
    # Additional signal for import progress
    import_progress = Signal(int, int)  # current, total
    
    def __init__(self, project=None):
        self.imported_files: List[Path] = []
        self.pending_files: List[Path] = []
        self.all_discovered_files: List[Path] = []  # All files found before exclusions
        self.excluded_paths: set = set()  # Files/folders to exclude
        self.excluded_patterns: List[str] = []  # Patterns to exclude (e.g., *.tmp)
        self.base_folder: Optional[Path] = None  # Track base folder for relative paths
        self.logger = logging.getLogger(__name__)
        super().__init__(project)
        
    def setup_ui(self):
        """Create the UI for document import."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # Title
        title = QLabel("Import Documents")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        
        # Description
        desc = QLabel("Select a folder to import all PDF, Word documents, and text files recursively.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666;")
        layout.addWidget(desc)
        
        # Main import area
        import_widget = self._create_import_widget()
        layout.addWidget(import_widget)
        
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
        drop_group = QGroupBox("Select Documents Folder")
        drop_layout = QVBoxLayout(drop_group)
        
        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self._handle_dropped_files)
        self.drop_zone.setMinimumHeight(150)
        drop_layout.addWidget(self.drop_zone)
        
        # Browse button
        browse_layout = QHBoxLayout()
        browse_layout.addStretch()
        browse_folder_btn = QPushButton("Browse Folder...")
        browse_folder_btn.clicked.connect(self._browse_folder)
        browse_layout.addWidget(browse_folder_btn)
        browse_layout.addStretch()
        drop_layout.addLayout(browse_layout)
        
        layout.addWidget(drop_group)
        
        # File list
        list_group = QGroupBox("Discovered Documents")
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
        
        # Exclusions controls
        exclusion_layout = QHBoxLayout()
        self.configure_exclusions_btn = QPushButton("Configure Exclusions...")
        self.configure_exclusions_btn.setEnabled(False)
        self.configure_exclusions_btn.clicked.connect(self._show_exclusion_dialog)
        exclusion_layout.addWidget(self.configure_exclusions_btn)
        
        self.exclusion_label = QLabel("No exclusions")
        self.exclusion_label.setStyleSheet("color: #666;")
        exclusion_layout.addWidget(self.exclusion_label)
        exclusion_layout.addStretch()
        
        list_layout.addLayout(exclusion_layout)
        layout.addWidget(list_group)
        
        # Import options
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout(options_group)
        
        self.convert_pdf_check = QCheckBox("Convert PDFs to text during import")
        self.convert_pdf_check.setChecked(True)
        options_layout.addWidget(self.convert_pdf_check)
        
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
    
    def _browse_folder(self):
        """Browse for a folder to import all documents from recursively."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Documents Folder",
            str(Path.home() / "Documents"),
            QFileDialog.ShowDirsOnly
        )
        
        if folder:
            self._scan_and_add_folder(Path(folder))
    
    
    def _scan_and_add_folder(self, folder_path: Path):
        """Recursively scan folder for valid documents."""
        # Set base folder for relative path display
        self.base_folder = folder_path
        
        # Valid extensions to look for
        valid_extensions = {'.pdf', '.doc', '.docx', '.txt', '.md'}
        
        # Find all files recursively
        found_files = []
        try:
            for file_path in folder_path.rglob('*'):
                # Skip hidden files and directories
                if any(part.startswith('.') for part in file_path.parts):
                    continue
                
                # Check if it's a file with valid extension
                if file_path.is_file() and file_path.suffix.lower() in valid_extensions:
                    found_files.append(file_path)
            
            # Sort files by path for consistent ordering
            found_files.sort()
            
            if found_files:
                # Store all discovered files
                self.all_discovered_files = found_files.copy()
                
                # Show summary message
                QMessageBox.information(
                    self,
                    "Files Found",
                    f"Found {len(found_files)} document(s) in {folder_path.name}"
                )
                
                # Enable exclusions button
                self.configure_exclusions_btn.setEnabled(True)
                
                # Add all found files
                self._add_files(found_files)
            else:
                QMessageBox.information(
                    self,
                    "No Files Found",
                    f"No valid documents found in {folder_path.name}\n\n"
                    f"Looking for: PDF, Word, Text, and Markdown files"
                )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Scan Error",
                f"Error scanning folder: {str(e)}"
            )
        # Note: Don't clear base_folder here as we need it for exclusions
    
    def _handle_dropped_files(self, files: List[str]):
        """Handle files or folders dropped on the drop zone."""
        paths = [Path(f) for f in files]
        
        # Separate files and folders
        file_paths = []
        folder_paths = []
        
        for path in paths:
            if path.is_dir():
                folder_paths.append(path)
            elif path.is_file():
                file_paths.append(path)
        
        # Process folders first (recursive scan)
        for folder in folder_paths:
            self._scan_and_add_folder(folder)
        
        # Then add individual files
        if file_paths:
            self._add_files(file_paths)
    
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
            
            # Determine display name (use relative path if from folder scan)
            if self.base_folder and file_path.is_relative_to(self.base_folder):
                display_name = str(file_path.relative_to(self.base_folder))
            else:
                display_name = file_path.name
            
            # Add file size
            size_mb = file_path.stat().st_size / (1024 * 1024)
            
            # Create list item
            item = QListWidgetItem(f"{display_name} ({size_mb:.1f} MB)")
            item.setData(Qt.UserRole, str(file_path))
            item.setToolTip(str(file_path))
            
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
        self.all_discovered_files.clear()
        self.excluded_paths.clear()
        self.excluded_patterns.clear()
        self.base_folder = None
        self.configure_exclusions_btn.setEnabled(False)
        self.exclusion_label.setText("No exclusions")
        self._update_ui_state()
    
    def _show_exclusion_dialog(self):
        """Show the exclusion configuration dialog."""
        if not self.base_folder or not self.all_discovered_files:
            return
        
        dialog = ExclusionDialog(
            self.base_folder,
            self.all_discovered_files,
            self.excluded_paths,
            self
        )
        
        if dialog.exec() == QDialog.Accepted:
            # Update excluded paths
            self.excluded_paths = dialog.excluded_paths
            self.excluded_patterns = dialog.get_patterns()
            
            # Apply exclusions
            self._apply_exclusions()
    
    def _apply_exclusions(self):
        """Apply exclusions to the file list."""
        if not self.all_discovered_files:
            return
        
        # Clear current list
        self.file_list.clear()
        
        # Filter files based on exclusions
        filtered_files = []
        for file_path in self.all_discovered_files:
            # Check if file or any parent folder is excluded
            is_excluded = False
            
            # Check path exclusions
            current = file_path
            while current != self.base_folder.parent:
                if current in self.excluded_paths:
                    is_excluded = True
                    break
                current = current.parent
            
            # Check pattern exclusions
            if not is_excluded and self.excluded_patterns:
                import fnmatch
                file_name = file_path.name
                for pattern in self.excluded_patterns:
                    if fnmatch.fnmatch(file_name, pattern):
                        is_excluded = True
                        break
            
            if not is_excluded:
                filtered_files.append(file_path)
        
        # Re-add filtered files
        if filtered_files:
            self._add_files(filtered_files)
        
        # Update exclusion label
        excluded_count = len(self.all_discovered_files) - len(filtered_files)
        if excluded_count > 0:
            self.exclusion_label.setText(f"{excluded_count} files excluded")
            self.exclusion_label.setStyleSheet("color: #ff9800;")
        else:
            self.exclusion_label.setText("No exclusions")
            self.exclusion_label.setStyleSheet("color: #666;")
        
        self._update_ui_state()
    
    def _on_selection_changed(self):
        """Handle file selection change."""
        selected = self.file_list.selectedItems()
        self.remove_btn.setEnabled(len(selected) > 0)
    
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
                "convert_pdf": self.convert_pdf_check.isChecked()
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
            "convert_pdf": self.convert_pdf_check.isChecked()
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
        self.setText("Drag and drop a folder or files here\nor click Browse Folder")
    
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


class ExclusionDialog(QDialog):
    """Dialog for configuring file and folder exclusions."""
    
    def __init__(self, base_folder: Path, all_files: List[Path], excluded_paths: set, parent=None):
        super().__init__(parent)
        self.base_folder = base_folder
        self.all_files = all_files
        self.excluded_paths = excluded_paths.copy()  # Make a copy to work with
        
        self.setWindowTitle("Configure Exclusions")
        self.setModal(True)
        self.resize(800, 600)
        
        self.setup_ui()
        self.populate_tree()
    
    def setup_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Description
        desc = QLabel(
            "Select files or folders to exclude from import. "
            "Unchecked items will be excluded."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Splitter for tree and preview
        splitter = QSplitter(Qt.Horizontal)
        
        # Tree widget
        tree_widget = QWidget()
        tree_layout = QVBoxLayout(tree_widget)
        
        # Tree controls
        controls = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all)
        controls.addWidget(select_all_btn)
        
        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self.deselect_all)
        controls.addWidget(deselect_all_btn)
        
        controls.addStretch()
        tree_layout.addLayout(controls)
        
        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Files and Folders")
        self.tree.itemChanged.connect(self.on_item_changed)
        tree_layout.addWidget(self.tree)
        
        # Summary label
        self.summary_label = QLabel()
        tree_layout.addWidget(self.summary_label)
        
        splitter.addWidget(tree_widget)
        
        # Preview pane
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        
        preview_title = QLabel("Excluded Patterns")
        preview_title.setStyleSheet("font-weight: bold;")
        preview_layout.addWidget(preview_title)
        
        self.patterns_edit = QTextEdit()
        self.patterns_edit.setPlaceholderText(
            "Enter patterns to exclude (one per line):\n"
            "Examples:\n"
            "*.tmp - exclude all .tmp files\n"
            "__pycache__ - exclude folders named __pycache__\n"
            "test_* - exclude files starting with test_"
        )
        preview_layout.addWidget(self.patterns_edit)
        
        splitter.addWidget(preview_widget)
        splitter.setStretchFactor(0, 2)  # Tree gets more space
        splitter.setStretchFactor(1, 1)
        
        layout.addWidget(splitter)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def populate_tree(self):
        """Populate the tree with files and folders."""
        # Build folder structure
        folder_items = {}
        
        for file_path in self.all_files:
            # Get relative path
            rel_path = file_path.relative_to(self.base_folder)
            parts = rel_path.parts
            
            # Create folder hierarchy
            parent_item = None
            current_path = self.base_folder
            
            for i, part in enumerate(parts[:-1]):  # All but the last (file name)
                current_path = current_path / part
                
                if current_path not in folder_items:
                    # Create folder item
                    if parent_item is None:
                        folder_item = QTreeWidgetItem(self.tree)
                    else:
                        folder_item = QTreeWidgetItem(parent_item)
                    
                    folder_item.setText(0, part)
                    folder_item.setData(0, Qt.UserRole, str(current_path))
                    folder_item.setCheckState(0, Qt.Checked if current_path not in self.excluded_paths else Qt.Unchecked)
                    folder_item.setFlags(folder_item.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
                    folder_items[current_path] = folder_item
                    parent_item = folder_item
                else:
                    parent_item = folder_items[current_path]
            
            # Add file item
            if parent_item is None:
                file_item = QTreeWidgetItem(self.tree)
            else:
                file_item = QTreeWidgetItem(parent_item)
            
            file_item.setText(0, parts[-1])
            file_item.setData(0, Qt.UserRole, str(file_path))
            file_item.setCheckState(0, Qt.Checked if file_path not in self.excluded_paths else Qt.Unchecked)
            file_item.setFlags(file_item.flags() | Qt.ItemIsUserCheckable)
        
        # Expand all
        self.tree.expandAll()
        self.update_summary()
    
    def on_item_changed(self, item: QTreeWidgetItem, column: int):
        """Handle item check state change."""
        if column != 0:
            return
        
        path = Path(item.data(0, Qt.UserRole))
        
        if item.checkState(0) == Qt.Unchecked:
            self.excluded_paths.add(path)
        else:
            self.excluded_paths.discard(path)
        
        self.update_summary()
    
    def select_all(self):
        """Select all items."""
        self.set_all_check_state(Qt.Checked)
    
    def deselect_all(self):
        """Deselect all items."""
        self.set_all_check_state(Qt.Unchecked)
    
    def set_all_check_state(self, state: Qt.CheckState):
        """Set check state for all items."""
        def set_state_recursive(item):
            item.setCheckState(0, state)
            for i in range(item.childCount()):
                set_state_recursive(item.child(i))
        
        for i in range(self.tree.topLevelItemCount()):
            set_state_recursive(self.tree.topLevelItem(i))
    
    def update_summary(self):
        """Update the summary label."""
        # Count included files
        included_count = 0
        for file_path in self.all_files:
            # Check if file or any parent folder is excluded
            is_excluded = False
            current = file_path
            while current != self.base_folder.parent:
                if current in self.excluded_paths:
                    is_excluded = True
                    break
                current = current.parent
            
            if not is_excluded:
                included_count += 1
        
        total = len(self.all_files)
        excluded = total - included_count
        
        self.summary_label.setText(
            f"Including {included_count} of {total} files ({excluded} excluded)"
        )
    
    def get_patterns(self) -> List[str]:
        """Get exclusion patterns from the text edit."""
        text = self.patterns_edit.toPlainText().strip()
        if not text:
            return []
        return [line.strip() for line in text.split('\n') if line.strip()]