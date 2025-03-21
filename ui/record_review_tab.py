"""
Record Review tab module for the Forensic Psych Report Drafter.
Handles PDF record review and analysis functionality.
"""

import os
import tempfile
import fitz  # PyMuPDF
import shutil
import json
import time
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.base_tab import BaseTab
from ui.components.workflow_indicator import WorkflowIndicator
from ui.components.status_panel import StatusPanel
from ui.components.results_viewer import ResultsViewer
from ui.components.file_selector import FileSelector
from ui.workers.pdf_processing_thread import PDFProcessingThread
from ui.workers.azure_processing_thread import AzureProcessingThread
from ui.workers.llm_summary_thread import LLMSummaryThread
from ui.workers.integrated_analysis_thread import IntegratedAnalysisThread
from config import DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE, DEFAULT_TIMEOUT


class RecordReviewTab(BaseTab):
    """
    Tab for reviewing PDF records and generating analysis.
    Provides UI for entering case information, selecting files, and setting output location.
    """

    def __init__(self, parent=None, status_bar=None):
        """Initialize the Record Review tab."""
        # Initialize state variables
        self.selected_directory = None
        self.output_directory = None
        self.pdf_files = []
        self.processed_pdf_files = []
        self.temp_directory = None

        # Initialize the base tab
        super().__init__(parent, status_bar)

    def setup_ui(self):
        """Set up the UI components for the Record Review tab."""
        # Main layout is the vertical box layout from the base class

        # Create a workflow indicator at the top
        self.workflow_indicator = WorkflowIndicator(
            "Processing Workflow", 
            ["1. Select Files", "2. Process Files", "3. Integration"]
        )
        self.layout.addWidget(self.workflow_indicator)

        # Create tabbed interface for organizing content
        self.create_tabbed_interface()

        # Add status panel for feedback
        self.status_panel = StatusPanel("Processing Status")
        self.layout.addWidget(self.status_panel)

        # Add the file tree and results viewer
        self.results_viewer = ResultsViewer(
            header_labels=["Files", "Status", "Size"],
            placeholder_text="PDF files will be listed here after directory selection"
        )
        self.results_viewer.item_selected.connect(self.on_file_tree_item_clicked)
        self.layout.addWidget(self.results_viewer)

    def create_tabbed_interface(self):
        """Create a tabbed interface to organize the UI components."""
        from PyQt6.QtWidgets import QTabWidget

        self.tabs = QTabWidget()

        # Create tabs for different sections
        input_tab = QWidget()
        processing_tab = QWidget()
        results_tab = QWidget()

        # Set up the different tabs
        self.setup_input_tab(input_tab)
        self.setup_processing_tab(processing_tab)
        self.setup_results_tab(results_tab)

        # Add the tabs to the tab widget
        self.tabs.addTab(input_tab, "1. Input Information")
        self.tabs.addTab(processing_tab, "2. Processing")
        self.tabs.addTab(results_tab, "3. Results")

        # Connect tab changed signal to update UI
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # Add the tab widget to the main layout
        self.layout.addWidget(self.tabs)

    def setup_input_tab(self, tab):
        """Set up the input tab with selection buttons for PDF files and output directory."""
        layout = QVBoxLayout()
        
        # Add subject name input
        subject_group = QGroupBox("Subject Information")
        subject_layout = QFormLayout()
        
        # Add subject name field
        self.subject_input = QLineEdit()
        self.subject_input.setPlaceholderText("Enter the subject's name")
        subject_layout.addRow("Subject Name:", self.subject_input)
        
        # Add case information field
        self.case_info_input = QTextEdit()
        self.case_info_input.setPlaceholderText("Enter case information")
        self.case_info_input.setMaximumHeight(100)
        subject_layout.addRow("Case Information:", self.case_info_input)
        
        subject_group.setLayout(subject_layout)
        layout.addWidget(subject_group)

        # Add PDF directory selector
        self.pdf_selector = FileSelector(
            title="PDF File Selection",
            button_text="Select PDF Files",
            file_mode=QFileDialog.FileMode.ExistingFiles,
            file_filter="PDF Files (*.pdf)",
            placeholder_text="No PDF files selected",
            callback=self.on_pdf_files_selected
        )
        layout.addWidget(self.pdf_selector)

        # Add output directory selector
        self.output_selector = FileSelector(
            title="Output Directory",
            button_text="Select Output Directory",
            file_mode=QFileDialog.FileMode.Directory,
            placeholder_text="No output directory selected",
            callback=self.on_output_directory_selected
        )
        layout.addWidget(self.output_selector)

        # Set the layout for the tab
        tab.setLayout(layout)

    def setup_processing_tab(self, tab):
        """Set up the UI components for the Processing tab."""
        layout = QVBoxLayout()

        # Create Azure credentials group
        azure_group = QGroupBox("Azure Document Intelligence Credentials")
        azure_layout = QFormLayout()

        # Add help text
        help_label = QLabel(
            "Enter your Azure Document Intelligence credentials to enable document processing."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #666;")
        azure_layout.addRow(help_label)

        # Add Azure endpoint field
        self.azure_endpoint_label = QLabel("Endpoint:")
        self.azure_endpoint_input = QLineEdit()
        self.azure_endpoint_input.setPlaceholderText(
            "Enter Azure Document Intelligence endpoint"
        )
        self.azure_endpoint_input.setToolTip(
            "The endpoint URL for your Azure Document Intelligence resource"
        )
        azure_layout.addRow(self.azure_endpoint_label, self.azure_endpoint_input)

        # Add Azure API key field
        self.azure_key_label = QLabel("API Key:")
        self.azure_key_input = QLineEdit()
        self.azure_key_input.setPlaceholderText(
            "Enter Azure Document Intelligence API key"
        )
        self.azure_key_input.setToolTip(
            "Your Azure Document Intelligence API key (will be masked for security)"
        )
        self.azure_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        azure_layout.addRow(self.azure_key_label, self.azure_key_input)

        # Use environment variables if available
        if os.getenv("AZURE_ENDPOINT"):
            self.azure_endpoint_input.setText(os.getenv("AZURE_ENDPOINT"))
        if os.getenv("AZURE_KEY"):
            self.azure_key_input.setText(os.getenv("AZURE_KEY"))

        azure_group.setLayout(azure_layout)
        layout.addWidget(azure_group)

        # Create processing buttons group with cards for each processing step
        operations_group = QGroupBox("Processing Operations")
        operations_layout = QVBoxLayout()

        # Add button cards for processing steps - PDF Processing
        pdf_process_card = QGroupBox("Step 1: Document Preparation")
        pdf_process_layout = QVBoxLayout()

        self.process_button = QPushButton("Process PDF Records")
        self.process_button.setIcon(
            self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogStart)
        )
        self.process_button.setToolTip(
            "Split and prepare PDF files for further processing"
        )
        self.process_button.clicked.connect(self.process_records)
        self.process_button.setEnabled(False)
        pdf_process_layout.addWidget(self.process_button)

        pdf_description = QLabel(
            "Splits large PDFs into smaller chunks for more effective processing."
        )
        pdf_description.setWordWrap(True)
        pdf_description.setStyleSheet("color: #666;")
        pdf_process_layout.addWidget(pdf_description)

        pdf_process_card.setLayout(pdf_process_layout)
        operations_layout.addWidget(pdf_process_card)

        # Azure Processing
        azure_process_card = QGroupBox("Step 2: Document Analysis")
        azure_process_layout = QVBoxLayout()

        self.azure_process_button = QPushButton("Process with Azure")
        self.azure_process_button.setIcon(
            self.style().standardIcon(self.style().StandardPixmap.SP_BrowserReload)
        )
        self.azure_process_button.setToolTip(
            "Extract text from PDFs using Azure Document Intelligence"
        )
        self.azure_process_button.clicked.connect(self.process_with_azure)
        self.azure_process_button.setEnabled(False)
        azure_process_layout.addWidget(self.azure_process_button)

        azure_description = QLabel(
            "Uses Azure Document Intelligence to extract text content from PDFs."
        )
        azure_description.setWordWrap(True)
        azure_description.setStyleSheet("color: #666;")
        azure_process_layout.addWidget(azure_description)

        azure_process_card.setLayout(azure_process_layout)
        operations_layout.addWidget(azure_process_card)

        # LLM Summarization
        summarization_card = QGroupBox("Step 3: Document Summarization")
        summarization_layout = QVBoxLayout()

        self.llm_process_button = QPushButton("Summarize with LLM")
        self.llm_process_button.setIcon(
            self.style().standardIcon(
                self.style().StandardPixmap.SP_FileDialogDetailedView
            )
        )
        self.llm_process_button.setToolTip(
            "Generate summaries of extracted text using Claude AI"
        )
        self.llm_process_button.clicked.connect(self.summarize_with_llm)
        self.llm_process_button.setEnabled(False)
        summarization_layout.addWidget(self.llm_process_button)

        summarization_description = QLabel(
            "Uses Claude AI to create comprehensive summaries of each document."
        )
        summarization_description.setWordWrap(True)
        summarization_description.setStyleSheet("color: #666;")
        summarization_layout.addWidget(summarization_description)

        summarization_card.setLayout(summarization_layout)
        operations_layout.addWidget(summarization_card)

        operations_group.setLayout(operations_layout)
        layout.addWidget(operations_group)

        # Add a spacer at the bottom
        layout.addStretch()

        # Set the layout for the tab
        tab.setLayout(layout)

    def setup_results_tab(self, tab):
        """Set up the UI components for the Results tab."""
        layout = QVBoxLayout()

        # Create integration buttons group
        integration_group = QGroupBox("Integration Operations")
        integration_layout = QVBoxLayout()

        # Combine Summaries
        combine_card = QGroupBox("Step 4: Combine Summaries")
        combine_layout = QVBoxLayout()

        self.combine_button = QPushButton("Combine Summaries")
        self.combine_button.setIcon(
            self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogListView)
        )
        self.combine_button.setToolTip(
            "Merge all individual document summaries into a single file"
        )
        self.combine_button.clicked.connect(self.combine_summaries)
        self.combine_button.setEnabled(False)
        combine_layout.addWidget(self.combine_button)

        combine_description = QLabel(
            "Combines all individual document summaries into a single file for integrated analysis."
        )
        combine_description.setWordWrap(True)
        combine_description.setStyleSheet("color: #666;")
        combine_layout.addWidget(combine_description)

        combine_card.setLayout(combine_layout)
        integration_layout.addWidget(combine_card)

        # Generate Integrated Analysis
        integrate_card = QGroupBox("Step 5: Generate Integrated Analysis")
        integrate_layout = QVBoxLayout()

        self.integrate_button = QPushButton("Generate Integrated Analysis")
        self.integrate_button.setIcon(
            self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogInfoView)
        )
        self.integrate_button.setToolTip(
            "Generate a comprehensive analysis across all documents"
        )
        self.integrate_button.clicked.connect(self.generate_integrated_analysis)
        self.integrate_button.setEnabled(False)
        integrate_layout.addWidget(self.integrate_button)

        integrate_description = QLabel(
            "Creates a comprehensive analysis that combines information from all documents into a coherent narrative."
        )
        integrate_description.setWordWrap(True)
        integrate_description.setStyleSheet("color: #666;")
        integrate_layout.addWidget(integrate_description)

        integrate_card.setLayout(integrate_layout)
        integration_layout.addWidget(integrate_card)

        integration_group.setLayout(integration_layout)
        layout.addWidget(integration_group)

        # Add results viewer group
        viewer_group = QGroupBox("Results Preview")
        viewer_layout = QVBoxLayout()

        # Add file selector
        file_selector_layout = QHBoxLayout()
        file_selector_layout.addWidget(QLabel("Select a file to preview:"))

        self.file_selector = QComboBox()
        self.file_selector.setToolTip("Choose a file to preview in the viewer below")
        self.file_selector.currentIndexChanged.connect(self.update_preview)
        file_selector_layout.addWidget(self.file_selector)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setIcon(
            self.style().standardIcon(self.style().StandardPixmap.SP_BrowserReload)
        )
        self.refresh_button.clicked.connect(self.refresh_file_list)
        file_selector_layout.addWidget(self.refresh_button)

        viewer_layout.addLayout(file_selector_layout)

        # Add file preview area
        self.preview_area = QTextEdit()
        self.preview_area.setReadOnly(True)
        self.preview_area.setFont(QFont(DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE))
        self.preview_area.setMinimumHeight(200)
        self.preview_area.setPlaceholderText("Select a file to preview its contents")
        viewer_layout.addWidget(self.preview_area)

        viewer_group.setLayout(viewer_layout)
        layout.addWidget(viewer_group)

        # Set the layout for the tab
        tab.setLayout(layout)

    def on_tab_changed(self, index):
        """Handle tab change events to update UI state."""
        # Update button enablement based on the selected tab
        self.check_ready_state()

        # Update workflow indicators
        self.update_workflow_indicators()

    def on_pdf_files_selected(self, files):
        """Handle PDF file selection."""
        try:
            # Validate files
            valid_files = []
            for file_path in files:
                # Check if the file exists and is a PDF
                if os.path.exists(file_path) and file_path.lower().endswith('.pdf'):
                    valid_files.append(file_path)
                else:
                    self.show_status(f"Warning: {os.path.basename(file_path)} is not a valid PDF file or doesn't exist")
            
            self.pdf_files = valid_files
            
            # Update UI with success message if any valid files
            if valid_files:
                self.refresh_file_list()
                self.check_ready_state()
                self.workflow_indicator.update_status(0, [], f"{len(valid_files)} PDF files selected")
            else:
                self.show_status("No valid PDF files were selected")
        except Exception as e:
            self.show_status(f"Error selecting PDF files: {str(e)}")

    def on_output_directory_selected(self, directory):
        """Handle output directory selection."""
        self.output_directory = directory
        # Refresh the file list to show linked output files
        self.refresh_file_list()
        self.check_ready_state()

    def show_status(self, message):
        """Show a status message in the UI."""
        self.status_panel.update_summary(message)
        self.workflow_indicator.set_status_message(message)

    def append_status(self, message):
        """Append a message to the status details."""
        self.status_panel.append_details(message)

    def refresh_file_list(self):
        """Refresh the file selector with the current PDF files."""
        # Clear the tree
        self.results_viewer.clear_tree()
        
        if not self.pdf_files:
            return
            
        # Add files to the tree
        for file_path in self.pdf_files:
            try:
                # Extract the file name
                file_name = os.path.basename(file_path)
                
                # Check if file exists
                if not os.path.exists(file_path):
                    self.results_viewer.add_tree_item(
                        None, 
                        file_name, 
                        data=file_path, 
                        **{"1": "File not found", "2": "N/A"}
                    )
                    continue
                    
                file_size = os.path.getsize(file_path)
                file_size_str = f"{file_size / (1024*1024):.2f} MB"
                
                status = "Not processed"
                if file_path in self.processed_pdf_files:
                    status = "Processed"
                    
                self.results_viewer.add_tree_item(
                    None, 
                    file_name, 
                    data=file_path, 
                    **{"1": status, "2": file_size_str}
                )
            except Exception as e:
                # Handle any exceptions that might occur
                self.results_viewer.add_tree_item(
                    None, 
                    os.path.basename(file_path), 
                    data=file_path, 
                    **{"1": f"Error: {str(e)[:30]}...", "2": "N/A"}
                )

    def on_file_tree_item_clicked(self, item, column):
        """Handle file tree item click to show file details."""
        try:
            file_path = item.data(0, Qt.ItemDataRole.UserRole)
            if not file_path or not os.path.exists(file_path):
                self.results_viewer.set_content(f"File not found: {file_path}")
                return
                
            # Get file information
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            # Prepare text with file details
            details_text = f"File: {file_name}\n"
            details_text += f"Path: {file_path}\n"
            details_text += f"Size: {file_size / (1024*1024):.2f} MB\n\n"
            
            # If it's a PDF, get more info
            if file_path.lower().endswith('.pdf'):
                try:
                    doc = fitz.open(file_path)
                    page_count = len(doc)
                    details_text += f"Pages: {page_count}\n"
                    
                    # Check if file will need to be split
                    if page_count > 1750:
                        parts = (page_count - 1) // 1750 + 1
                        details_text += f"\n⚠️ This file will be split into {parts} parts of 1750 pages each\n"
                    
                    # Close the document to prevent resource leaks
                    doc.close()
                    
                    # Check for related files
                    if self.output_directory:
                        details_text += "\nRelated Files:\n"
                        
                        # Base name without extension
                        base_name = os.path.splitext(file_name)[0]
                        
                        # Check for markdown file
                        markdown_dir = os.path.join(self.output_directory, "markdown")
                        if os.path.exists(markdown_dir):
                            markdown_file = os.path.join(markdown_dir, f"{base_name}.md")
                            if os.path.exists(markdown_file):
                                md_size = os.path.getsize(markdown_file) / 1024  # KB
                                details_text += f"- Markdown: {base_name}.md ({md_size:.1f} KB)\n"
                        
                        # Check for JSON file
                        json_dir = os.path.join(self.output_directory, "json")
                        if os.path.exists(json_dir):
                            json_file = os.path.join(json_dir, f"{base_name}.json")
                            if os.path.exists(json_file):
                                json_size = os.path.getsize(json_file) / 1024  # KB
                                details_text += f"- JSON: {base_name}.json ({json_size:.1f} KB)\n"
                        
                        # Check for summary file
                        summaries_dir = os.path.join(self.output_directory, "summaries")
                        if os.path.exists(summaries_dir):
                            summary_file = os.path.join(summaries_dir, f"{base_name}_summary.md")
                            if os.path.exists(summary_file):
                                summary_size = os.path.getsize(summary_file) / 1024  # KB
                                details_text += f"- Summary: {base_name}_summary.md ({summary_size:.1f} KB)\n"
                except Exception as e:
                    details_text += f"\nError reading PDF: {str(e)}\n"
                
            self.results_viewer.set_content(details_text)
            
        except Exception as e:
            self.results_viewer.set_content(f"Error getting file details: {str(e)}")

    def check_ready_state(self):
        """Check if all requirements are met to enable the process button."""
        # Enable the process button if we have PDF files and an output directory
        ready = bool(self.pdf_files) and self.output_directory is not None
        self.process_button.setEnabled(ready)

        # Also check for Azure credentials for the Azure process button
        azure_ready = ready and (
            (
                bool(self.azure_endpoint_input.text().strip())
                and bool(self.azure_key_input.text().strip())
            )
            or (bool(os.getenv("AZURE_ENDPOINT")) and bool(os.getenv("AZURE_KEY")))
        )
        self.azure_process_button.setEnabled(azure_ready)

        # Also check for LLM processing
        llm_ready = ready and bool(self.processed_pdf_files)
        self.llm_process_button.setEnabled(llm_ready)

        # Check if summary files exist for combine button
        summaries_dir = (
            os.path.join(self.output_directory, "summaries")
            if self.output_directory
            else None
        )
        summaries_exist = bool(
            summaries_dir
            and os.path.exists(summaries_dir)
            and any(
                f.endswith("_summary.md")
                for f in os.listdir(summaries_dir)
                if os.path.isfile(os.path.join(summaries_dir, f))
            )
        )
        self.combine_button.setEnabled(summaries_exist)

        # Check if combined summary exists for integrate button
        combined_path = (
            os.path.join(self.output_directory, "combined_summary.md")
            if self.output_directory
            else None
        )
        combined_exists = bool(combined_path and os.path.exists(combined_path))
        self.integrate_button.setEnabled(combined_exists)

        # Update the workflow indicators
        self.update_workflow_indicators()

        if ready:
            self.show_status("Ready to process records")
        else:
            missing = []
            if not self.pdf_files:
                missing.append("PDF files")
            if self.output_directory is None:
                missing.append("output directory")

            if missing:
                self.show_status(f"Missing: {', '.join(missing)}")

    def update_workflow_indicators(self):
        """Update the workflow indicator based on the current state."""
        # Determine current step and completed steps
        current_step = 0
        completed_steps = []
        
        # Check if any PDFs are selected
        if self.pdf_files:
            current_step = 1
            
        # Check if files are processed
        if self.processed_pdf_files:
            completed_steps.append(0)
            current_step = 1
            
            # Check if we have Azure documents and/or summaries
            has_markdown = False
            has_summaries = False
            
            if self.output_directory:
                markdown_dir = os.path.join(self.output_directory, "markdown")
                summaries_dir = os.path.join(self.output_directory, "summaries")
                
                if os.path.exists(markdown_dir) and os.listdir(markdown_dir):
                    has_markdown = True
                
                if os.path.exists(summaries_dir) and os.listdir(summaries_dir):
                    has_summaries = True
            
            if has_markdown:
                completed_steps.append(1)
                current_step = 2
                
                if has_summaries:
                    # Check for integrated analysis
                    integrated_path = os.path.join(self.output_directory, "integrated_analysis.md")
                    if os.path.exists(integrated_path):
                        completed_steps.append(2)
        
        # Update the workflow indicator
        status_message = "Ready to process records" if self.pdf_files else "⏳ Waiting for input: Select PDF files and output directory"
        self.workflow_indicator.update_status(current_step, completed_steps, status_message)

    def process_records(self):
        """Process the selected PDF files."""
        # Get the subject name and case information
        subject_name = self.subject_input.text().strip()
        case_info = self.case_info_input.toPlainText().strip()

        # Validate required fields
        if not subject_name:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter the subject's name before processing.",
            )
            return

        if not case_info:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter case information before processing.",
            )
            return

        # Create and start the progress dialog
        progress_dialog = QProgressDialog(
            "Processing PDF files...", "Cancel", 0, 100, self
        )
        progress_dialog.setWindowTitle("Processing PDF Files")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.show()

        # Create a worker thread for PDF processing
        self.pdf_thread = PDFProcessingThread(self.pdf_files, self.output_directory)

        # Connect signals
        self.pdf_thread.progress_signal.connect(
            lambda pct, msg: self.update_progress(progress_dialog, pct, msg)
        )
        self.pdf_thread.finished_signal.connect(
            lambda files, temp_dir: self.on_pdf_processing_finished(
                files, temp_dir, progress_dialog
            )
        )
        self.pdf_thread.error_signal.connect(
            lambda error: self.on_pdf_processing_error(error, progress_dialog)
        )

        # Connect the canceled signal of the progress dialog to stop the thread
        progress_dialog.canceled.connect(self.pdf_thread.terminate)

        # Start the thread
        self.pdf_thread.start()

    def update_progress(self, dialog, percent, message):
        """Update the progress dialog and status details."""
        # Update the progress dialog
        dialog.setValue(percent)
        dialog.setLabelText(message)

        # Add the message to the status details
        timestamp = time.strftime("%H:%M:%S")
        self.status_details.append(f"[{timestamp}] {message}")

        # Also update the status summary
        self.status_summary.setText(f"Progress: {percent}% - {message}")

        # Process events to keep UI responsive
        from PyQt6.QtCore import QCoreApplication

        QCoreApplication.processEvents()

    def on_pdf_processing_finished(self, processed_files, temp_dir, dialog):
        """Handle completion of PDF processing."""
        # Close the progress dialog
        dialog.close()

        # Store the processed files and temporary directory
        self.processed_pdf_files = processed_files
        self.temp_directory = temp_dir

        # Update the UI
        if processed_files:
            # Update the text area
            self.file_list_text.clear()
            self.file_list_text.setPlainText(
                f"Processed {len(processed_files)} PDF files in {temp_dir}:\n\n"
            )
            for i, file_path in enumerate(processed_files, start=1):
                self.file_list_text.append(f"{i}. {os.path.basename(file_path)}")

            # Update tree view to show processed files
            self.update_file_tree_processed_files(processed_files, temp_dir)

            # Update UI state
            self.check_ready_state()

            # Update the workflow indicator
            self.update_workflow_indicators()

            # Update status
            self.show_status(f"Processed {len(processed_files)} PDF files")
            self.show_status_bar_message(
                f"Processed {len(processed_files)} PDF files successfully", 5000
            )

            # Move to the processing tab
            self.tabs.setCurrentIndex(1)  # Switch to Processing tab
        else:
            self.show_status("No PDF files were processed")
            self.show_status_bar_message("No PDF files were processed", 5000)

    def update_file_tree_processed_files(self, processed_files, temp_dir):
        """Update the file tree to show processed PDF files."""
        # Create a root item for processed PDFs if not exists
        processed_root = None
        for i in range(self.file_tree.topLevelItemCount()):
            if self.file_tree.topLevelItem(i).text(0) == "Processed PDFs":
                processed_root = self.file_tree.topLevelItem(i)
                break

        if not processed_root:
            processed_root = QTreeWidgetItem(self.file_tree, ["Processed PDFs"])
            processed_root.setIcon(
                0, self.style().standardIcon(self.style().StandardPixmap.SP_DirIcon)
            )

        processed_root.setExpanded(True)
        processed_root.setText(1, f"{len(processed_files)} files")
        processed_root.setText(2, f"Directory: {os.path.basename(temp_dir)}")

        # Clear existing items
        processed_root.takeChildren()

        # Add each processed file
        for file_path in processed_files:
            filename = os.path.basename(file_path)
            # Get file size
            try:
                file_size = os.path.getsize(file_path) / 1024  # KB
                size_str = f"{file_size:.1f} KB"
                page_count = get_pdf_page_count(file_path)
                page_info = f"{page_count} pages"
                file_item = QTreeWidgetItem(
                    processed_root, [filename, "Processed", f"{size_str} ({page_info})"]
                )
            except Exception as e:
                file_item = QTreeWidgetItem(
                    processed_root, [filename, "Processed", f"Error: {str(e)}"]
                )

            file_item.setIcon(
                0, self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon)
            )

            # Set a green background to indicate successful processing
            for col in range(3):
                file_item.setBackground(col, QColor(240, 255, 240))  # Light green

    def on_pdf_processing_error(self, error, dialog):
        """Handle errors in PDF processing."""
        # Close the progress dialog
        dialog.close()

        # Show an error message
        QMessageBox.critical(
            self,
            "PDF Processing Error",
            f"An error occurred during PDF processing:\n\n{error}",
        )

        # Update status
        self.show_status("PDF processing failed")
        self.show_status_bar_message("PDF processing failed", 5000)

    def process_with_azure(self):
        """Process the selected PDF files with Azure Document Intelligence."""
        # Get the subject name and case information
        subject_name = self.subject_input.text().strip()
        case_info = self.case_info_input.toPlainText().strip()

        # Get Azure credentials
        azure_endpoint = self.azure_endpoint_input.text().strip() or os.getenv(
            "AZURE_ENDPOINT"
        )
        azure_key = self.azure_key_input.text().strip() or os.getenv("AZURE_KEY")

        # Validate required fields
        if not subject_name:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter the subject's name before processing.",
            )
            return

        if not case_info:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter case information before processing.",
            )
            return

        if not (azure_endpoint and azure_key):
            QMessageBox.warning(
                self,
                "Missing Azure Credentials",
                "Please enter both Azure endpoint and API key before processing.",
            )
            return

        # If we don't have processed files, process them first
        if not self.processed_pdf_files:
            reply = QMessageBox.question(
                self,
                "Process PDFs First",
                "You need to split large PDFs before processing with Azure. Would you like to do that now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.process_records()
            else:
                return

        # Use processed files if available, otherwise use the original PDF files
        files_to_process = (
            self.processed_pdf_files if self.processed_pdf_files else self.pdf_files
        )

        # Create and start the progress dialog
        progress_dialog = QProgressDialog(
            "Processing with Azure Document Intelligence...", "Cancel", 0, 100, self
        )
        progress_dialog.setWindowTitle("Azure Document Processing")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.show()

        # Create a worker thread for Azure processing
        self.azure_thread = AzureProcessingThread(
            files_to_process, self.output_directory, azure_endpoint, azure_key
        )

        # Connect signals
        self.azure_thread.progress_signal.connect(
            lambda pct, msg: self.update_progress(progress_dialog, pct, msg)
        )
        self.azure_thread.finished_signal.connect(
            lambda results: self.on_azure_processing_finished(results, progress_dialog)
        )
        self.azure_thread.error_signal.connect(
            lambda error: self.on_azure_processing_error(error, progress_dialog)
        )

        # Connect the canceled signal of the progress dialog to stop the thread
        progress_dialog.canceled.connect(self.azure_thread.terminate)

        # Start the thread
        self.azure_thread.start()

    def on_azure_processing_finished(self, results, dialog):
        """Handle completion of Azure Document Intelligence processing."""
        # Close the progress dialog
        dialog.close()

        # Update the UI
        self.file_list_text.append("\n\n=== AZURE DOCUMENT INTELLIGENCE RESULTS ===\n")

        # Display summary
        self.file_list_text.append(
            f"Total files: {results['total']}\n"
            f"Processed: {results['processed']}\n"
            f"Skipped (already processed): {results['skipped']}\n"
            f"Failed: {results['failed']}\n\n"
        )

        # Display JSON and Markdown output directories
        json_dir = os.path.join(self.output_directory, "json")
        markdown_dir = os.path.join(self.output_directory, "markdown")

        self.file_list_text.append(
            f"JSON output directory: {json_dir}\n"
            f"Markdown output directory: {markdown_dir}\n\n"
        )

        # Display details for each file
        for i, file_info in enumerate(results["files"], start=1):
            pdf_name = os.path.basename(file_info["pdf"])
            status = file_info["status"]

            if status == "processed":
                json_path = os.path.relpath(file_info["json"], self.output_directory)
                markdown_path = os.path.relpath(
                    file_info["markdown"], self.output_directory
                )
                self.file_list_text.append(
                    f"{i}. {pdf_name} - Successfully processed\n"
                    f"   ✓ JSON: {json_path}\n"
                    f"   ✓ Markdown: {markdown_path}\n"
                )
            elif status == "skipped":
                json_path = os.path.relpath(file_info["json"], self.output_directory)
                markdown_path = os.path.relpath(
                    file_info["markdown"], self.output_directory
                )
                self.file_list_text.append(
                    f"{i}. {pdf_name} - Already processed (skipped)\n"
                    f"   ✓ JSON: {json_path}\n"
                    f"   ✓ Markdown: {markdown_path}\n"
                )
            else:  # failed
                self.file_list_text.append(
                    f"{i}. {pdf_name} - Failed to process\n"
                    f"   ✗ Error: {file_info['error']}\n"
                )

        # Show status message
        self.show_status(
            f"Azure processing complete. {results['processed']} files processed, {results['failed']} failed."
        )
        self.show_status_bar_message("Azure processing complete", 5000)

        # Show a message box with the results
        QMessageBox.information(
            self,
            "Azure Document Intelligence Complete",
            f"Successfully processed PDF files with Azure Document Intelligence:\n\n"
            f"• Total files: {results['total']}\n"
            f"• Processed: {results['processed']}\n"
            f"• Skipped: {results['skipped']}\n"
            f"• Failed: {results['failed']}\n\n"
            f"Output directories:\n"
            f"• JSON: {json_dir}\n"
            f"• Markdown: {markdown_dir}",
        )

    def on_azure_processing_error(self, error, dialog):
        """Handle errors in Azure Document Intelligence processing."""
        # Close the progress dialog
        dialog.close()

        # Show an error message
        QMessageBox.critical(
            self,
            "Azure Processing Error",
            f"An error occurred during Azure Document Intelligence processing:\n\n{error}",
        )

        # Update status
        self.show_status("Azure processing failed")
        self.show_status_bar_message("Azure processing failed", 5000)

    def summarize_with_llm(self):
        """Summarize the markdown files with LLM."""
        # Get the subject name and case information
        subject_name = self.subject_input.text().strip()
        case_info = self.case_info_input.toPlainText().strip()

        # Validate required fields
        if not subject_name:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter the subject's name before summarizing.",
            )
            return

        if not case_info:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter case information before summarizing.",
            )
            return

        # Get the markdown files
        markdown_dir = os.path.join(self.output_directory, "markdown")
        markdown_files = []

        for file in os.listdir(markdown_dir):
            if file.endswith(".md"):
                markdown_files.append(os.path.join(markdown_dir, file))

        # Create and start the progress dialog
        progress_dialog = QProgressDialog(
            "Summarizing with LLM...", "Cancel", 0, 100, self
        )
        progress_dialog.setWindowTitle("LLM Summarization")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.show()

        # Create a worker thread for LLM summarization
        self.llm_thread = LLMSummaryThread(
            markdown_files, self.output_directory, subject_name, case_info
        )

        # Connect signals
        self.llm_thread.progress_signal.connect(
            lambda pct, msg: self.update_progress(progress_dialog, pct, msg)
        )
        self.llm_thread.finished_signal.connect(
            lambda results: self.on_llm_summarization_finished(results, progress_dialog)
        )
        self.llm_thread.error_signal.connect(
            lambda error: self.on_llm_summarization_error(error, progress_dialog)
        )

        # Connect the canceled signal of the progress dialog to stop the thread
        progress_dialog.canceled.connect(self.llm_thread.terminate)

        # Start the thread
        self.llm_thread.start()

    def on_llm_summarization_finished(self, results, dialog):
        """Handle completion of LLM summarization."""
        # Close the progress dialog
        dialog.close()

        # Update the UI
        self.file_list_text.append("\n\n=== LLM SUMMARIZATION RESULTS ===\n")

        # Display summary
        self.file_list_text.append(
            f"Total files: {results['total']}\n"
            f"Processed: {results['processed']}\n"
            f"Skipped (already processed): {results['skipped']}\n"
            f"Failed: {results['failed']}\n\n"
        )

        # Display summaries directory
        summaries_dir = os.path.join(self.output_directory, "summaries")

        self.file_list_text.append(f"Summaries directory: {summaries_dir}\n\n")

        # Display details for each file
        for i, file_info in enumerate(results["files"], start=1):
            markdown_name = os.path.basename(file_info["markdown"])
            status = file_info["status"]

            if status == "processed":
                summary_path = os.path.relpath(
                    file_info["summary"], self.output_directory
                )
                self.file_list_text.append(
                    f"{i}. {markdown_name} - Successfully summarized\n"
                    f"   ✓ Summary: {summary_path}\n"
                )
            elif status == "skipped":
                summary_path = os.path.relpath(
                    file_info["summary"], self.output_directory
                )
                self.file_list_text.append(
                    f"{i}. {markdown_name} - Already summarized (skipped)\n"
                    f"   ✓ Summary: {summary_path}\n"
                )
            else:  # failed
                self.file_list_text.append(
                    f"{i}. {markdown_name} - Failed to summarize\n"
                    f"   ✗ Error: {file_info['error']}\n"
                )

        # Show status message
        self.show_status(
            f"LLM summarization complete. {results['processed']} files summarized, {results['failed']} failed."
        )
        self.show_status_bar_message("LLM summarization complete", 5000)

        # Show a message box with the results
        QMessageBox.information(
            self,
            "LLM Summarization Complete",
            f"Successfully summarized markdown files with LLM:\n\n"
            f"• Total files: {results['total']}\n"
            f"• Processed: {results['processed']}\n"
            f"• Skipped: {results['skipped']}\n"
            f"• Failed: {results['failed']}\n\n"
            f"Summaries directory:\n"
            f"• {summaries_dir}",
        )

    def on_llm_summarization_error(self, error, dialog):
        """Handle errors in LLM summarization."""
        # Close the progress dialog
        dialog.close()

        # Show an error message
        QMessageBox.critical(
            self,
            "LLM Summarization Error",
            f"An error occurred during LLM summarization:\n\n{error}",
        )

        # Update status
        self.show_status("LLM summarization failed")
        self.show_status_bar_message("LLM summarization failed", 5000)

    def combine_summaries(self):
        """Combine all summary markdown files into a single file."""
        if not self.output_directory:
            QMessageBox.warning(
                self,
                "Missing Output Directory",
                "Please set an output directory before combining summaries.",
            )
            return

        subject_name = self.subject_input.text().strip()
        if not subject_name:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter the subject's name before combining summaries.",
            )
            return

        # Get the summary files
        summaries_dir = os.path.join(self.output_directory, "summaries")
        if not os.path.exists(summaries_dir):
            QMessageBox.warning(
                self,
                "No Summaries Found",
                "No summary files found. Please generate summaries first.",
            )
            return

        # Find all summary files
        summary_files = []
        for file in os.listdir(summaries_dir):
            if file.endswith("_summary.md") and os.path.isfile(
                os.path.join(summaries_dir, file)
            ):
                summary_files.append(os.path.join(summaries_dir, file))

        if not summary_files:
            QMessageBox.warning(
                self,
                "No Summaries Found",
                "No summary files found. Please generate summaries first.",
            )
            return

        # Define the output file
        combined_file = os.path.join(self.output_directory, "combined_summary.md")

        try:
            # Combine the files
            with open(combined_file, "w", encoding="utf-8") as outfile:
                # Write the header
                outfile.write(f"# Combined Document Analysis for {subject_name}\n\n")
                outfile.write(
                    f"*Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n\n"
                )
                outfile.write(
                    "This file contains summaries from multiple documents. Each document is separated by a horizontal rule.\n\n"
                )
                outfile.write("---\n\n")

                # Write the content of each summary file
                for i, file_path in enumerate(summary_files):
                    file_name = os.path.basename(file_path)
                    with open(file_path, "r", encoding="utf-8") as infile:
                        content = infile.read()
                        outfile.write(f"{content}\n\n")

                    # Add a separator between files (except for the last one)
                    if i < len(summary_files) - 1:
                        outfile.write("---\n\n")

            # Update the UI
            self.file_list_text.append("\n\n=== COMBINED SUMMARY ===\n")
            self.file_list_text.append(
                f"Combined {len(summary_files)} summary files into: {os.path.basename(combined_file)}\n"
            )
            self.file_list_text.append(f"Output file: {combined_file}\n")

            # Enable the integrate button
            self.integrate_button.setEnabled(True)

            # Show a message
            QMessageBox.information(
                self,
                "Summaries Combined",
                f"Successfully combined {len(summary_files)} summary files into:\n{combined_file}",
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Combining Summaries",
                f"An error occurred while combining summaries:\n\n{str(e)}",
            )

    def generate_integrated_analysis(self):
        """Generate an integrated analysis using the combined summary file."""
        if not self.output_directory:
            QMessageBox.warning(
                self,
                "Missing Output Directory",
                "Please set an output directory before generating an integrated analysis.",
            )
            return

        # Get the subject name and case information
        subject_name = self.subject_input.text().strip()
        case_info = self.case_info_input.toPlainText().strip()

        # Validate required fields
        if not subject_name:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter the subject's name before generating an integrated analysis.",
            )
            return

        if not case_info:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter case information before generating an integrated analysis.",
            )
            return

        # Get the combined summary file
        combined_file = os.path.join(self.output_directory, "combined_summary.md")
        if not os.path.exists(combined_file):
            QMessageBox.warning(
                self,
                "No Combined Summary Found",
                "No combined summary file found. Please combine summaries first.",
            )
            return

        # Create and start the progress dialog
        progress_dialog = QProgressDialog(
            "Generating integrated analysis...", "Cancel", 0, 100, self
        )
        progress_dialog.setWindowTitle("Integrated Analysis")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.show()

        # Create a worker thread for integrated analysis
        self.integrated_thread = IntegratedAnalysisThread(
            combined_file, self.output_directory, subject_name, case_info
        )

        # Connect signals
        self.integrated_thread.progress_signal.connect(
            lambda pct, msg: self.update_progress(progress_dialog, pct, msg)
        )
        self.integrated_thread.finished_signal.connect(
            lambda result_file: self.on_integrated_analysis_finished(
                result_file, progress_dialog
            )
        )
        self.integrated_thread.error_signal.connect(
            lambda error: self.on_integrated_analysis_error(error, progress_dialog)
        )

        # Connect the canceled signal of the progress dialog to stop the thread
        progress_dialog.canceled.connect(self.integrated_thread.terminate)

        # Start the thread
        self.integrated_thread.start()

    def on_integrated_analysis_finished(self, result_file, dialog):
        """Handle completion of integrated analysis."""
        # Close the progress dialog
        dialog.close()

        # Update the UI
        self.file_list_text.append("\n\n=== INTEGRATED ANALYSIS RESULTS ===\n")
        self.file_list_text.append(
            f"Successfully generated integrated analysis: {os.path.basename(result_file)}\n"
        )
        self.file_list_text.append(f"Output file: {result_file}\n")

        # Show status message
        self.show_status("Integrated analysis complete.")
        self.show_status_bar_message("Integrated analysis complete", 5000)

        # Show a message box with the results
        QMessageBox.information(
            self,
            "Integrated Analysis Complete",
            f"Successfully generated integrated analysis:\n\n{result_file}",
        )

    def on_integrated_analysis_error(self, error, dialog):
        """Handle errors in integrated analysis."""
        # Close the progress dialog
        dialog.close()

        # Show an error message
        QMessageBox.critical(
            self,
            "Integrated Analysis Error",
            f"An error occurred during integrated analysis:\n\n{error}",
        )

        # Update status
        self.show_status("Integrated analysis failed")
        self.show_status_bar_message("Integrated analysis failed", 5000)

    def update_preview(self, index):
        """Update the preview with the selected file content."""
        if index < 0 or not hasattr(self, 'file_selector') or not self.file_selector:
            return
            
        selected_file = self.file_selector.currentText()
        if not selected_file:
            return
            
        try:
            # Load the selected file content
            file_path = os.path.join(self.output_dir, selected_file)
            if os.path.exists(file_path):
                content = read_file_content(file_path)
                self.preview_text.setPlainText(content)
            else:
                self.preview_text.setPlainText(f"File not found: {file_path}")
        except Exception as e:
            self.preview_text.setPlainText(f"Error loading file: {str(e)}")
