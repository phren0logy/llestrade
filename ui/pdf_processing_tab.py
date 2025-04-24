"""
PDF Processing tab module for the Forensic Psych Report Drafter.
Handles PDF record extraction and conversion to markdown using Azure Document Intelligence.
"""

import os
import re
import tempfile
import time
from datetime import datetime

import fitz  # PyMuPDF
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE
from ui.base_tab import BaseTab
from ui.components.file_selector import FileSelector
from ui.components.status_panel import StatusPanel
from ui.components.workflow_indicator import WorkflowIndicator, WorkflowStep
from ui.workers.azure_processing_thread import AzureProcessingThread
from ui.workers.pdf_processing_thread import PDFProcessingThread


class PDFProcessingTab(BaseTab):
    """
    Tab for processing PDF records using Azure Document Intelligence.
    Converts PDFs to markdown format for later analysis.
    """

    def __init__(self, parent=None, status_bar=None):
        """Initialize the PDF Processing tab."""
        # Initialize key attributes to prevent 'no attribute' errors
        self.pdf_files = []
        self.output_directory = None
        self.processed_pdf_files = []
        self.file_list_text = None
        self.process_button = None
        self.workflow_indicator = None
        self._refreshing = False  # Flag to prevent recursion

        # Initialize state variables
        self.selected_directory = None
        self.temp_directory = None

        # Initialize the base tab with only parent and status_bar
        super().__init__(parent, status_bar)

        # Set the tab title separately if needed
        self.setWindowTitle("PDF Processing")

    def setup_ui(self):
        """Set up the UI components for the PDF Processing tab."""
        # Main layout
        main_layout = QVBoxLayout()
        
        # Create workflow indicator
        self.workflow_indicator = WorkflowIndicator()
        self.workflow_indicator.add_step(
            WorkflowStep.SELECT_FILES, "1. Select PDF Files", "Select PDF files to process"
        )
        self.workflow_indicator.add_step(
            WorkflowStep.PROCESS_PDFS, 
            "2. Process PDFs", 
            "Convert PDFs to markdown using Azure Document Intelligence"
        )
        
        main_layout.addWidget(self.workflow_indicator)
        
        # Create tabs
        self.setup_pdf_tab(main_layout)
        
        # Add status panel at the bottom
        self.status_panel = StatusPanel()
        main_layout.addWidget(self.status_panel)
        
        # Set the main layout
        self.layout.addLayout(main_layout)

    def setup_pdf_tab(self, layout):
        """Set up the PDF tab UI."""
        # Create a form layout for input fields
        form_layout = QFormLayout()

        # Create Azure credentials group
        azure_group = QGroupBox("Azure Document Intelligence Credentials")
        azure_layout = QFormLayout()

        # Add Azure endpoint input
        self.azure_endpoint_input = QLineEdit()
        self.azure_endpoint_input.setPlaceholderText(
            "Enter Azure Document Intelligence endpoint URL"
        )
        if os.getenv("AZURE_ENDPOINT"):
            self.azure_endpoint_input.setText(os.getenv("AZURE_ENDPOINT"))
        azure_layout.addRow(QLabel("Azure Endpoint:"), self.azure_endpoint_input)

        # Add Azure key input
        self.azure_key_input = QLineEdit()
        self.azure_key_input.setPlaceholderText(
            "Enter Azure Document Intelligence API key"
        )
        self.azure_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        if os.getenv("AZURE_KEY"):
            self.azure_key_input.setText(os.getenv("AZURE_KEY"))
        azure_layout.addRow(QLabel("Azure API Key:"), self.azure_key_input)

        # Add test connection button
        test_button_layout = QHBoxLayout()
        self.test_connection_button = QPushButton("Test Connection")
        self.test_connection_button.clicked.connect(self.test_azure_connection)
        test_button_layout.addWidget(self.test_connection_button)
        test_button_layout.addStretch()
        azure_layout.addRow("", test_button_layout)

        azure_group.setLayout(azure_layout)
        form_layout.addWidget(azure_group)

        # Create file selection group
        files_group = QGroupBox("PDF File Selection")
        files_layout = QVBoxLayout()

        # Add PDF folder selector
        self.pdf_folder_selector = FileSelector(
            title="PDF Directory",
            button_text="Select PDF Directory",
            file_mode=QFileDialog.FileMode.Directory,
            placeholder_text="Select a directory containing PDF files",
            callback=self.on_pdf_folder_selected,
        )
        files_layout.addWidget(self.pdf_folder_selector)

        # Add individual file selection
        self.select_files_button = QPushButton("Select PDF Files")
        self.select_files_button.clicked.connect(self.select_pdf_files)
        files_layout.addWidget(self.select_files_button)

        # Add selected files count label
        self.selected_files_label = QLabel("No PDF files selected")
        files_layout.addWidget(self.selected_files_label)

        files_group.setLayout(files_layout)
        form_layout.addWidget(files_group)

        # Create output directory selection
        output_group = QGroupBox("Output Directory")
        output_layout = QVBoxLayout()

        self.output_dir_selector = FileSelector(
            title="Output Directory",
            button_text="Select Output Directory",
            file_mode=QFileDialog.FileMode.Directory,
            placeholder_text="Select a directory for output files",
            callback=self.on_output_directory_selected,
        )
        output_layout.addWidget(self.output_dir_selector)

        output_group.setLayout(output_layout)
        form_layout.addWidget(output_group)

        # Add process button
        process_button_layout = QHBoxLayout()
        self.process_button = QPushButton("Process PDFs with Azure")
        self.process_button.setStyleSheet(
            """
            QPushButton {
                background-color: #2c7fb8;
                color: white;
                padding: 8px 12px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #4a98c9;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            """
        )
        self.process_button.setEnabled(False)
        self.process_button.clicked.connect(self.process_pdfs_with_azure)
        process_button_layout.addWidget(self.process_button)

        # Add layout to main layout
        layout.addLayout(form_layout)
        layout.addLayout(process_button_layout)

    def on_pdf_folder_selected(self, folder_path):
        """Handle selection of PDF folder."""
        if not folder_path:
            return

        # Set the selected folder and find PDFs
        self.selected_directory = folder_path
        self.pdf_files = self.find_pdf_files(folder_path)
        self.selected_files_label.setText(f"{len(self.pdf_files)} PDF files found in directory")

        # Update workflow state and enable processing button if appropriate
        self.workflow_indicator.update_status(
            WorkflowStep.SELECT_FILES, "complete" if self.pdf_files else "not_started"
        )
        self.check_ready_state()

    def select_pdf_files(self):
        """Open a file dialog for selecting multiple PDF files."""
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        file_dialog.setNameFilter("PDF Files (*.pdf)")
        
        if file_dialog.exec():
            # Get the selected files and update the PDF files list
            selected_files = file_dialog.selectedFiles()
            valid_files = [f for f in selected_files if f.lower().endswith(".pdf")]
            
            if not valid_files:
                self.show_status("No valid PDF files were selected.")
                return
            
            # Update the PDF files list
            self.pdf_files = valid_files
            self.selected_files_label.setText(f"{len(self.pdf_files)} PDF files selected")
            
            # Update workflow state and check if we're ready to process
            self.workflow_indicator.update_status(
                WorkflowStep.SELECT_FILES, "complete" if self.pdf_files else "not_started"
            )
            self.check_ready_state()
            
            # Show details in the status panel
            self.show_status(f"Selected {len(valid_files)} PDF files")
            self.status_panel.append_details("Selected PDF files:")
            for i, file_path in enumerate(valid_files, 1):
                self.status_panel.append_details(f"{i}. {os.path.basename(file_path)}")

    def find_pdf_files(self, directory):
        """Find all PDF files in the directory recursively."""
        pdf_files = []
        
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(".pdf"):
                    pdf_files.append(os.path.join(root, file))
        
        return pdf_files

    def on_output_directory_selected(self, directory):
        """Handle output directory selection."""
        if not directory:
            return
            
        self.output_directory = directory
        self.show_status(f"Output directory set: {directory}")
        self.check_ready_state()

    def check_ready_state(self):
        """Check if all requirements are met to enable the process button."""
        # Initialize with safe defaults if attributes don't exist yet
        if not hasattr(self, "pdf_files"):
            self.pdf_files = []
        if not hasattr(self, "output_directory"):
            self.output_directory = None

        # Enable the process button if we have PDF files and an output directory
        ready = bool(self.pdf_files) and self.output_directory is not None

        # Also check for Azure credentials for the process button
        azure_ready = ready and (
            (
                bool(self.azure_endpoint_input.text().strip())
                and bool(self.azure_key_input.text().strip())
            )
            or (os.getenv("AZURE_ENDPOINT") and os.getenv("AZURE_KEY"))
        )

        # Only enable the main process button if all requirements are met
        if hasattr(self, "process_button") and self.process_button is not None:
            self.process_button.setEnabled(azure_ready)

        # Update the workflow indicators (safely)
        if hasattr(self, "workflow_indicator") and self.workflow_indicator is not None:
            # Check if PDFs have been selected
            has_pdfs = bool(self.pdf_files)
            self.workflow_indicator.update_status(
                WorkflowStep.SELECT_FILES,
                "complete" if has_pdfs else "not_started",
            )
                
            # Check if PDFs have been processed
            pdfs_processed = False
            if hasattr(self, "output_directory") and self.output_directory:
                json_dir = os.path.join(self.output_directory, "json")
                markdown_dir = os.path.join(self.output_directory, "markdown")
                pdfs_processed = (
                    os.path.exists(json_dir) 
                    and os.path.exists(markdown_dir)
                    and bool(os.listdir(markdown_dir))
                )
            self.workflow_indicator.update_status(
                WorkflowStep.PROCESS_PDFS, 
                "complete" if pdfs_processed else "not_started"
            )

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

    def test_azure_connection(self):
        """Test the connection to Azure Document Intelligence."""
        # Get Azure credentials
        azure_endpoint = self.azure_endpoint_input.text().strip()
        azure_key = self.azure_key_input.text().strip()
        
        # Use environment variables if inputs are empty
        if not azure_endpoint:
            azure_endpoint = os.getenv("AZURE_ENDPOINT")
        if not azure_key:
            azure_key = os.getenv("AZURE_KEY")
            
        # Validate inputs
        if not azure_endpoint or not azure_key:
            QMessageBox.warning(
                self,
                "Missing Credentials",
                "Please enter both Azure endpoint and API key to test the connection.",
            )
            return
            
        # Create progress dialog
        progress_dialog = QProgressDialog(
            "Testing connection to Azure...",
            "Cancel",
            0,
            100,
            self,
        )
        progress_dialog.setWindowTitle("Azure Connection Test")
        progress_dialog.setValue(10)
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.show()
        
        # Import the correct test function
        from pdf_utils import test_azure_connection as azure_test_func
        
        # Test the connection
        try:
            progress_dialog.setValue(30)
            result = azure_test_func(azure_endpoint, azure_key)
            success = result.get('success', False)
            message = result.get('message', 'Unknown result')
            
            if not success:
                message = result.get('error', 'Unknown error')

            # Close progress dialog
            if progress_dialog:
                progress_dialog.close()
                
            # Show success or error message
            if success:
                QMessageBox.information(
                    self,
                    "Connection Successful",
                    f"Successfully connected to Azure Document Intelligence.\n\n{message}",
                )
                # Store the credentials in environment variables
                os.environ["AZURE_ENDPOINT"] = azure_endpoint
                os.environ["AZURE_KEY"] = azure_key
            else:
                QMessageBox.critical(
                    self,
                    "Connection Failed",
                    f"Failed to connect to Azure Document Intelligence.\n\nError: {message}",
                )
        except Exception as e:
            if progress_dialog:
                progress_dialog.close()
                
            QMessageBox.critical(
                self,
                "Connection Error",
                f"An error occurred while testing the connection:\n\n{str(e)}",
            )

    def process_pdfs_with_azure(self):
        """Process the selected PDF files with Azure Document Intelligence."""
        # Get the Azure credentials
        azure_endpoint = self.azure_endpoint_input.text().strip()
        azure_key = self.azure_key_input.text().strip()
        
        # Check for Azure credentials
        if not azure_endpoint or not azure_key:
            QMessageBox.critical(
                self,
                "Azure Credentials Missing",
                "Please enter your Azure Document Intelligence endpoint and API key.",
            )
            return
        
        # Filter files to only process those without existing outputs
        files_to_process = []
        skipped_files = []
        
        # Check each file against the output directory
        for pdf_path in self.pdf_files:
            basename = os.path.splitext(os.path.basename(pdf_path))[0]
            json_file = os.path.join(self.output_directory, "json", f"{basename}.json")
            md_file = os.path.join(self.output_directory, "markdown", f"{basename}.md")
            
            # Skip if both files already exist
            if os.path.exists(json_file) and os.path.exists(md_file):
                skipped_files.append({
                    "pdf": pdf_path,
                    "status": "skipped",
                    "json": json_file,
                    "markdown": md_file
                })
                self.status_panel.append_details(f"⚠ {os.path.basename(pdf_path)} - Skipped (already processed)")
            else:
                files_to_process.append(pdf_path)
        
        # Check if there are any files left to process
        if not files_to_process:
            QMessageBox.information(
                self,
                "No Files to Process",
                f"All {len(self.pdf_files)} PDF files have already been processed and exist in the output directory."
            )
            
            # Update workflow status
            self.workflow_indicator.update_status(WorkflowStep.PROCESS_PDFS, "complete")
            
            # Show skipped files in status
            self.status_panel.append_details(f"PDF processing complete: All {len(skipped_files)} files already processed")
            return
        
        # Create output directories if they don't exist
        os.makedirs(os.path.join(self.output_directory, "json"), exist_ok=True)
        os.makedirs(os.path.join(self.output_directory, "markdown"), exist_ok=True)
        
        # Create progress dialog
        progress_dialog = QProgressDialog(
            f"Processing {len(files_to_process)} PDF files...",
            "Cancel",
            0,
            len(files_to_process),
            self,
        )
        progress_dialog.setWindowTitle("Azure PDF Processing")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setValue(0)
        progress_dialog.show()
        
        # Disable UI elements
        self.process_button.setEnabled(False)
        
        # Create Azure thread
        self.azure_thread = AzureProcessingThread(
            files_to_process,
            self.output_directory,
            azure_endpoint,
            azure_key
        )
        
        # Connect signals
        self.azure_thread.progress_signal.connect(
            lambda processed, msg: self.update_azure_progress(processed, len(files_to_process), msg, progress_dialog)
        )
        self.azure_thread.finished_signal.connect(
            lambda results: self.azure_processing_finished(results, progress_dialog, skipped_files)
        )
        self.azure_thread.error_signal.connect(
            self.azure_processing_error
        )
        
        # Start the thread
        self.azure_thread.start()

    def update_azure_progress(self, processed, total, message, dialog):
        """Update the progress for Azure PDF processing."""
        if dialog and not dialog.wasCanceled():
            dialog.setValue(processed)
            dialog.setLabelText(message)
            
        # Update status panel
        self.status_panel.append_details(message)

    def azure_processing_finished(self, results, dialog, skipped_files=None):
        """Handle completion of Azure PDF processing."""
        # Close the progress dialog
        if dialog:
            dialog.close()
        
        # Initialize skipped_files if not provided
        if skipped_files is None:
            skipped_files = []
            
        # Check if results is a string and handle appropriately
        if isinstance(results, str):
            # Display the string result and set generic counts
            self.status_panel.append_details(f"PDF processing complete with message: {results}")
            self.workflow_indicator.update_status(WorkflowStep.PROCESS_PDFS, "complete")
            self.process_button.setEnabled(True)
            
            QMessageBox.information(
                self,
                "Processing Complete",
                f"PDF processing completed: {results}"
            )
            return
        
        # Combine skipped files with results
        if skipped_files:
            if "files" not in results:
                results["files"] = []
            results["files"].extend(skipped_files)
            results["skipped"] = results.get("skipped", 0) + len(skipped_files)
        
        # Get success and failure counts for dictionary results
        successful = sum(1 for r in results.get("files", []) if r.get("status") == "processed")
        failed = sum(1 for r in results.get("files", []) if r.get("status") == "failed")
        skipped = sum(1 for r in results.get("files", []) if r.get("status") == "skipped")
        total = successful + failed + skipped
            
        # Update workflow status
        if successful > 0 and failed == 0:
            self.workflow_indicator.update_status(WorkflowStep.PROCESS_PDFS, "complete")
        elif successful > 0:
            self.workflow_indicator.update_status(WorkflowStep.PROCESS_PDFS, "partial")
        else:
            self.workflow_indicator.update_status(WorkflowStep.PROCESS_PDFS, "error")
            
        # Re-enable UI elements
        self.process_button.setEnabled(True)
            
        # Show details in status panel
        self.status_panel.append_details(f"PDF processing complete: {successful} successful, {failed} failed, {skipped} skipped")
        for result in results.get("files", []):
            file_name = os.path.basename(result.get("pdf", "Unknown file"))
            if result.get("status") == "processed":
                self.status_panel.append_details(f"✓ {file_name} - Successfully processed")
            elif result.get("status") == "skipped":
                self.status_panel.append_details(f"⚠ {file_name} - Skipped (already processed)")
            else:
                error = result.get("error", "Unknown error")
                self.status_panel.append_details(f"❌ {file_name} - Failed: {error}")
            
        # Show completion message
        QMessageBox.information(
            self,
            "Processing Complete",
            f"Processed {total} PDF files with Azure Document Intelligence.\n\n"
            f"Successfully processed: {successful}\n"
            f"Failed: {failed}\n"
            f"Skipped: {skipped}\n\n"
            f"Output directory: {self.output_directory}"
        )

    def azure_processing_error(self, error):
        """Handle error in Azure PDF processing."""
        # Update workflow status
        self.workflow_indicator.update_status(WorkflowStep.PROCESS_PDFS, "error")
        
        # Re-enable UI elements
        self.process_button.setEnabled(True)
        
        # Show error message
        self.status_panel.append_details(f"Error processing PDFs: {error}")
        
        QMessageBox.critical(
            self,
            "Azure Processing Error",
            f"An error occurred during Azure PDF processing:\n\n{error}"
        )
