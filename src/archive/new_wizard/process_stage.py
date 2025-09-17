"""
Document processing stage for the new UI.
Handles PDF conversion, Word document processing, and text file imports.
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QTextEdit, QSplitter, QMessageBox, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QFont

from src.new.core.stage_manager import BaseStage
from src.new.core import SecureSettings
from src.core.pdf_utils import process_pdf_with_azure
from src.core.file_utils import process_docx_to_markdown, process_txt_to_markdown


class DocumentProcessorThread(QThread):
    """Worker thread for processing documents."""
    
    # Signals
    progress = Signal(int, str)  # percent, message
    file_processed = Signal(str, str, bool, str)  # filename, output_path, success, error_msg
    finished = Signal()
    error = Signal(str)
    
    def __init__(self, files_to_process: List[Path], output_dir: Path):
        super().__init__()
        self.files_to_process = files_to_process
        self.output_dir = output_dir
        self._is_running = True
        self.logger = logging.getLogger(__name__)
        
        # Get Azure DI credentials from SecureSettings
        self.azure_di_endpoint = None
        self.azure_di_key = None
        try:
            settings = SecureSettings()
            azure_di_settings = settings.get("azure_di_settings", {})
            self.azure_di_endpoint = azure_di_settings.get("endpoint")
            self.azure_di_key = settings.get_api_key("azure_di")
        except Exception as e:
            self.logger.warning(f"Could not load Azure DI settings: {e}")
        
    def run(self):
        """Process all documents."""
        try:
            total_files = len(self.files_to_process)
            
            for i, file_path in enumerate(self.files_to_process):
                if not self._is_running:
                    break
                    
                # Update progress
                percent = int((i / total_files) * 100)
                self.progress.emit(percent, f"Processing {file_path.name}...")
                
                # Process based on file type
                try:
                    output_path = None
                    
                    if file_path.suffix.lower() == '.pdf':
                        # Use Azure Document Intelligence for PDFs
                        self.logger.info(f"Processing PDF: {file_path}")
                        json_path, md_path = process_pdf_with_azure(
                            str(file_path),
                            str(self.output_dir),
                            endpoint=self.azure_di_endpoint,
                            key=self.azure_di_key
                        )
                        output_path = md_path
                        
                    elif file_path.suffix.lower() in ['.doc', '.docx']:
                        # Process Word documents
                        self.logger.info(f"Processing Word document: {file_path}")
                        output_path = process_docx_to_markdown(
                            str(file_path),
                            str(self.output_dir)
                        )
                        
                    elif file_path.suffix.lower() in ['.txt', '.md']:
                        # Process text files
                        self.logger.info(f"Processing text file: {file_path}")
                        output_path = process_txt_to_markdown(
                            str(file_path),
                            str(self.output_dir)
                        )
                    else:
                        raise ValueError(f"Unsupported file type: {file_path.suffix}")
                    
                    # Emit success
                    self.file_processed.emit(
                        file_path.name,
                        str(output_path) if output_path else "",
                        True,
                        ""
                    )
                    
                except Exception as e:
                    # Emit failure
                    self.logger.error(f"Failed to process {file_path.name}: {e}")
                    self.file_processed.emit(
                        file_path.name,
                        "",
                        False,
                        str(e)
                    )
            
            # Final progress update
            self.progress.emit(100, "Processing complete")
            self.finished.emit()
            
        except Exception as e:
            self.logger.error(f"Document processing failed: {e}")
            self.error.emit(str(e))
    
    def stop(self):
        """Stop processing."""
        self._is_running = False


class DocumentProcessStage(BaseStage):
    """Stage for processing imported documents."""
    
    def __init__(self, project):
        # Initialize thread as None
        self.processor_thread = None
        self.files_to_process = []
        self.processed_files = {}
        super().__init__(project)
        
    def setup_ui(self):
        """Create the document processing UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Header
        header = self._create_header()
        layout.addWidget(header)
        
        # Main content splitter
        splitter = QSplitter(Qt.Vertical)
        
        # Files table
        files_group = self._create_files_table()
        splitter.addWidget(files_group)
        
        # Processing log
        log_group = self._create_processing_log()
        splitter.addWidget(log_group)
        
        # Set initial splitter sizes (60% files, 40% log)
        splitter.setSizes([400, 300])
        layout.addWidget(splitter)
        
        # Progress section
        progress_widget = self._create_progress_section()
        layout.addWidget(progress_widget)
        
        # Action buttons
        buttons = self._create_action_buttons()
        layout.addWidget(buttons)
        
    def _create_header(self) -> QWidget:
        """Create the header section."""
        header = QWidget()
        layout = QVBoxLayout(header)
        
        title = QLabel("Process Documents")
        font = title.font()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        
        subtitle = QLabel("Convert PDFs, Word documents, and text files to markdown format")
        subtitle.setStyleSheet("color: #666;")
        layout.addWidget(subtitle)
        
        return header
        
    def _create_files_table(self) -> QWidget:
        """Create the files table."""
        group = QGroupBox("Documents to Process")
        layout = QVBoxLayout(group)
        
        # Create table
        self.files_table = QTableWidget()
        self.files_table.setColumnCount(4)
        self.files_table.setHorizontalHeaderLabels(["File Name", "Type", "Size", "Status"])
        
        # Configure table
        self.files_table.setAlternatingRowColors(True)
        self.files_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.files_table.horizontalHeader().setStretchLastSection(True)
        self.files_table.verticalHeader().setVisible(False)
        
        layout.addWidget(self.files_table)
        
        # Summary label
        self.summary_label = QLabel("No documents loaded")
        self.summary_label.setStyleSheet("color: #666; padding: 5px;")
        layout.addWidget(self.summary_label)
        
        return group
        
    def _create_processing_log(self) -> QWidget:
        """Create the processing log."""
        group = QGroupBox("Processing Log")
        layout = QVBoxLayout(group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                font-family: monospace;
                font-size: 12px;
                background-color: #f5f5f5;
            }
        """)
        layout.addWidget(self.log_text)
        
        return group
        
    def _create_progress_section(self) -> QWidget:
        """Create the progress section."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 5px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #4caf50;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("Ready to process documents")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        return widget
        
    def _create_action_buttons(self) -> QWidget:
        """Create action buttons."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        
        # Skip already processed checkbox
        from PySide6.QtWidgets import QCheckBox
        self.skip_processed_check = QCheckBox("Skip already processed files")
        self.skip_processed_check.setChecked(True)
        layout.addWidget(self.skip_processed_check)
        
        layout.addStretch()
        
        # Process button
        self.process_btn = QPushButton("Process All Documents")
        self.process_btn.setMinimumHeight(40)
        self.process_btn.setStyleSheet("""
            QPushButton {
                background-color: #4caf50;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.process_btn.clicked.connect(self._start_processing)
        layout.addWidget(self.process_btn)
        
        # Skip button (if all files are processed)
        self.skip_btn = QPushButton("Skip to Next Stage")
        self.skip_btn.setMinimumHeight(40)
        self.skip_btn.setVisible(False)
        self.skip_btn.clicked.connect(self._skip_stage)
        layout.addWidget(self.skip_btn)
        
        return widget
        
    def load_state(self):
        """Load documents from import stage."""
        if not self.project:
            return
            
        # Get imported files from previous stage
        import_data = self.project.get_stage_data('import')
        if import_data and 'imported_files' in import_data:
            self.files_to_process = [Path(f) for f in import_data['imported_files']]
            self._populate_files_table()
            
        # Check for already processed files
        self._check_processed_files()
        
    def _populate_files_table(self):
        """Populate the files table."""
        self.files_table.setRowCount(len(self.files_to_process))
        
        total_size = 0
        for i, file_path in enumerate(self.files_to_process):
            # File name
            self.files_table.setItem(i, 0, QTableWidgetItem(file_path.name))
            
            # File type
            file_type = file_path.suffix.upper()[1:] if file_path.suffix else "Unknown"
            self.files_table.setItem(i, 1, QTableWidgetItem(file_type))
            
            # File size
            if file_path.exists():
                size = file_path.stat().st_size
                total_size += size
                size_str = self._format_size(size)
                self.files_table.setItem(i, 2, QTableWidgetItem(size_str))
            else:
                self.files_table.setItem(i, 2, QTableWidgetItem("Not found"))
                
            # Status
            status_item = QTableWidgetItem("Pending")
            status_item.setForeground(Qt.gray)
            self.files_table.setItem(i, 3, status_item)
        
        # Update summary
        count = len(self.files_to_process)
        size_str = self._format_size(total_size)
        self.summary_label.setText(f"{count} document{'s' if count != 1 else ''} ({size_str} total)")
        
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
        
    def _check_processed_files(self):
        """Check which files have already been processed."""
        if not self.project:
            return
            
        output_dir = self.project.project_dir / "processed_documents"
        processed_count = 0
        
        for i, file_path in enumerate(self.files_to_process):
            # Check if markdown version exists
            base_name = file_path.stem
            md_path = output_dir / f"{base_name}.md"
            
            if md_path.exists():
                processed_count += 1
                status_item = self.files_table.item(i, 3)
                status_item.setText("Already processed")
                status_item.setForeground(Qt.darkGreen)
                self.processed_files[file_path.name] = str(md_path)
        
        # Show skip button if all files are processed
        if processed_count == len(self.files_to_process):
            self.skip_btn.setVisible(True)
            self.status_label.setText("All documents already processed")
            self._add_log("ℹ️ All documents have been processed previously.", "info")
            
    def _start_processing(self):
        """Start processing documents."""
        if self.processor_thread and self.processor_thread.isRunning():
            return
            
        # Determine which files to process
        files_to_process = []
        if self.skip_processed_check.isChecked():
            for file_path in self.files_to_process:
                if file_path.name not in self.processed_files:
                    files_to_process.append(file_path)
        else:
            files_to_process = self.files_to_process.copy()
            
        if not files_to_process:
            QMessageBox.information(
                self,
                "No Files to Process",
                "All documents have already been processed."
            )
            return
            
        # Disable UI during processing
        self.process_btn.setEnabled(False)
        self.skip_btn.setVisible(False)
        
        # Clear log
        self.log_text.clear()
        self._add_log(f"Starting document processing for {len(files_to_process)} files...", "info")
        
        # Create and start processor thread
        output_dir = self.project.project_dir / "processed_documents"
        output_dir.mkdir(exist_ok=True)
        
        self.processor_thread = DocumentProcessorThread(files_to_process, output_dir)
        self.processor_thread.progress.connect(self._on_progress)
        self.processor_thread.file_processed.connect(self._on_file_processed)
        self.processor_thread.finished.connect(self._on_processing_finished)
        self.processor_thread.error.connect(self._on_processing_error)
        self.processor_thread.start()
        
    def _on_progress(self, percent: int, message: str):
        """Handle progress update."""
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
        
    def _on_file_processed(self, filename: str, output_path: str, success: bool, error_msg: str):
        """Handle file processed signal."""
        # Find the file in the table
        for i in range(self.files_table.rowCount()):
            if self.files_table.item(i, 0).text() == filename:
                status_item = self.files_table.item(i, 3)
                
                if success:
                    status_item.setText("Processed ✓")
                    status_item.setForeground(Qt.darkGreen)
                    self.processed_files[filename] = output_path
                    self._add_log(f"✓ Successfully processed: {filename}", "success")
                else:
                    status_item.setText(f"Failed: {error_msg[:30]}...")
                    status_item.setForeground(Qt.red)
                    self._add_log(f"✗ Failed to process {filename}: {error_msg}", "error")
                break
                
    def _on_processing_finished(self):
        """Handle processing finished."""
        self.process_btn.setEnabled(True)
        self.status_label.setText("Processing complete")
        self._add_log("🎉 Document processing completed!", "success")
        
        # Mark stage as complete
        self.completed.emit({
            'processed_files': self.processed_files,
            'processing_time': datetime.now().isoformat()
        })
        
    def _on_processing_error(self, error_msg: str):
        """Handle processing error."""
        self.process_btn.setEnabled(True)
        self.status_label.setText("Processing failed")
        self._add_log(f"💥 Processing error: {error_msg}", "error")
        QMessageBox.critical(
            self,
            "Processing Error",
            f"Document processing failed:\n{error_msg}"
        )
        
    def _skip_stage(self):
        """Skip to next stage if all files are already processed."""
        self.completed.emit({
            'processed_files': self.processed_files,
            'skipped': True
        })
        
    def _add_log(self, message: str, level: str = "info"):
        """Add a message to the log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Color based on level
        if level == "error":
            color = "#d32f2f"
        elif level == "success":
            color = "#388e3c"
        elif level == "warning":
            color = "#f57c00"
        else:
            color = "#1976d2"
            
        html = f'<span style="color: #666;">[{timestamp}]</span> <span style="color: {color};">{message}</span>'
        self.log_text.append(html)
        
    def validate(self) -> tuple[bool, str]:
        """Check if stage can proceed."""
        if not self.files_to_process:
            return False, "No documents to process"
            
        # Check if any files have been processed
        if not self.processed_files:
            return False, "No documents have been processed yet"
            
        return True, ""
        
    def save_state(self):
        """Save processing results."""
        if self.project:
            self.project.save_stage_data('process', {
                'processed_files': self.processed_files,
                'processing_complete': True
            })
            
    def cleanup(self):
        """Clean up resources."""
        if self.processor_thread and self.processor_thread.isRunning():
            self.processor_thread.stop()
            self.processor_thread.wait()
        super().cleanup()