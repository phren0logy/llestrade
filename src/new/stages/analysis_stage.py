"""
Analysis stage for the new UI.
Handles document summarization using LLM providers.
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QTextEdit, QSplitter, QMessageBox, QAbstractItemView,
    QComboBox, QCheckBox, QFormLayout
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QFont, QTextCursor

from src.new.core.stage_manager import BaseStage
from src.config.app_config import get_available_providers_and_models, get_configured_llm_provider
from src.core.prompt_manager import PromptManager
from llm import create_provider
from llm.tokens import TokenCounter
from llm.chunking import ChunkingStrategy


class DocumentSummaryThread(QThread):
    """Worker thread for generating document summaries."""
    
    # Signals
    progress = Signal(int, str)  # percent, message
    file_summarized = Signal(str, str, bool, str)  # filename, summary_path, success, error_msg
    finished = Signal()
    error = Signal(str)
    status = Signal(str)  # status messages
    
    def __init__(self, 
                 files_to_summarize: List[Dict[str, str]], 
                 output_dir: Path,
                 subject_name: str,
                 subject_dob: str,
                 case_info: str,
                 provider_id: str,
                 model_name: str):
        super().__init__()
        self.files_to_summarize = files_to_summarize
        self.output_dir = output_dir
        self.subject_name = subject_name
        self.subject_dob = subject_dob
        self.case_info = case_info
        self.provider_id = provider_id
        self.model_name = model_name
        self._is_running = True
        self.logger = logging.getLogger(__name__)
        self.llm_provider = None
        
    def run(self):
        """Process all documents for summarization."""
        try:
            # Initialize LLM provider
            self.status.emit("Initializing LLM provider...")
            provider_info = get_configured_llm_provider(
                provider_id_override=self.provider_id,
                model_override=self.model_name
            )
            
            if not provider_info or not provider_info.get("provider"):
                raise Exception(f"Failed to initialize {self.provider_id} provider")
                
            self.llm_provider = provider_info["provider"]
            provider_label = provider_info.get("provider_label", self.provider_id)
            effective_model = provider_info.get("effective_model_name", self.model_name)
            
            self.status.emit(f"Using {provider_label} ({effective_model})")
            
            # Get prompt template
            prompt_manager = PromptManager()
            
            total_files = len(self.files_to_summarize)
            
            for i, file_info in enumerate(self.files_to_summarize):
                if not self._is_running:
                    break
                    
                file_path = Path(file_info['path'])
                
                # Update progress
                percent = int((i / total_files) * 100)
                self.progress.emit(percent, f"Summarizing {file_path.name}...")
                
                try:
                    # Read the markdown content
                    self.status.emit(f"Reading {file_path.name}...")
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Check if content needs chunking
                    estimated_tokens = len(content) // 4  # Rough estimate
                    context_window = TokenCounter.get_model_context_window(effective_model)
                    max_chunk_tokens = int(context_window * 0.65)  # Conservative limit
                    
                    if estimated_tokens > max_chunk_tokens:
                        # Process with chunking
                        self.status.emit(f"Document is large, using chunked processing...")
                        summary = self._process_with_chunks(content, file_path.name, max_chunk_tokens)
                    else:
                        # Process as single document
                        summary = self._process_single_document(content, file_path.name)
                    
                    if summary:
                        # Save summary
                        summary_filename = f"{file_path.stem}_summary.md"
                        summary_path = self.output_dir / summary_filename
                        
                        with open(summary_path, 'w', encoding='utf-8') as f:
                            f.write(summary)
                        
                        # Emit success
                        self.file_summarized.emit(
                            file_path.name,
                            str(summary_path),
                            True,
                            ""
                        )
                    else:
                        raise Exception("Empty summary generated")
                        
                except Exception as e:
                    # Emit failure
                    self.logger.error(f"Failed to summarize {file_path.name}: {e}")
                    self.file_summarized.emit(
                        file_path.name,
                        "",
                        False,
                        str(e)
                    )
            
            # Final progress update
            self.progress.emit(100, "Summarization complete")
            self.finished.emit()
            
        except Exception as e:
            self.logger.error(f"Document summarization failed: {e}")
            self.error.emit(str(e))
    
    def _process_single_document(self, content: str, filename: str) -> str:
        """Process a single document without chunking."""
        # Get prompt template
        prompt_manager = PromptManager()
        prompt_template = prompt_manager.get_template("document_summary_prompt")
        
        # Format the prompt
        prompt = prompt_template.format(
            subject_name=self.subject_name,
            subject_dob=self.subject_dob,
            case_info=self.case_info,
            document=content
        )
        
        # Generate summary
        self.status.emit(f"Generating summary for {filename}...")
        response = self.llm_provider.generate(
            prompt=prompt,
            model=self.model_name,
            temperature=0.1  # Low temperature for factual summaries
        )
        
        if response.get("success"):
            return response.get("content", "")
        else:
            raise Exception(response.get("error", "Unknown error"))
    
    def _process_with_chunks(self, content: str, filename: str, max_chunk_tokens: int) -> str:
        """Process a large document using chunking."""
        # Split content into chunks
        chunks = ChunkingStrategy.markdown_headers(
            text=content,
            max_tokens=max_chunk_tokens,
            overlap=2000 * 4  # Convert tokens to chars (approx)
        )
        
        self.status.emit(f"Document split into {len(chunks)} chunks")
        
        # Process each chunk
        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            self.status.emit(f"Processing chunk {i+1}/{len(chunks)}...")
            
            # Get prompt template for chunks
            prompt_manager = PromptManager()
            prompt_template = prompt_manager.get_template("document_summary_prompt")
            
            # Modify prompt for chunk processing
            chunk_prompt = f"""You are summarizing part {i+1} of {len(chunks)} from document: {filename}

