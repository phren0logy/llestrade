"""
Apply Prompt to PDF tab module for the Forensic Psych Report Drafter.
Handles sending prompts to PDFs using Claude's native PDF handling and extended thinking.
"""

import os
import time
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
)

from ui.base_tab import BaseTab
from ui.components.workflow_indicator import WorkflowIndicator
from ui.components.content_viewer import ContentViewer
from ui.components.file_selector import FileSelector
from ui.workers import PDFPromptThread
from config import DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE
from file_utils import read_file_content, read_file_preview


class TestingTab(BaseTab):
    """
    Tab for applying prompts to PDF files using Claude's native PDF handling.
    Provides UI for selecting prompts and PDFs for analysis.
    """
    
    def __init__(self, parent=None, status_bar=None):
        """Initialize the Apply Prompt to PDF tab."""
        # Initialize state variables
        self.current_pdf_path = None
        self.current_prompt_path = None
        self.processing_thread = None
        
        # Pre-initialize UI elements that will be referenced in check_ready_state
        self.process_button = None
        self.pdf_selector = None
        self.prompt_selector = None
        self.workflow_indicator = None
        
        # Initialize the base tab
        super().__init__(parent, status_bar)
    
    def setup_ui(self):
        """Set up the UI components for the Apply Prompt to PDF tab."""
        # Create workflow indicator
        self.workflow_indicator = WorkflowIndicator()
        self.workflow_indicator.add_step(1, "1. Select Files", "Select PDF and prompt files")
        self.workflow_indicator.add_step(2, "2. Process PDF", "Apply prompt to PDF")
        self.workflow_indicator.add_step(3, "3. Review Results", "Review the results")
        self.layout.addWidget(self.workflow_indicator)
        
        # Create file selectors for PDF and prompt
        file_selectors_layout = QHBoxLayout()
        
        # PDF file selector
        self.pdf_selector = FileSelector(
            title="PDF Document",
            button_text="Select PDF",
            file_mode=QFileDialog.FileMode.ExistingFile,
            file_filter="PDF Files (*.pdf)",
            placeholder_text="No PDF selected",
            callback=self.on_pdf_selected
        )
        file_selectors_layout.addWidget(self.pdf_selector)
        
        # Prompt file selector
        self.prompt_selector = FileSelector(
            title="Prompt Template",
            button_text="Select Prompt",
            file_mode=QFileDialog.FileMode.ExistingFile,
            file_filter="Text Files (*.txt *.md)",
            placeholder_text="No prompt selected",
            callback=self.on_prompt_selected
        )
        file_selectors_layout.addWidget(self.prompt_selector)
        
        self.layout.addLayout(file_selectors_layout)
        
        # Create content viewer (replacing results viewer)
        self.results_viewer = ContentViewer(
            placeholder_text="Select a PDF and prompt to begin analysis"
        )
        self.layout.addWidget(self.results_viewer)
        
        # Add action buttons
        button_layout = QHBoxLayout()
        
        # Add process button
        self.process_button = QPushButton("Apply Prompt to PDF")
        self.process_button.setEnabled(False)
        self.process_button.clicked.connect(self.process_pdf)
        button_layout.addWidget(self.process_button)
        
        self.layout.addLayout(button_layout)
        
        # Add progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.layout.addWidget(self.progress_bar)
        
        # Update UI state
        self.check_ready_state()
    
    def on_pdf_selected(self, file_path):
        """Handle PDF file selection."""
        self.current_pdf_path = file_path
        self.load_pdf_preview()
        self.check_ready_state()
        self.workflow_indicator.update_status(1, "complete")
        self.workflow_indicator.set_status_message("PDF selected")
    
    def on_prompt_selected(self, file_path):
        """Handle prompt file selection."""
        self.current_prompt_path = file_path
        self.load_prompt_preview()
        self.check_ready_state()
    
    def load_pdf_preview(self):
        """Load and display a preview of the selected PDF file."""
        if not self.current_pdf_path:
            return
        
        try:
            # Extract preview text from the PDF
            preview_result = read_file_preview(self.current_pdf_path, max_pages=2)
            
            # Handle different return types (string for PDFs, tuple for text files)
            if isinstance(preview_result, tuple):
                preview_text, is_truncated = preview_result
                truncation_notice = "\n\n[Preview truncated...]" if is_truncated else ""
                preview_text = f"{preview_text}{truncation_notice}"
            else:
                preview_text = preview_result
            
            # Display the preview
            self.results_viewer.set_markdown(
                f"Preview of {os.path.basename(self.current_pdf_path)}:\n\n{preview_text}"
            )
        except Exception as e:
            self.results_viewer.set_markdown(f"Error loading PDF preview: {str(e)}")
    
    def load_prompt_preview(self):
        """Load and display a preview of the selected prompt file."""
        if not self.current_prompt_path:
            return
        
        try:
            # Read the prompt file content
            prompt_content = read_file_content(self.current_prompt_path)
            
            # Display the preview
            self.results_viewer.set_markdown(
                f"Prompt from {os.path.basename(self.current_prompt_path)}:\n\n{prompt_content}"
            )
        except Exception as e:
            self.results_viewer.set_markdown(f"Error loading prompt: {str(e)}")
    
    def check_ready_state(self):
        """Check if all requirements are met to enable the process button."""
        # Check if UI elements are properly initialized
        if not all([hasattr(self, attr) for attr in ['process_button', 'pdf_selector', 'prompt_selector']]):
            return
            
        if None in [self.process_button, self.pdf_selector, self.prompt_selector]:
            return
        
        # Both PDF and prompt must be selected to process
        ready = (self.pdf_selector.selected_path is not None and 
                self.prompt_selector.selected_path is not None)
        self.process_button.setEnabled(ready)
        
        # Update workflow indicator if it exists
        if not hasattr(self, 'workflow_indicator') or self.workflow_indicator is None:
            return
            
        # Update the workflow indicator
        if ready:
            self.workflow_indicator.update_status(2, "complete")
            self.workflow_indicator.set_status_message("Ready to process")
        else:
            self.workflow_indicator.update_status(0, "not_started")
            self.workflow_indicator.set_status_message("Select PDF and prompt files")
    
    def process_pdf(self):
        """Process the selected PDF with the selected prompt using Claude."""
        if not self.current_pdf_path or not self.current_prompt_path:
            self.show_status("Please select both a PDF and a prompt file")
            return
        
        # Prompt user for output directory
        output_dir = QFileDialog.getExistingDirectory(
            self, 
            "Select Output Directory",
            os.path.dirname(self.current_pdf_path),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not output_dir:
            self.show_status("Operation cancelled")
            return
            
        # Update the workflow indicator
        self.workflow_indicator.update_status(1, [0], "Applying prompt to PDF...")
        
        # Reset the progress bar
        self.progress_bar.setValue(0)
        
        # Read the prompt file content
        try:
            prompt_text = read_file_content(self.current_prompt_path)
        except Exception as e:
            self.show_status(f"Error reading prompt file: {str(e)}")
            return
        
        # Create and start the processing thread
        self.processing_thread = PDFPromptThread(
            self.current_pdf_path, 
            prompt_text,
            output_dir
        )
        
        # Connect signals
        self.processing_thread.update_signal.connect(self.update_processing_status)
        self.processing_thread.progress_signal.connect(self.update_progress)
        self.processing_thread.finished_signal.connect(self.processing_completed)
        
        # Start processing
        self.processing_thread.start()
        
        # Disable buttons during processing
        self.process_button.setEnabled(False)
        
        # Show status
        self.show_status("Applying prompt to PDF... Please wait")
    
    def update_processing_status(self, message):
        """Update the status with a processing message."""
        # Just update the workflow indicator with the status message
        self.workflow_indicator.set_status_message(message)
    
    def update_progress(self, current, total):
        """Update the progress bar."""
        percentage = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(percentage)
    
    def processing_completed(self, result):
        """Handle completion of PDF processing."""
        # Re-enable buttons
        self.check_ready_state()
        
        if result["success"]:
            # Show the result in the results viewer
            content = result.get("content", "") or ""
            thinking = result.get("thinking", "") or ""
            
            content_summary = content[:1000] + "..." if len(content) > 1000 else content
            thinking_summary = thinking[:1000] + "..." if len(thinking) > 1000 else thinking
            
            display_text = f"# Analysis Complete\n\n"
            display_text += f"## Results Summary\n\n"
            
            # Safely access usage data
            usage = result.get("usage", {})
            input_tokens = usage.get("input_tokens", "N/A") 
            output_tokens = usage.get("output_tokens", "N/A")
            
            # Check if there was redacted thinking
            has_redacted_thinking = "[NOTE: Some of Claude's thinking process was flagged" in thinking
            
            display_text += f"- Input tokens: {input_tokens}\n"
            display_text += f"- Output tokens: {output_tokens}\n"
            
            if has_redacted_thinking:
                display_text += f"\n**Note:** Some of Claude's thinking process was redacted by safety systems. The thinking file contains a note about this.\n\n"
            
            # Safely access file paths
            content_file = result.get("content_file", "")
            thinking_file = result.get("thinking_file", "")
            
            if content_file:
                display_text += f"\n## Content Summary:\n\n```\n{content_summary}\n```\n\n"
                display_text += f"Full content saved to: `{content_file}`\n\n"
            
            if thinking_file:
                display_text += f"\n## Thinking Summary:\n\n```\n{thinking_summary}\n```\n\n"
                display_text += f"Full thinking process saved to: `{thinking_file}`\n\n"
                
            # Update the results display
            self.results_viewer.set_markdown(display_text)
            
            # Update status
            self.show_status("Processing complete")
            
            # Update workflow indicator
            self.workflow_indicator.update_status(2, "complete")
            self.workflow_indicator.set_status_message("Processing complete")
        else:
            # Show error
            error_message = result.get("error", "Unknown error occurred")
            display_text = f"# Error Occurred\n\n"
            display_text += f"```\n{error_message}\n```\n"
            self.results_viewer.set_markdown(display_text)
            self.show_status(f"Processing failed: {error_message}")
    
    def show_status(self, message):
        """Show a status message in the workflow indicator."""
        self.workflow_indicator.set_status_message(message)
        # Also call the base class method
        super().show_status(message)
