"""
Record Review tab module for the Forensic Psych Report Drafter.
Handles PDF record review and analysis functionality.
"""

import json
import os
import re
import shutil
import tempfile
import time
from datetime import datetime

import fitz  # PyMuPDF
from PySide6.QtCore import QCoreApplication, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE, DEFAULT_TIMEOUT
from ui.base_tab import BaseTab
from ui.components.file_selector import FileSelector
from ui.components.results_viewer import ResultsViewer
from ui.components.status_panel import StatusPanel
from ui.components.workflow_indicator import WorkflowIndicator, WorkflowStep
from ui.workers.azure_processing_thread import AzureProcessingThread
from ui.workers.integrated_analysis_thread import IntegratedAnalysisThread
from ui.workers.llm_summary_thread import LLMSummaryThread
from ui.workers.pdf_processing_thread import PDFProcessingThread


class RecordReviewTab(BaseTab):
    """
    Tab for reviewing PDF records and generating analysis.
    Provides UI for entering case information, selecting files, and setting output location.
    """

    def __init__(self, parent=None, status_bar=None):
        """Initialize the Record Review tab."""
        # Initialize key attributes to prevent 'no attribute' errors
        self.pdf_files = []
        self.output_directory = None
        self.processed_pdf_files = []
        self.file_list_text = None
        self.process_button = None
        self.llm_process_button = None
        self.combine_button = None
        self.integrate_button = None
        self.workflow_indicator = None
        self.markdown_directory = None
        self.results_output_directory = None
        self._refreshing = False  # Flag to prevent recursion

        # Initialize state variables
        self.selected_directory = None
        self.temp_directory = None

        # Initialize the base tab with only parent and status_bar
        super().__init__(parent, status_bar)

        # Set the tab title separately if needed
        self.setWindowTitle("Record Review")

        # setup_ui is already called in the parent class constructor
        # No need to call it again

    def setup_ui(self):
        """Set up the UI components for the Record Review tab."""
        # Main layout is the vertical box layout from the base class

        # Create a workflow indicator at the top
        self.workflow_indicator = WorkflowIndicator(
            "Processing Workflow",
            ["1. Select Files", "2. Process Files", "3. Integration"],
        )
        self.layout.addWidget(self.workflow_indicator)

        # Create tabs
        self.tabs = QTabWidget()
        self.create_tabbed_interface()

        # Add status panel for feedback
        self.status_panel = StatusPanel("Processing Status")
        self.layout.addWidget(self.status_panel)

        # Add the file tree and results viewer
        self.results_viewer = ResultsViewer(
            header_labels=["Files", "Status", "Size"],
            placeholder_text="PDF files will be listed here after directory selection",
        )
        self.results_viewer.item_selected.connect(self.on_file_tree_item_clicked)
        self.layout.addWidget(self.results_viewer)

        # Create a status bar for showing progress
        self.status_bar = QStatusBar()
        self.status_label = QLabel()
        self.status_bar.addWidget(self.status_label)

        # Add progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        self.status_bar.addPermanentWidget(self.progress_bar, 1)  # Give it stretch

        # Add components to main layout
        self.layout.addWidget(self.tabs)
        self.layout.addWidget(self.status_bar)

    def create_tabbed_interface(self):
        """Create a tabbed interface to organize the UI components."""
        from PySide6.QtWidgets import QTabWidget

        # Create tabs for different sections
        input_tab = QWidget()
        processing_tab = QWidget()

        # Set up the different tabs
        self.setup_input_tab(input_tab)
        self.setup_processing_tab(processing_tab)

        # Add the tabs to the tab widget
        self.tabs.addTab(input_tab, "1. Input Information")
        self.tabs.addTab(processing_tab, "2. Processing")

        # Connect tab changed signal to update UI
        self.tabs.currentChanged.connect(self.on_tab_changed)

    def setup_input_tab(self, tab):
        """Set up the input tab with selection buttons for PDF files and output directory."""
        layout = QVBoxLayout()

        # Create a subject information group
        subject_group = QGroupBox("Subject Information")
        subject_layout = QFormLayout()

        # Subject name input
        self.subject_label = QLabel("Subject Name:")
        self.subject_input = QLineEdit()
        self.subject_input.setPlaceholderText("Enter subject's name")
        subject_layout.addRow(self.subject_label, self.subject_input)

        # Subject DOB input
        self.dob_label = QLabel("Date of Birth:")
        self.dob_input = QLineEdit()
        self.dob_input.setPlaceholderText("MM/DD/YYYY")
        subject_layout.addRow(self.dob_label, self.dob_input)

        # Case information input
        self.case_info_label = QLabel("Case Information:")
        self.case_info_input = QTextEdit()
        self.case_info_input.setPlaceholderText(
            "Enter case details, referral information, and purpose of evaluation"
        )
        self.case_info_input.setMinimumHeight(100)
        subject_layout.addRow(self.case_info_label, self.case_info_input)

        subject_group.setLayout(subject_layout)
        layout.addWidget(subject_group)

        # Add PDF file selector
        self.pdf_selector = FileSelector(
            title="PDF File Selection",
            button_text="Select PDF Files",
            file_mode=QFileDialog.FileMode.ExistingFiles,
            file_filter="PDF Files (*.pdf)",
            placeholder_text="No PDF files selected",
            callback=self.on_pdf_files_selected,
        )
        layout.addWidget(self.pdf_selector)

        # Add folder selector
        self.pdf_folder_selector = FileSelector(
            title="PDF Folder Selection (Recursive)",
            button_text="Select Folder with PDFs",
            file_mode=QFileDialog.FileMode.Directory,
            placeholder_text="No folder selected",
            callback=lambda folder: (
                self.on_pdf_folder_selected(folder) if folder else None
            ),
        )
        layout.addWidget(self.pdf_folder_selector)

        # Add output directory selector
        self.output_selector = FileSelector(
            title="Output Directory",
            button_text="Select Output Directory",
            file_mode=QFileDialog.FileMode.Directory,
            placeholder_text="No output directory selected",
            callback=self.on_output_directory_selected,
        )
        layout.addWidget(self.output_selector)

        tab.setLayout(layout)

    def on_pdf_folder_selected(self, folder):
        """Safely handle folder selection for recursive PDF search."""
        try:
            if not folder:
                return

            # Show a status message
            self.show_status(
                f"Searching for PDF files in {folder} and its subdirectories..."
            )

            # Recursively find PDF files
            pdf_files = self.find_pdf_files_recursively(folder)

            if not pdf_files:
                self.show_status("No PDF files found in the selected folder.")
                return

            # Update the list of PDF files
            self.pdf_files = pdf_files

            # Show success message
            self.show_status(
                f"Found {len(pdf_files)} PDF files in {folder} and its subdirectories."
            )

            # Update UI components SAFELY
            if hasattr(self, "file_list_text") and self.file_list_text is not None:
                self.file_list_text.setPlainText(
                    f"Found {len(pdf_files)} PDF files:\n\n"
                )
                for i, file_path in enumerate(pdf_files[:20], 1):  # Show first 20 files
                    self.file_list_text.append(f"{i}. {os.path.basename(file_path)}")

                if len(pdf_files) > 20:
                    self.file_list_text.append(
                        f"\n... and {len(pdf_files) - 20} more files"
                    )

            # Refresh the file list and update ready state
            self.refresh_file_list()

            # Safely check ready state
            self.safely_check_ready_state()

        except Exception as e:
            # Log and show error
            import traceback

            error_msg = f"Error selecting PDF folder: {str(e)}"
            print(error_msg)
            print(traceback.format_exc())

            self.show_status(error_msg)

    def find_pdf_files_recursively(self, directory):
        """
        Find all PDF files in a directory and its subdirectories.

        Args:
            directory: Directory path to search

        Returns:
            List of paths to PDF files
        """
        pdf_files = []

        try:
            # Create a progress dialog for lengthy searches
            progress_dialog = QProgressDialog(
                f"Searching for PDF files in {os.path.basename(directory)}...",
                "Cancel",
                0,
                100,
                self,
            )
            progress_dialog.setWindowTitle("Searching Directory")
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setMinimumDuration(
                500
            )  # Only show for searches that take longer than 500ms
            progress_dialog.setValue(0)
            progress_dialog.show()

            # Get all files in the directory tree
            all_files = []
            for root, dirs, files in os.walk(directory):
                for file in files:
                    all_files.append((root, file))

                # Process events to keep the UI responsive
                QCoreApplication.processEvents()

                # Check if the user canceled
                if progress_dialog.wasCanceled():
                    self.show_status("PDF search canceled.")
                    return []

            # Update the progress dialog to have the correct maximum
            total_files = len(all_files)
            if total_files == 0:
                progress_dialog.close()
                return []

            progress_dialog.setMaximum(total_files)

            # Find PDF files
            for i, (root, file) in enumerate(all_files):
                # Update progress
                progress_dialog.setValue(i)
                progress_dialog.setLabelText(
                    f"Checking file {i+1}/{total_files}: {file}"
                )

                # Process events to keep the UI responsive
                QCoreApplication.processEvents()

                # Check if the user canceled
                if progress_dialog.wasCanceled():
                    self.show_status("PDF search canceled.")
                    return pdf_files

                # Check if it's a PDF
                if file.lower().endswith(".pdf"):
                    file_path = os.path.join(root, file)
                    pdf_files.append(file_path)

            # Close the progress dialog
            progress_dialog.close()

            # Show results
            self.show_status(
                f"Found {len(pdf_files)} PDF files in {directory} and subdirectories"
            )

        except Exception as e:
            self.show_status(f"Error searching for PDF files: {str(e)}")
            import traceback

            print(f"Error searching for PDFs: {str(e)}")
            print(traceback.format_exc())

        return pdf_files

    def safely_check_ready_state(self):
        """Safely check the ready state without crashing if UI components aren't initialized."""
        try:
            if hasattr(self, "check_ready_state"):
                self.check_ready_state()
        except Exception as e:
            import traceback

            print(f"Error in check_ready_state: {str(e)}")
            print(traceback.format_exc())

    def setup_processing_tab(self, tab):
        """Set up the UI components for the Processing tab."""
        try:
            layout = QVBoxLayout()

            # Create Azure Document Intelligence settings group
            azure_group = QGroupBox("Azure Document Intelligence Settings")
            azure_layout = QFormLayout()

            # Azure endpoint input
            self.azure_endpoint_label = QLabel("Azure Endpoint:")
            self.azure_endpoint_input = QLineEdit()
            self.azure_endpoint_input.setPlaceholderText(
                "https://your-resource-name.cognitiveservices.azure.com/"
            )
            self.azure_endpoint_input.setToolTip(
                "The endpoint URL for your Azure Document Intelligence resource"
            )
            azure_layout.addRow(self.azure_endpoint_label, self.azure_endpoint_input)

            # Azure key input
            self.azure_key_label = QLabel("Azure API Key:")
            self.azure_key_input = QLineEdit()
            self.azure_key_input.setPlaceholderText("Enter your Azure API key")
            self.azure_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.azure_key_input.setToolTip(
                "The API key for your Azure Document Intelligence resource"
            )
            azure_layout.addRow(self.azure_key_label, self.azure_key_input)

            # Try to get Azure credentials from environment variables
            if os.getenv("AZURE_ENDPOINT"):
                self.azure_endpoint_input.setText(os.getenv("AZURE_ENDPOINT"))
            if os.getenv("AZURE_KEY"):
                self.azure_key_input.setText(os.getenv("AZURE_KEY"))

            # Azure test connection button
            azure_buttons_layout = QHBoxLayout()
            self.test_azure_button = QPushButton("Test Azure Connection")

            # Use safe connection method with proper error handling
            self.test_azure_button.clicked.connect(self.safely_test_azure_connection)
            self.test_azure_button.setToolTip(
                "Test your Azure Document Intelligence connection"
            )
            azure_buttons_layout.addWidget(self.test_azure_button)

            # Unified process button
            self.process_button = QPushButton("Process PDF Files with Azure")

            # Use safe connection method with proper error handling
            self.process_button.clicked.connect(self.safely_process_pdfs_with_azure)
            self.process_button.setToolTip(
                "Process selected PDF files with Azure Document Intelligence"
            )
            azure_buttons_layout.addWidget(self.process_button)

            azure_layout.addRow("", azure_buttons_layout)

            azure_group.setLayout(azure_layout)
            layout.addWidget(azure_group)

            # Create processing steps
            steps_group = QGroupBox("Processing Steps")
            steps_layout = QVBoxLayout()

            # Add a label with instructions
            instructions_label = QLabel(
                "1. Set Azure credentials above\n"
                "2. Select PDF files in the Record Review tab\n"
                '3. Press "Process PDF Files with Azure" to extract text using Azure Document Intelligence\n'
                '4. Use "Summarize with LLM" after processing to generate summaries'
            )
            instructions_label.setWordWrap(True)
            instructions_label.setStyleSheet("color: #555;")
            steps_layout.addWidget(instructions_label)

            # Add LLM processing button
            llm_layout = QHBoxLayout()
            self.llm_process_button = QPushButton("Summarize with LLM")

            # Use safe connection method with proper error handling
            self.llm_process_button.clicked.connect(self.safely_summarize_with_llm)
            self.llm_process_button.setEnabled(
                False
            )  # Disabled until PDF processing is done
            llm_layout.addWidget(self.llm_process_button)
            steps_layout.addLayout(llm_layout)

            steps_group.setLayout(steps_layout)
            layout.addWidget(steps_group)

            # Add spacing and stretch
            layout.addStretch()

            # Set the layout on the tab
            tab.setLayout(layout)

        except Exception as e:
            # Log any errors that occur during processing tab setup
            import traceback

            print(f"Error setting up processing tab: {str(e)}")
            print(traceback.format_exc())

            # Show a basic layout with error message if something went wrong
            error_layout = QVBoxLayout()
            error_label = QLabel(f"Error setting up processing tab: {str(e)}")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: red;")
            error_layout.addWidget(error_label)
            tab.setLayout(error_layout)

    def setup_results_tab(self, tab):
        """Set up the UI components for the Results tab."""
        # This tab has been replaced by the AnalysisTab
        # This method is kept as a placeholder but not used
        layout = QVBoxLayout()

        # Add a label explaining that functionality has moved
        info_label = QLabel(
            "The analysis functionality has been moved to the dedicated Analysis tab.\n"
            "Please use the Analysis tab for summarizing documents, combining summaries,\n"
            "and generating integrated analysis."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(info_label)

        # Set the layout for the tab
        tab.setLayout(layout)

    def on_tab_changed(self, index):
        """Handle tab changes to update the UI as needed."""
        try:
            # Update UI based on the tab that was selected
            tab_name = self.tabs.tabText(index)
            self.show_status(f"Switched to {tab_name}")

            # Do any necessary updates for the specific tab
            if tab_name == "2. Processing":
                # Safely update the processing tab
                self.safely_update_processing_tab()

        except Exception as e:
            # Log any errors that occur during tab switching
            import traceback

            print(f"Error changing tabs: {str(e)}")
            print(traceback.format_exc())

            # Show error to user
            QMessageBox.critical(
                self,
                "Tab Change Error",
                f"An error occurred when switching tabs: {str(e)}",
            )

    def safely_update_processing_tab(self):
        """Safely update the processing tab UI without causing crashes."""
        try:
            # Make sure all required attributes are initialized
            if not hasattr(self, "process_button") or self.process_button is None:
                print("Warning: process_button is None, skipping enable/disable")
                return

            if not hasattr(self, "test_azure_button") or self.test_azure_button is None:
                print("Warning: test_azure_button is None, skipping enable/disable")
                return

            if (
                not hasattr(self, "llm_process_button")
                or self.llm_process_button is None
            ):
                print("Warning: llm_process_button is None, skipping enable/disable")
                return

            # Check if we have PDF files and an output directory
            pdf_files_selected = hasattr(self, "pdf_files") and bool(self.pdf_files)
            output_dir_selected = (
                hasattr(self, "output_directory") and self.output_directory
            )

            # Enable buttons based on current state
            if hasattr(self, "check_ready_state"):
                self.check_ready_state()

        except Exception as e:
            # Log any errors for debugging
            import traceback

            print(f"Error updating processing tab: {str(e)}")
            print(traceback.format_exc())

    def on_pdf_files_selected(self, files, recursive=False):
        """
        Handle PDF file selection.

        Args:
            files: List of selected file paths or single directory path
            recursive: If True, files is actually a directory to search recursively
        """
        try:
            # Ensure self.pdf_files is initialized as a list
            if not hasattr(self, "pdf_files"):
                self.pdf_files = []

            valid_files = []

            if recursive:
                # If recursive is True, files is actually a single directory path
                directory = files
                self.show_status(
                    f"Searching for PDF files in {directory} and subdirectories..."
                )
                valid_files = self.find_pdf_files_recursively(directory)
            else:
                # Regular file selection - filter for PDF files only
                for file_path in files:
                    if os.path.exists(file_path) and file_path.lower().endswith(".pdf"):
                        valid_files.append(file_path)
                    else:
                        self.show_status(
                            f"Warning: {os.path.basename(file_path)} is not a valid PDF file or doesn't exist"
                        )

            # Update the list of PDF files
            if valid_files:
                self.pdf_files = valid_files
                self.show_status(f"Selected {len(valid_files)} PDF files.")

                # Initialize file_list_text if needed
                if not hasattr(self, "file_list_text") or self.file_list_text is None:
                    # Create it but don't add to the layout yet
                    self.file_list_text = QTextEdit()
                    self.file_list_text.setReadOnly(True)
                    self.file_list_text.setFont(
                        QFont(DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE)
                    )

                # Update text display
                self.file_list_text.setPlainText(
                    f"Selected {len(valid_files)} PDF files:\n\n"
                )
                for i, file_path in enumerate(valid_files, 1):
                    self.file_list_text.append(f"{i}. {os.path.basename(file_path)}")

            # Refresh the file list
            self.refresh_file_list()

            # Make sure check_ready_state is defined before calling it
            if hasattr(self, "check_ready_state"):
                self.check_ready_state()

        except Exception as e:
            # Ensure error doesn't crash the application
            self.show_status(f"Error selecting PDF files: {str(e)}")
            # Initialize with empty list if there's an error
            self.pdf_files = []

            # Log the full error for debugging
            import traceback

            print(f"PDF selection error: {str(e)}")
            print(traceback.format_exc())

    def refresh_file_list(self):
        """This functionality has been moved to the AnalysisTab"""
        # Only defined as a stub since it might be called from other places
        pass

    def on_file_tree_item_clicked(self, item, column):
        """Handle file tree item click to show file details."""
        # Get the full path from the item data
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not file_path or not os.path.exists(file_path):
            return

        # Show basic file information
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        size_str = self.format_file_size(file_size)

        # Create text for file details
        details = f"=== FILE DETAILS ===\n"
        details += f"Name: {file_name}\n"
        details += f"Path: {file_path}\n"
        details += f"Size: {size_str}\n"

        # Get creation and modification times
        try:
            created_time = os.path.getctime(file_path)
            modified_time = os.path.getmtime(file_path)
            details += f"Created: {datetime.fromtimestamp(created_time).strftime('%Y-%m-%d %H:%M:%S')}\n"
            details += f"Modified: {datetime.fromtimestamp(modified_time).strftime('%Y-%m-%d %H:%M:%S')}\n"
        except Exception as e:
            details += f"Error getting file times: {str(e)}\n"

        details += "\n"

        # For PDF files, try to get page count and other metadata
        if file_path.lower().endswith(".pdf"):
            try:
                # Use PyMuPDF (fitz) to get PDF metadata
                with fitz.open(file_path) as pdf:
                    page_count = len(pdf)
                    details += f"Pages: {page_count}\n"

                    # Get basic metadata
                    metadata = pdf.metadata
                    if metadata:
                        details += "\nMetadata:\n"
                        for key, value in metadata.items():
                            if value:
                                details += f"  {key}: {value}\n"
            except Exception as e:
                details += f"Error reading PDF metadata: {str(e)}\n"

        # Check for processed versions (if they exist)
        if self.output_directory:
            # JSON version
            json_dir = os.path.join(self.output_directory, "json")
            base_name = os.path.splitext(file_name)[0]
            json_path = os.path.join(json_dir, f"{base_name}.json")

            if os.path.exists(json_path):
                details += f"\nProcessed with Azure Document Intelligence\n"
                details += f"  JSON: {json_path}\n"

            # Markdown version
            markdown_dir = os.path.join(self.output_directory, "markdown")
            markdown_path = os.path.join(markdown_dir, f"{base_name}.md")

            if os.path.exists(markdown_path):
                details += f"  Markdown: {markdown_path}\n"

            # Summary version
            summary_dir = os.path.join(self.output_directory, "summaries")
            summary_path = os.path.join(summary_dir, f"{base_name}_summary.md")

            if os.path.exists(summary_path):
                details += f"  Summary: {summary_path}\n"

        # Set the detail text
        detail_text = QTextEdit()
        detail_text.setReadOnly(True)
        detail_text.setFont(QFont(DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE))
        detail_text.setText(details)

        # Set the detail widget
        self.results_viewer.set_detail_widget(detail_text)

    def check_ready_state(self):
        """Check if we have the required components to proceed with processing."""
        # If output directory isn't set yet, skip checking
        if not hasattr(self, "output_directory"):
            self.output_directory = None

        # Update progress indicators
        if hasattr(self, "workflow_indicator") and self.workflow_indicator is not None:
            try:
                # Check if PDFs have been selected
                if hasattr(self, "pdf_files"):
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
                    "complete" if pdfs_processed else "not_started",
                )

                # Check if we have LLM summaries
                summaries_exist = False
                if (
                    hasattr(self, "results_output_directory")
                    and self.results_output_directory
                ):
                    summaries_dir = os.path.join(
                        self.results_output_directory, "summaries"
                    )
                    if os.path.exists(summaries_dir):
                        summaries_exist = bool(
                            [f for f in os.listdir(summaries_dir) if f.endswith(".md")]
                        )
                self.workflow_indicator.update_status(
                    WorkflowStep.SUMMARIZE_LLM,
                    "complete" if summaries_exist else "not_started",
                )

                # Check if we have a combined summary
                combined_exists = False
                if (
                    hasattr(self, "results_output_directory")
                    and self.results_output_directory
                ):
                    combined_file = os.path.join(
                        self.results_output_directory, "combined_summary.md"
                    )
                    combined_exists = os.path.exists(combined_file)
                self.workflow_indicator.update_status(
                    WorkflowStep.COMBINE_SUMMARIES,
                    "complete" if combined_exists else "not_started",
                )

                # Check if we have integrated analysis
                integrated_exists = False
                if (
                    hasattr(self, "results_output_directory")
                    and self.results_output_directory
                ):
                    integrated_file = os.path.join(
                        self.results_output_directory, "integrated_analysis.md"
                    )
                    integrated_exists = os.path.exists(integrated_file)
                self.workflow_indicator.update_status(
                    WorkflowStep.INTEGRATE_ANALYSIS,
                    "complete" if integrated_exists else "not_started",
                )

                # Update button states based on workflow state
                if hasattr(self, "process_button") and self.process_button is not None:
                    self.process_button.setEnabled(bool(has_pdfs))

                if (
                    hasattr(self, "llm_process_button")
                    and self.llm_process_button is not None
                ):
                    self.llm_process_button.setEnabled(bool(pdfs_processed))

                if hasattr(self, "combine_button") and self.combine_button is not None:
                    self.combine_button.setEnabled(bool(summaries_exist))

                if (
                    hasattr(self, "integrate_button")
                    and self.integrate_button is not None
                ):
                    self.integrate_button.setEnabled(bool(combined_exists))

            except Exception as e:
                print(f"Error in check_ready_state: {str(e)}")

    def update_workflow_indicators(self, status=None):
        """Update the workflow indicators based on the current status."""
        # Initialize with safe defaults if attributes don't exist yet
        if not hasattr(self, "pdf_files"):
            self.pdf_files = []
        if not hasattr(self, "output_directory"):
            self.output_directory = None

        # Update progress indicators
        if status:
            self.workflow_indicator.set_status_message(status)

        # Initialize variables
        current_step = 0
        completed_steps = []

        # Set step 1 (select) status
        if bool(self.pdf_files):
            completed_steps.append(0)  # Step 1 completed
            current_step = 1  # Move to step 2

        # Check if Azure credentials are available
        has_azure_creds = False
        try:
            has_azure_creds = (
                bool(self.azure_endpoint_input.text().strip())
                and bool(self.azure_key_input.text().strip())
            ) or (os.getenv("AZURE_ENDPOINT") and os.getenv("AZURE_KEY"))
        except (AttributeError, TypeError):
            pass

        # Set other workflow steps based on our state
        markdown_dir = (
            os.path.join(self.output_directory, "markdown")
            if self.output_directory
            else None
        )
        has_markdown = bool(
            markdown_dir
            and os.path.exists(markdown_dir)
            and any(
                f.endswith(".md")
                for f in os.listdir(markdown_dir)
                if os.path.isfile(os.path.join(markdown_dir, f))
            )
        )

        # Set states based on progress
        if has_markdown:
            completed_steps.append(1)  # Step 2 completed
            current_step = 2  # Move to step 3

        # Check for summaries
        summaries_dir = (
            os.path.join(self.output_directory, "summaries")
            if self.output_directory
            else None
        )
        has_summaries = bool(
            summaries_dir
            and os.path.exists(summaries_dir)
            and any(f.endswith(".md") for f in os.listdir(summaries_dir))
        )

        if has_summaries:
            completed_steps.append(2)  # Step 3 completed

        # Update the workflow indicator
        self.workflow_indicator.update_status(current_step, completed_steps, status)

    def process_pdfs_with_azure(self):
        """Process the selected PDF files with Azure Document Intelligence."""
        try:
            # Get Azure credentials
            azure_endpoint = self.azure_endpoint_input.text().strip() or os.getenv(
                "AZURE_ENDPOINT"
            )
            azure_key = self.azure_key_input.text().strip() or os.getenv("AZURE_KEY")

            # Validate Azure credentials
            if not azure_endpoint or not azure_key:
                QMessageBox.warning(
                    self,
                    "Missing Azure Credentials",
                    "Please enter Azure endpoint and API key to use Azure Document Intelligence.",
                )
                return

            # Get selected PDF files - use a safer method
            selected_files = []
            if hasattr(self, "pdf_files") and self.pdf_files:
                selected_files = self.pdf_files

            if not selected_files:
                QMessageBox.warning(
                    self, "No Files Selected", "Please select files to process."
                )
                return

            # Filter for PDF files only
            pdf_files = [f for f in selected_files if f.lower().endswith(".pdf")]
            if not pdf_files:
                QMessageBox.warning(
                    self,
                    "No PDF Files",
                    "No PDF files found in the selection. Only PDF files can be processed with Azure.",
                )
                return

            # Confirm with user
            num_files = len(pdf_files)
            msg = f"Process {num_files} PDF file{'s' if num_files > 1 else ''} with Azure Document Intelligence?\n\n"
            msg += "This will convert the PDFs to text using Azure's Document Intelligence service.\n"
            msg += "The converted files will be saved as JSON and Markdown in the output directory."
            reply = QMessageBox.question(
                self,
                "Process with Azure?",
                msg,
                QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.No:
                return

            # Validate output directory
            if not hasattr(self, "output_directory") or not self.output_directory:
                QMessageBox.warning(
                    self,
                    "No Output Directory",
                    "Please select an output directory before processing.",
                )
                return

            # Show status with progress bar
            self.show_status(
                f"Starting Azure Document Intelligence processing for {num_files} files...",
                0,
            )

            # Show an info dialog to remind about Azure processing
            QMessageBox.information(
                self,
                "Azure Processing Started",
                f"Azure Document Intelligence processing has started for {num_files} PDF files.\n\n"
                f"This process runs in the background and may take several minutes.\n\n"
                f"You can monitor progress in the status bar and continue using the application.",
            )

            # Create Azure thread class only if it exists
            if not hasattr(self, "AzureProcessingThread"):
                from ui.workers.azure_processing_thread import AzureProcessingThread

            # Create and start the Azure processing thread
            self.azure_thread = AzureProcessingThread(
                pdf_files, self.output_directory, azure_endpoint, azure_key
            )

            # Connect signals safely
            if hasattr(self.azure_thread, "progress_signal"):
                self.azure_thread.progress_signal.connect(self.update_azure_progress)
            if hasattr(self.azure_thread, "finished_signal"):
                self.azure_thread.finished_signal.connect(
                    self.azure_processing_finished
                )
            if hasattr(self.azure_thread, "error_signal"):
                self.azure_thread.error_signal.connect(self.azure_processing_error)

            # Start the thread
            self.azure_thread.start()

        except Exception as e:
            # Log and show error
            import traceback

            error_msg = f"Error in process_pdfs_with_azure: {str(e)}"
            print(error_msg)
            print(traceback.format_exc())

            QMessageBox.critical(
                self,
                "Processing Error",
                f"An error occurred while processing PDFs:\n\n{error_msg}",
            )

    def update_azure_progress(self, progress, message):
        """Update the progress for Azure Document Intelligence processing."""
        # Update status with progress
        self.show_status(f"Azure: {message}", progress)

        # Update logs
        self.append_status(f"Azure ({progress}%): {message}")

    def azure_processing_finished(self, results):
        """Handle completion of Azure Document Intelligence processing."""
        # Update status
        processed = results.get("processed", 0)
        skipped = results.get("skipped", 0)
        failed = results.get("failed", 0)
        total = results.get("total", 0)

        # Show results in a message box with color-coded details
        details = f"<b>Total:</b> {total}<br>"
        if processed > 0:
            details += (
                f"<span style='color: green'><b>Processed:</b> {processed}</span><br>"
            )
        if skipped > 0:
            details += f"<span style='color: blue'><b>Skipped:</b> {skipped}</span><br>"
        if failed > 0:
            details += f"<span style='color: red'><b>Failed:</b> {failed}</span><br>"

        # If any files failed, add detailed error info
        if failed > 0:
            details += "<br><b>Failed files:</b><br>"
            for file_info in results.get("files", []):
                if file_info.get("status") == "failed":
                    pdf_name = os.path.basename(file_info.get("pdf", "Unknown"))
                    error = file_info.get("error", "Unknown error")
                    details += (
                        f"<span style='color: red'>• {pdf_name}: {error}</span><br>"
                    )

        # Show the final status message
        completion_msg = (
            f"Azure processing complete: {processed}/{total} PDF files processed"
        )
        self.show_status(completion_msg, 100)

        # Add a delay before hiding the progress bar
        QTimer.singleShot(3000, self.clear_status)

        # Show message box with detailed results
        result_dialog = QMessageBox(self)
        result_dialog.setWindowTitle("Azure Processing Results")
        result_dialog.setIcon(QMessageBox.Icon.Information)
        result_dialog.setText("Azure Document Intelligence processing is complete.")
        result_dialog.setInformativeText(
            f"{processed} out of {total} files were successfully processed."
        )
        result_dialog.setDetailedText(
            f"Processed: {processed}\nSkipped: {skipped}\nFailed: {failed}"
        )

        # Create custom widget for rich text display
        details_widget = QLabel()
        details_widget.setTextFormat(Qt.TextFormat.RichText)
        details_widget.setText(details)
        details_widget.setMinimumWidth(400)
        details_widget.setStyleSheet("background-color: white; padding: 8px;")

        # Add custom widget to the layout
        layout = result_dialog.layout()
        layout.addWidget(details_widget, 3, 0, 1, layout.columnCount())

        result_dialog.exec()

        # Refresh file list to show new files
        self.refresh_file_list()

    def azure_processing_error(self, error_message):
        """Handle error during Azure Document Intelligence processing."""
        self.show_status(f"Error: {error_message}")

        # Show error message box
        QMessageBox.critical(
            self,
            "Azure Processing Error",
            f"An error occurred during Azure Document Intelligence processing:\n\n{error_message}",
        )

    def summarize_with_llm(self):
        """This functionality has been moved to the AnalysisTab"""
        # Inform the user
        QMessageBox.information(
            self,
            "Functionality Moved",
            "The LLM summarization functionality has been moved to the Analysis tab.\n"
            "Please use the Analysis tab for document summarization and integration.",
        )

    def update_llm_progress(self, percent, message):
        """This functionality has been moved to the AnalysisTab"""
        pass

    def on_llm_summarization_finished(self, results, dialog):
        """This functionality has been moved to the AnalysisTab"""
        if dialog and dialog.isVisible():
            dialog.close()

    def select_file_in_tree(self, file_path):
        """This functionality has been moved to the AnalysisTab"""
        pass

    def on_llm_summarization_error(self, error, dialog):
        """This functionality has been moved to the AnalysisTab"""
        if dialog and dialog.isVisible():
            dialog.close()

    def combine_summaries(self):
        """This functionality has been moved to the AnalysisTab"""
        # Inform the user
        QMessageBox.information(
            self,
            "Functionality Moved",
            "The combine summaries functionality has been moved to the Analysis tab.\n"
            "Please use the Analysis tab for document summarization and integration.",
        )

    def generate_integrated_analysis(self):
        """This functionality has been moved to the AnalysisTab"""
        # Inform the user
        QMessageBox.information(
            self,
            "Functionality Moved",
            "The integrated analysis functionality has been moved to the Analysis tab.\n"
            "Please use the Analysis tab for document summarization and integration.",
        )

    def on_integrated_analysis_finished(self, result_file, dialog):
        """This functionality has been moved to the AnalysisTab"""
        if dialog and dialog.isVisible():
            dialog.close()

    def on_integrated_analysis_error(self, error, dialog):
        """This functionality has been moved to the AnalysisTab"""
        if dialog and dialog.isVisible():
            dialog.close()

    def update_preview(self, index):
        """This functionality has been moved to the AnalysisTab"""
        # Only defined as a stub since it might be called from other places
        pass

    def test_azure_connection(self):
        """Test the connection to Azure Document Intelligence."""
        progress_dialog = None
        try:
            # Get Azure credentials from the UI or environment variables
            azure_endpoint = self.azure_endpoint_input.text().strip() or os.getenv(
                "AZURE_ENDPOINT"
            )
            azure_key = self.azure_key_input.text().strip() or os.getenv("AZURE_KEY")

            # Validate Azure credentials
            if not azure_endpoint or not azure_key:
                QMessageBox.warning(
                    self,
                    "Missing Azure Credentials",
                    "Please enter Azure endpoint and API key to test the connection.",
                )
                return

            # Create progress dialog
            progress_dialog = QProgressDialog(
                "Testing Azure connection...", "Cancel", 0, 0, self
            )
            progress_dialog.setWindowTitle("Azure Connection Test")
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setMinimumDuration(0)
            progress_dialog.setValue(0)
            progress_dialog.setRange(0, 0)  # Indeterminate progress
            progress_dialog.show()

            # Show initial status
            self.show_status("Testing Azure connection...")

            # Process events to keep UI responsive
            QCoreApplication.processEvents()

            # Import the test function directly
            from pdf_utils import test_azure_connection

            # Test the connection directly
            result = test_azure_connection(azure_endpoint, azure_key)
            success = result.get("success", False)
            message = result.get("message", "")
            if not success:
                message = result.get("error", "Unknown error")

            # Close the progress dialog
            if progress_dialog:
                progress_dialog.close()

            # Show result messages
            if success:
                QMessageBox.information(
                    self,
                    "Azure Connection Successful",
                    f"Successfully connected to Azure Document Intelligence.\n\n{message}",
                )
                self.show_status("Azure connection test: Success")
            else:
                QMessageBox.critical(
                    self,
                    "Azure Connection Failed",
                    f"Failed to connect to Azure Document Intelligence:\n\n{message}",
                )
                self.show_status("Azure connection test: Failed")
        except ImportError as e:
            if progress_dialog:
                progress_dialog.close()
            QMessageBox.critical(
                self,
                "Import Error",
                f"Could not import required modules: {str(e)}",
            )
        except Exception as e:
            if progress_dialog:
                progress_dialog.close()
            QMessageBox.critical(
                self,
                "Azure Connection Error",
                f"An error occurred while testing the Azure connection: {str(e)}",
            )

    def get_selected_files(self):
        """Get the list of selected PDF files."""
        # Check if we have files from the input tab
        if hasattr(self, "pdf_files") and self.pdf_files:
            return self.pdf_files

        # Return an empty list if no files are selected
        return []

    def get_markdown_files(self):
        """This functionality has been moved to the AnalysisTab"""
        # Only defined as a stub since it might be called from other places
        return []

    def on_file_selected(self, file_path):
        """Handle the selection of a file in the results tree."""
        if not self.results_viewer or not self.results_viewer.tree:
            return

        # Get the relative path to the output directory
        if os.path.isabs(file_path):
            rel_path = os.path.relpath(file_path, self.output_directory)
        else:
            rel_path = file_path

        # Find and select the item
        for i in range(self.results_viewer.tree.topLevelItemCount()):
            top_item = self.results_viewer.tree.topLevelItem(i)
            # Check if this is the summaries folder
            if top_item.text(0) == "summaries":
                # Look through children
                for j in range(top_item.childCount()):
                    child = top_item.child(j)
                    if child.text(0) == os.path.basename(rel_path):
                        # Select this item
                        self.results_viewer.tree.setCurrentItem(child)
                        return

    def safely_test_azure_connection(self):
        """Safely test Azure connection with error handling."""
        try:
            self.test_azure_connection()
        except Exception as e:
            # Log any errors
            import traceback

            print(f"Error testing Azure connection: {str(e)}")
            print(traceback.format_exc())

            # Show error to user
            QMessageBox.critical(
                self,
                "Azure Connection Error",
                f"An error occurred when testing Azure connection: {str(e)}",
            )

    def safely_process_pdfs_with_azure(self):
        """Safely process PDFs with Azure with error handling."""
        try:
            self.process_pdfs_with_azure()
        except Exception as e:
            # Log any errors
            import traceback

            print(f"Error processing PDFs with Azure: {str(e)}")
            print(traceback.format_exc())

            # Show error to user
            QMessageBox.critical(
                self,
                "PDF Processing Error",
                f"An error occurred when processing PDFs with Azure: {str(e)}",
            )

    def safely_summarize_with_llm(self):
        """Safely summarize markdown files with LLM"""
        # This functionality has been moved to the AnalysisTab
        # Inform the user
        QMessageBox.information(
            self,
            "Functionality Moved",
            "The summarize with LLM functionality has been moved to the Analysis tab.\n"
            "Please use the Analysis tab for document summarization and integration.",
        )

    def on_markdown_folder_selected(self, directory):
        """This functionality has been moved to the AnalysisTab"""
        # Inform the user
        QMessageBox.information(
            self,
            "Functionality Moved",
            "The markdown folder selection has been moved to the Analysis tab.\n"
            "Please use the Analysis tab for document summarization and integration.",
        )

    def on_results_output_selected(self, directory):
        """This functionality has been moved to the AnalysisTab"""
        # Inform the user
        QMessageBox.information(
            self,
            "Functionality Moved",
            "The results output selection has been moved to the Analysis tab.\n"
            "Please use the Analysis tab for document summarization and integration.",
        )

    def check_workflow_state(self):
        """This functionality has been moved to the AnalysisTab"""
        # Inform the user if called directly
        pass

    def on_output_directory_selected(self, directory):
        """Handle output directory selection."""
        self.output_directory = directory
        # Refresh the file list to show linked output files
        self.refresh_file_list()
        self.safely_check_ready_state()

    def show_status(self, message, progress=None):
        """Show a status message in the status bar and update progress if provided."""
        self.status_label.setText(message)

        # Update progress bar if provided
        if progress is not None:
            self.progress_bar.setValue(progress)
            self.progress_bar.setVisible(True)
        elif progress == 0:  # Reset progress bar
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)

        # Process events to keep the UI responsive
        QCoreApplication.processEvents()

    def clear_status(self):
        """Clear the status message and hide progress bar."""
        self.status_label.setText("")
        self.progress_bar.setVisible(False)

    def append_status(self, message):
        """Append a message to the status details."""
        if hasattr(self, "status_panel") and self.status_panel is not None:
            self.status_panel.append_details(message)