{prompt_template}"""
            
            prompt = chunk_prompt.format(
                subject_name=self.subject_name,
                subject_dob=self.subject_dob,
                case_info=self.case_info,
                document=chunk
            )
            
            response = self.llm_provider.generate(
                prompt=prompt,
                model=self.model_name,
                temperature=0.1
            )
            
            if response.get("success"):
                chunk_summaries.append(response.get("content", ""))
            else:
                raise Exception(f"Failed to process chunk {i+1}: {response.get('error', 'Unknown error')}")
        
        # Combine chunk summaries
        if len(chunk_summaries) == 1:
            return chunk_summaries[0]
        else:
            # Create a final summary combining all chunks
            self.status.emit("Combining chunk summaries...")
            combined_chunks = "\n\n---\n\n".join(chunk_summaries)
            
            final_prompt = f"""Create a unified summary by combining these partial summaries of document: {filename}

## Partial Summaries:
{combined_chunks}

Please create a single, coherent summary that captures all key information from the document."""
            
            response = self.llm_provider.generate(
                prompt=final_prompt,
                model=self.model_name,
                temperature=0.1
            )
            
            if response.get("success"):
                return response.get("content", "")
            else:
                # Fallback to combined chunks if final summary fails
                return f"# Combined Summary for {filename}\n\n" + combined_chunks
    
    def stop(self):
        """Stop processing."""
        self._is_running = False


class AnalysisStage(BaseStage):
    """Stage for analyzing documents and generating summaries."""
    
    def __init__(self, project):
        # Initialize thread as None
        self.summary_thread = None
        self.files_to_analyze = []
        self.summarized_files = {}
        self.selected_provider = None
        self.selected_model = None
        super().__init__(project)
        
    def setup_ui(self):
        """Create the analysis UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Header
        header = self._create_header()
        layout.addWidget(header)
        
        # LLM configuration
        llm_config = self._create_llm_config()
        layout.addWidget(llm_config)
        
        # Main content splitter
        splitter = QSplitter(Qt.Vertical)
        
        # Files table
        files_group = self._create_files_table()
        splitter.addWidget(files_group)
        
        # Analysis log
        log_group = self._create_analysis_log()
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
        
        title = QLabel("Document Analysis")
        font = title.font()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        
        subtitle = QLabel("Generate AI-powered summaries of processed documents")
        subtitle.setStyleSheet("color: #666;")
        layout.addWidget(subtitle)
        
        return header
        
    def _create_llm_config(self) -> QWidget:
        """Create LLM configuration section."""
        group = QGroupBox("LLM Configuration")
        layout = QFormLayout(group)
        
        # Provider dropdown
        self.provider_combo = QComboBox()
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        layout.addRow("Provider:", self.provider_combo)
        
        # Model dropdown
        self.model_combo = QComboBox()
        layout.addRow("Model:", self.model_combo)
        
        # Load available providers
        self._load_llm_options()
        
        return group
        
    def _create_files_table(self) -> QWidget:
        """Create the files table."""
        group = QGroupBox("Documents to Analyze")
        layout = QVBoxLayout(group)
        
        # Create table
        self.files_table = QTableWidget()
        self.files_table.setColumnCount(4)
        self.files_table.setHorizontalHeaderLabels(["Document", "Size", "Status", "Summary"])
        
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
        
    def _create_analysis_log(self) -> QWidget:
        """Create the analysis log."""
        group = QGroupBox("Analysis Log")
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
                background-color: #2196f3;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("Ready to analyze documents")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        return widget
        
    def _create_action_buttons(self) -> QWidget:
        """Create action buttons."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        
        # Skip already summarized checkbox
        self.skip_summarized_check = QCheckBox("Skip already summarized files")
        self.skip_summarized_check.setChecked(True)
        layout.addWidget(self.skip_summarized_check)
        
        layout.addStretch()
        
        # Analyze button
        self.analyze_btn = QPushButton("Analyze All Documents")
        self.analyze_btn.setMinimumHeight(40)
        self.analyze_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196f3;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.analyze_btn.clicked.connect(self._start_analysis)
        layout.addWidget(self.analyze_btn)
        
        # Skip button (if all files are summarized)
        self.skip_btn = QPushButton("Skip to Next Stage")
        self.skip_btn.setMinimumHeight(40)
        self.skip_btn.setVisible(False)
        self.skip_btn.clicked.connect(self._skip_stage)
        layout.addWidget(self.skip_btn)
        
        return widget
        
    def _load_llm_options(self):
        """Load available LLM providers and models."""
        try:
            providers_and_models = get_available_providers_and_models()
            
            # Clear existing items
            self.provider_combo.clear()
            
            # Add providers
            for provider_info in providers_and_models:
                provider_id = provider_info["id"]
                provider_label = provider_info["label"]
                model = provider_info["model"]
                
                # Store provider info
                self.provider_combo.addItem(provider_info["display_name"], {
                    "provider_id": provider_id,
                    "model": model
                })
            
            # Select first provider if available
            if self.provider_combo.count() > 0:
                self.provider_combo.setCurrentIndex(0)
                self._on_provider_changed(self.provider_combo.currentText())
                
        except Exception as e:
            self.logger.error(f"Failed to load LLM options: {e}")
            
    def _on_provider_changed(self, provider_label: str):
        """Handle provider selection change."""
        if not provider_label:
            return
            
        # Get provider data
        provider_data = self.provider_combo.currentData()
        if not provider_data:
            return
            
        # Since we're using single model per provider from settings,
        # just update the model combo with the one model
        self.model_combo.clear()
        self.model_combo.addItem(provider_data["model"], provider_data["model"])
        self.model_combo.setCurrentIndex(0)
            
    def load_state(self):
        """Load processed documents from previous stage."""
        if not self.project:
            return
            
        # Get processed files from previous stage
        process_data = self.project.get_stage_data('process')
        if process_data and 'processed_files' in process_data:
            self.files_to_analyze = []
            for filename, filepath in process_data['processed_files'].items():
                self.files_to_analyze.append({
                    'name': filename,
                    'path': filepath
                })
            self._populate_files_table()
            
        # Check for already summarized files
        self._check_summarized_files()
        
    def _populate_files_table(self):
        """Populate the files table."""
        self.files_table.setRowCount(len(self.files_to_analyze))
        
        total_size = 0
        for i, file_info in enumerate(self.files_to_analyze):
            file_path = Path(file_info['path'])
            
            # Document name
            self.files_table.setItem(i, 0, QTableWidgetItem(file_info['name']))
            
            # File size
            if file_path.exists():
                size = file_path.stat().st_size
                total_size += size
                size_str = self._format_size(size)
                self.files_table.setItem(i, 1, QTableWidgetItem(size_str))
            else:
                self.files_table.setItem(i, 1, QTableWidgetItem("Not found"))
                
            # Status
            status_item = QTableWidgetItem("Pending")
            status_item.setForeground(Qt.gray)
            self.files_table.setItem(i, 2, status_item)
            
            # Summary placeholder
            self.files_table.setItem(i, 3, QTableWidgetItem(""))
        
        # Update summary
        count = len(self.files_to_analyze)
        size_str = self._format_size(total_size)
        self.summary_label.setText(f"{count} document{'s' if count != 1 else ''} ({size_str} total)")
        
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
        
    def _check_summarized_files(self):
        """Check which files have already been summarized."""
        if not self.project:
            return
            
        output_dir = self.project.project_dir / "summaries"
        summarized_count = 0
        
        for i, file_info in enumerate(self.files_to_analyze):
            # Check if summary exists
            file_path = Path(file_info['path'])
            summary_filename = f"{file_path.stem}_summary.md"
            summary_path = output_dir / summary_filename
            
            if summary_path.exists():
                summarized_count += 1
                status_item = self.files_table.item(i, 2)
                status_item.setText("Already summarized")
                status_item.setForeground(Qt.darkGreen)
                
                # Add to summarized files
                self.summarized_files[file_info['name']] = str(summary_path)
                
                # Update summary column
                summary_item = self.files_table.item(i, 3)
                summary_item.setText(summary_filename)
        
        # Show skip button if all files are summarized
        if summarized_count == len(self.files_to_analyze):
            self.skip_btn.setVisible(True)
            self.status_label.setText("All documents already summarized")
            self._add_log("ℹ️ All documents have been summarized previously.", "info")
            
    def _start_analysis(self):
        """Start analyzing documents."""
        if self.summary_thread and self.summary_thread.isRunning():
            return
            
        # Get selected provider and model
        provider_data = self.provider_combo.currentData()
        if not provider_data:
            QMessageBox.warning(self, "No Provider", "Please select an LLM provider.")
            return
            
        self.selected_provider = provider_data["provider_id"]
        self.selected_model = self.model_combo.currentData()
        
        if not self.selected_model:
            QMessageBox.warning(self, "No Model", "Please select a model.")
            return
            
        # Determine which files to analyze
        files_to_analyze = []
        if self.skip_summarized_check.isChecked():
            for file_info in self.files_to_analyze:
                if file_info['name'] not in self.summarized_files:
                    files_to_analyze.append(file_info)
        else:
            files_to_analyze = self.files_to_analyze.copy()
            
        if not files_to_analyze:
            QMessageBox.information(
                self,
                "No Files to Analyze",
                "All documents have already been summarized."
            )
            return
            
        # Get subject information
        metadata = self.project.metadata
        subject_name = metadata.subject_name or "Unknown Subject"
        subject_dob = metadata.subject_dob or "Unknown DOB"
        case_info = metadata.case_background or "No case background provided"
        
        # Disable UI during analysis
        self.analyze_btn.setEnabled(False)
        self.skip_btn.setVisible(False)
        self.provider_combo.setEnabled(False)
        self.model_combo.setEnabled(False)
        
        # Clear log
        self.log_text.clear()
        self._add_log(f"Starting document analysis for {len(files_to_analyze)} files...", "info")
        self._add_log(f"Using {self.provider_combo.currentText()} - {self.model_combo.currentText()}", "info")
        
        # Create and start summary thread
        output_dir = self.project.project_dir / "summaries"
        output_dir.mkdir(exist_ok=True)
        
        self.summary_thread = DocumentSummaryThread(
            files_to_analyze, 
            output_dir,
            subject_name,
            subject_dob,
            case_info,
            self.selected_provider,
            self.selected_model
        )
        self.summary_thread.progress.connect(self._on_progress)
        self.summary_thread.file_summarized.connect(self._on_file_summarized)
        self.summary_thread.finished.connect(self._on_analysis_finished)
        self.summary_thread.error.connect(self._on_analysis_error)
        self.summary_thread.status.connect(self._on_status_update)
        self.summary_thread.start()
        
    def _on_progress(self, percent: int, message: str):
        """Handle progress update."""
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
        
    def _on_status_update(self, message: str):
        """Handle status update from thread."""
        self._add_log(message, "info")
        
    def _on_file_summarized(self, filename: str, summary_path: str, success: bool, error_msg: str):
        """Handle file summarized signal."""
        # Find the file in the table
        for i in range(self.files_table.rowCount()):
            if self.files_table.item(i, 0).text() == filename:
                status_item = self.files_table.item(i, 2)
                summary_item = self.files_table.item(i, 3)
                
                if success:
                    status_item.setText("Summarized ✓")
                    status_item.setForeground(Qt.darkGreen)
                    self.summarized_files[filename] = summary_path
                    
                    # Update summary column
                    summary_filename = Path(summary_path).name
                    summary_item.setText(summary_filename)
                    
                    self._add_log(f"✓ Successfully summarized: {filename}", "success")
                else:
                    status_item.setText(f"Failed: {error_msg[:30]}...")
                    status_item.setForeground(Qt.red)
                    self._add_log(f"✗ Failed to summarize {filename}: {error_msg}", "error")
                break
                
    def _on_analysis_finished(self):
        """Handle analysis finished."""
        self.analyze_btn.setEnabled(True)
        self.provider_combo.setEnabled(True)
        self.model_combo.setEnabled(True)
        self.status_label.setText("Analysis complete")
        self._add_log("🎉 Document analysis completed!", "success")
        
        # Update project costs
        if self.project and self.selected_provider:
            # Note: Actual cost tracking will be implemented with Langfuse
            # For now, just track that we used this provider
            if hasattr(self.project, 'costs'):
                if self.selected_provider not in self.project.costs.by_provider:
                    self.project.costs.by_provider[self.selected_provider] = 0.0
                # Placeholder cost tracking
                self.project.costs.by_provider[self.selected_provider] += 0.01
                self.project.costs.by_stage['analysis'] = self.project.costs.by_stage.get('analysis', 0.0) + 0.01
                self.project.costs.total += 0.01
        
        # Mark stage as complete
        self.completed.emit({
            'summarized_files': self.summarized_files,
            'analysis_time': datetime.now().isoformat(),
            'provider': self.selected_provider,
            'model': self.selected_model
        })
        
    def _on_analysis_error(self, error_msg: str):
        """Handle analysis error."""
        self.analyze_btn.setEnabled(True)
        self.provider_combo.setEnabled(True)
        self.model_combo.setEnabled(True)
        self.status_label.setText("Analysis failed")
        self._add_log(f"💥 Analysis error: {error_msg}", "error")
        QMessageBox.critical(
            self,
            "Analysis Error",
            f"Document analysis failed:\n{error_msg}"
        )
        
    def _skip_stage(self):
        """Skip to next stage if all files are already summarized."""
        self.completed.emit({
            'summarized_files': self.summarized_files,
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
        
        # Scroll to bottom
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)
        
    def validate(self) -> tuple[bool, str]:
        """Check if stage can proceed."""
        if not self.files_to_analyze:
            return False, "No documents to analyze"
            
        # Check if any files have been summarized
        if not self.summarized_files:
            return False, "No documents have been summarized yet"
            
        return True, ""
        
    def save_state(self):
        """Save analysis results."""
        if self.project:
            self.project.save_stage_data('analysis', {
                'summarized_files': self.summarized_files,
                'analysis_complete': True,
                'provider': self.selected_provider,
                'model': self.selected_model
            })
            
    def cleanup(self):
        """Clean up resources."""
        if self.summary_thread and self.summary_thread.isRunning():
            self.summary_thread.stop()
            self.summary_thread.wait()
        super().cleanup()