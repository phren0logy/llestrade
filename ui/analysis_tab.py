"""
Analysis tab module for the Forensic Psych Report Drafter.
Handles document summarization, integration, and analysis using LLM.
"""

import os
import re
from datetime import datetime

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
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
    QStyle,
    QTextEdit,
    QVBoxLayout,
)

from app_config import get_available_providers_and_models, get_configured_llm_client
from config import DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE
from llm_utils_compat import LLMClientFactory, cached_count_tokens
from ui.base_tab import BaseTab
from ui.components.file_selector import FileSelector
from ui.components.status_panel import StatusPanel
from ui.components.workflow_indicator import WorkflowIndicator, WorkflowStep
from ui.workers.directory_scanner_thread import DirectoryScannerThread
from ui.workers.integrated_analysis_thread import IntegratedAnalysisThread
from ui.workers.llm_summary_thread import LLMSummaryThread

# Constants for directory and file names
SUMMARIES_SUBDIR = "summaries"
COMBINED_SUMMARY_FILENAME = "combined_summary.md"


class AnalysisTab(BaseTab):
    """
    Tab for analyzing and integrating markdown files using LLM.
    Provides summarization and integration of documents.
    """

    def __init__(self, parent=None, status_bar=None):
        """Initialize the Analysis tab."""
        # Initialize key attributes
        self.markdown_directory = None
        self.results_output_directory = None
        self._refreshing = False  # Flag to prevent recursion
        self.selected_llm_provider_id = None
        self.selected_llm_model_name = None
        self.available_llms = []
        self.file_selector = QComboBox()
        
        # Directory scanning attributes
        self.directory_scanner_thread = None
        self.scan_progress_dialog = None
        self.cached_markdown_files = {}  # Cache for scanned directories

        # Initialize the base tab
        super().__init__(parent, status_bar)

        # Set the tab title
        self.setWindowTitle("Analysis & Integration")
    
    def closeEvent(self, event):
        """Clean up resources when the tab is closed."""
        # Stop any running directory scanner
        if self.directory_scanner_thread and self.directory_scanner_thread.isRunning():
            self.directory_scanner_thread.stop()
            self.directory_scanner_thread.wait(1000)
        
        # Clean up LLM thread
        if hasattr(self, 'single_file_thread') and self.single_file_thread is not None:
            try:
                self.single_file_thread.cleanup()
                self.single_file_thread = None
            except Exception:
                pass  # Ignore cleanup errors during close
        
        # Close any open progress dialogs
        if self.scan_progress_dialog:
            self.scan_progress_dialog.close()
        
        super().closeEvent(event)

    def setup_ui(self):
        """Set up the UI components for the Analysis tab."""
        # Main layout
        main_layout = QVBoxLayout()

        # Create workflow indicator
        self.workflow_indicator = WorkflowIndicator()
        self.workflow_indicator.add_step(
            WorkflowStep.SELECT_MARKDOWN,
            "1. Select Markdown Files",
            "Select markdown files to analyze",
        )
        self.workflow_indicator.add_step(
            WorkflowStep.SUMMARIZE_LLM,
            "2. Generate Summaries",
            "Generate summaries for each document",
        )
        self.workflow_indicator.add_step(
            WorkflowStep.COMBINE_SUMMARIES,
            "3. Combine Summaries",
            "Combine all summaries into one document",
        )
        self.workflow_indicator.add_step(
            WorkflowStep.INTEGRATE_ANALYSIS,
            "4. Integrate Analysis",
            "Generate an integrated analysis",
        )

        main_layout.addWidget(self.workflow_indicator)

        # Add subject information section
        subject_group = QGroupBox("Subject Information")
        subject_layout = QFormLayout()

        # Subject name input
        self.subject_input = QLineEdit()
        self.subject_input.setPlaceholderText("Enter the subject's full name")
        subject_layout.addRow("Subject Name:", self.subject_input)

        # Date of birth input
        self.dob_input = QLineEdit()
        self.dob_input.setPlaceholderText("YYYY-MM-DD")
        subject_layout.addRow("Date of Birth:", self.dob_input)

        # Case information
        self.case_info_input = QTextEdit()
        self.case_info_input.setPlaceholderText(
            "Enter case details and context information"
        )
        self.case_info_input.setMaximumHeight(100)
        subject_layout.addRow("Case Information:", self.case_info_input)

        subject_group.setLayout(subject_layout)
        main_layout.addWidget(subject_group)

        # Add selector group for markdown files and output folder
        selector_group = QGroupBox("Document Selection")
        selector_layout = QVBoxLayout()

        # Add markdown folder selector
        self.markdown_folder_selector = FileSelector(
            title="Markdown Files Directory",
            button_text="Select Markdown Directory",
            file_mode=QFileDialog.FileMode.Directory,
            placeholder_text="No markdown directory selected",
            callback=self.on_markdown_folder_selected,
        )
        selector_layout.addWidget(self.markdown_folder_selector)

        # Add output directory selector for results
        self.results_output_selector = FileSelector(
            title="Results Output Directory",
            button_text="Select Output Directory",
            file_mode=QFileDialog.FileMode.Directory,
            placeholder_text="No output directory selected",
            callback=self.on_results_output_selected,
        )
        selector_layout.addWidget(self.results_output_selector)

        selector_group.setLayout(selector_layout)
        main_layout.addWidget(selector_group)

        # Add status panel (moved earlier to be available for LLM selector initialization)
        self.status_panel = StatusPanel()

        # Create operation buttons group
        operations_group = QGroupBox("Analysis Operations")
        operations_layout = QVBoxLayout()

        # LLM Selector
        llm_selector_layout = QHBoxLayout()
        llm_selector_layout.addWidget(QLabel("Select LLM for Analysis:"))
        self.llm_selector_combo = QComboBox()
        self.llm_selector_combo.setToolTip("Choose the LLM to use for summarization and analysis.")
        llm_selector_layout.addWidget(self.llm_selector_combo)
        operations_layout.addLayout(llm_selector_layout)
        self._populate_llm_selector()
        self.llm_selector_combo.currentIndexChanged.connect(self._on_llm_selection_changed)

        # LLM Summarization button
        self.llm_process_button = QPushButton("Generate Summaries with LLM")
        self.llm_process_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self.llm_process_button.setToolTip(
            "Generate summaries for each markdown file using LLM"
        )
        self.llm_process_button.clicked.connect(self.safely_summarize_with_llm)
        self.llm_process_button.setEnabled(False)
        operations_layout.addWidget(self.llm_process_button)

        # Combine Summaries button
        self.combine_button = QPushButton("Combine Summaries")
        self.combine_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView)
        )
        self.combine_button.setToolTip(
            "Merge all individual document summaries into a single file"
        )
        self.combine_button.clicked.connect(self.combine_summaries)
        self.combine_button.setEnabled(False)
        operations_layout.addWidget(self.combine_button)

        # Generate Integrated Analysis button
        self.integrate_button = QPushButton("Generate Integrated Analysis")
        self.integrate_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView)
        )
        self.integrate_button.setToolTip(
            "Generate a comprehensive analysis across all documents"
        )
        self.integrate_button.clicked.connect(self.generate_integrated_analysis)
        self.integrate_button.setEnabled(False)
        operations_layout.addWidget(self.integrate_button)

        operations_group.setLayout(operations_layout)
        main_layout.addWidget(operations_group)

        # Add results viewer group
        viewer_group = QGroupBox("Results Preview")
        viewer_layout = QVBoxLayout()

        # Add file selector
        file_selector_layout = QHBoxLayout()
        file_selector_layout.addWidget(QLabel("Select a file to preview:"))

        self.file_selector.setToolTip("Choose a file to preview in the viewer below")
        self.file_selector.currentIndexChanged.connect(self.update_preview)
        file_selector_layout.addWidget(self.file_selector)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
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
        main_layout.addWidget(viewer_group)

        # Add status panel at the bottom (original position, now add it to layout here)
        main_layout.addWidget(self.status_panel)

        # Set the main layout
        self.layout.addLayout(main_layout)

    def _populate_llm_selector(self):
        """Populates the LLM selector ComboBox."""
        self.available_llms = get_available_providers_and_models()
        self.llm_selector_combo.clear()
        if not self.available_llms:
            self.llm_selector_combo.addItem("No LLMs configured or available")
            self.llm_selector_combo.setEnabled(False)
            self.selected_llm_provider_id = None
            self.selected_llm_model_name = None
            return

        self.llm_selector_combo.setEnabled(True)
        for i, llm_config in enumerate(self.available_llms):
            self.llm_selector_combo.addItem(llm_config["display_name"], userData=llm_config)
        
        # Set initial selection if any
        if self.available_llms:
            self._on_llm_selection_changed(0) # Trigger initial selection

    def _on_llm_selection_changed(self, index):
        """Handles changes in the LLM selector ComboBox."""
        if index < 0 or not self.available_llms:
            self.selected_llm_provider_id = None
            self.selected_llm_model_name = None
            # Disable buttons if no LLM is selected
            self.llm_process_button.setEnabled(False)
            self.integrate_button.setEnabled(False)
            return

        selected_data = self.llm_selector_combo.itemData(index)
        if selected_data:
            self.selected_llm_provider_id = selected_data["id"]
            self.selected_llm_model_name = selected_data["model"]
            self.status_panel.append_details(
                f"LLM for Analysis set to: {selected_data['display_name']}"
            )
            # Update button states based on selection and other conditions
            self.check_workflow_state()
        else:
            # Handle case where itemData might be None unexpectedly
            self.selected_llm_provider_id = None
            self.selected_llm_model_name = None
            self.llm_process_button.setEnabled(False)
            self.integrate_button.setEnabled(False)

    def on_markdown_folder_selected(self, directory):
        """Handle selection of markdown folder directory."""
        if not directory:
            return

        self.markdown_directory = directory
        self.status_panel.append_details(f"Markdown directory set to: {directory}")
        
        # Check if we have cached results for this directory
        if directory in self.cached_markdown_files:
            self.show_status(f"Using cached scan results for {os.path.basename(directory)}")
            self.check_workflow_state()
            return
        
        # Start asynchronous directory scanning
        self.start_directory_scan(directory)
    
    def start_directory_scan(self, directory):
        """Start asynchronous directory scanning with progress dialog."""
        try:
            # Stop any existing scan
            if self.directory_scanner_thread and self.directory_scanner_thread.isRunning():
                self.directory_scanner_thread.stop()
                self.directory_scanner_thread.wait(1000)  # Wait up to 1 second
            
            # Create progress dialog
            self.scan_progress_dialog = QProgressDialog(
                f"Scanning directory: {os.path.basename(directory)}...",
                "Cancel",
                0,
                100,
                self
            )
            self.scan_progress_dialog.setWindowTitle("Scanning Markdown Directory")
            self.scan_progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.scan_progress_dialog.setMinimumDuration(500)  # Show after 500ms
            self.scan_progress_dialog.canceled.connect(self.cancel_directory_scan)
            
            # Create and configure scanner thread
            self.directory_scanner_thread = DirectoryScannerThread(directory, ['.md'])
            self.directory_scanner_thread.progress_signal.connect(self.update_scan_progress)
            self.directory_scanner_thread.finished_signal.connect(self.on_directory_scan_finished)
            self.directory_scanner_thread.error_signal.connect(self.on_directory_scan_error)
            
            # Start scanning
            self.directory_scanner_thread.start()
            self.scan_progress_dialog.show()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Directory Scan Error",
                f"Failed to start directory scan: {str(e)}"
            )
    
    def update_scan_progress(self, progress, message):
        """Update the progress dialog during directory scanning."""
        dialog = self.scan_progress_dialog
        if dialog is not None and not dialog.wasCanceled():
            dialog.setValue(progress)
            dialog.setLabelText(message)
    
    def cancel_directory_scan(self):
        """Cancel the directory scanning operation."""
        if self.directory_scanner_thread:
            self.directory_scanner_thread.stop()
            self.show_status("Directory scan canceled by user")
    
    def on_directory_scan_finished(self, success, message, files):
        """Handle completion of directory scanning."""
        try:
            # Close progress dialog
            if self.scan_progress_dialog:
                self.scan_progress_dialog.close()
                self.scan_progress_dialog = None
            
            if success:
                # Cache the results
                self.cached_markdown_files[self.markdown_directory] = files
                
                # Show warning if too many files
                if message:  # Warning message about too many files
                    QMessageBox.warning(self, "Large Directory", message)
                
                # Update status
                self.show_status(f"Found {len(files)} markdown files in {os.path.basename(self.markdown_directory)}")
                self.status_panel.append_details(f"Scanned directory: {len(files)} markdown files found")
                
                # Update workflow state now that we have the file list
                self.check_workflow_state()
            else:
                QMessageBox.warning(
                    self,
                    "Directory Scan Failed",
                    f"Failed to scan directory: {message}"
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Error handling directory scan results: {str(e)}"
            )
        finally:
            # Clean up thread
            if self.directory_scanner_thread:
                self.directory_scanner_thread.deleteLater()
                self.directory_scanner_thread = None
    
    def on_directory_scan_error(self, error_message):
        """Handle directory scanning errors."""
        try:
            # Close progress dialog
            if self.scan_progress_dialog:
                self.scan_progress_dialog.close()
                self.scan_progress_dialog = None
            
            QMessageBox.critical(
                self,
                "Directory Scan Error",
                f"Error scanning directory: {error_message}"
            )
            self.show_status(f"Directory scan failed: {error_message}")
        finally:
            # Clean up thread
            if self.directory_scanner_thread:
                self.directory_scanner_thread.deleteLater()
                self.directory_scanner_thread = None

    def on_results_output_selected(self, directory):
        """Handle selection of results output directory."""
        if not directory:
            return

        self.results_output_directory = directory
        self.status_panel.append_details(
            f"Results output directory set to: {directory}"
        )
        self.check_workflow_state()

    def check_workflow_state(self):
        """Check the state of the workflow and enable/disable buttons accordingly."""
        # Check if markdown files directory is set and contains markdown files
        has_markdown = False
        if (
            hasattr(self, "markdown_directory")
            and self.markdown_directory
            and os.path.exists(self.markdown_directory)
        ):
            # Use cached results if available, otherwise fall back to quick check
            if self.markdown_directory in self.cached_markdown_files:
                markdown_files = self.cached_markdown_files[self.markdown_directory]
                has_markdown = bool(markdown_files)
            else:
                # Quick check - don't block UI for large directories
                try:
                    # Only check first few files to avoid blocking
                    files_sample = os.listdir(self.markdown_directory)[:100]  # Limit to first 100 items
                    markdown_files = [f for f in files_sample if f.endswith(".md")]
                    has_markdown = bool(markdown_files)
                    
                    # If we found files, note that full scan may be needed
                    if has_markdown and len(files_sample) == 100:
                        self.status_panel.append_details("Quick scan found markdown files. Full scan may be in progress.")
                except Exception as e:
                    print(f"Error checking markdown files: {e}")
                    has_markdown = False

        # Check if there are summary files
        has_summaries = False
        if (
            hasattr(self, "results_output_directory")
            and self.results_output_directory
            and os.path.exists(self.results_output_directory)
        ):
            try:
                # Look for summary files in the 'summaries' subdirectory
                summaries_path = os.path.join(
                    self.results_output_directory, SUMMARIES_SUBDIR
                )
                if os.path.exists(summaries_path):
                    summary_files = [
                        f
                        for f in os.listdir(summaries_path)
                        if f.endswith("_summary.md")
                    ]
                    has_summaries = bool(summary_files)
                else:
                    has_summaries = False # Subdirectory doesn't exist
            except Exception as e:
                print(f"Error checking summary files: {e}")
                has_summaries = False

        # Check if combined summary exists
        has_combined = False
        if (
            hasattr(self, "results_output_directory")
            and self.results_output_directory
            and os.path.exists(self.results_output_directory)
        ):
            try:
                combined_file = os.path.join(
                    self.results_output_directory, COMBINED_SUMMARY_FILENAME
                )
                has_combined = os.path.exists(combined_file)
            except Exception as e:
                print(f"Error checking combined summary: {e}")
                has_combined = False

        # Update workflow indicator states
        try:
            self.workflow_indicator.update_status(
                WorkflowStep.SELECT_MARKDOWN,
                "complete" if has_markdown else "not_started",
            )

            self.workflow_indicator.update_status(
                WorkflowStep.SUMMARIZE_LLM,
                "complete" if has_summaries else "not_started",
            )

            self.workflow_indicator.update_status(
                WorkflowStep.COMBINE_SUMMARIES,
                "complete" if has_combined else "not_started",
            )
        except Exception as e:
            print(f"Error updating workflow indicator: {e}")

        # Enable/disable LLM process button
        try:
            if (
                hasattr(self, "llm_process_button")
                and self.llm_process_button is not None
            ):
                valid_subject = bool(self.subject_input.text().strip())
                valid_dob = bool(self.dob_input.text().strip())
                valid_llm = bool(
                    hasattr(self, "selected_llm_provider_id")
                    and self.selected_llm_provider_id
                    and hasattr(self, "selected_llm_model_name")
                    and self.selected_llm_model_name
                )
                self.llm_process_button.setEnabled(
                    has_markdown and valid_subject and valid_dob and valid_llm
                )
        except Exception as e:
            print(f"Error setting LLM process button state: {e}")

        # Enable/disable combine button
        try:
            if hasattr(self, "combine_button") and self.combine_button is not None:
                self.combine_button.setEnabled(has_summaries)
        except Exception as e:
            print(f"Error setting combine button state: {e}")

        # Enable/disable integrate button
        try:
            if hasattr(self, "integrate_button") and self.integrate_button is not None:
                self.integrate_button.setEnabled(has_combined)
        except Exception as e:
            print(f"Error setting integrate button state: {e}")

        # If we haven't called this from refresh_file_list, update the file list
        try:
            if not hasattr(self, "_refreshing") or not self._refreshing:
                self._refreshing = True
                self.refresh_file_list()
                self._refreshing = False
        except Exception as e:
            print(f"Error refreshing file list: {e}")
            self._refreshing = False

    def refresh_file_list(self):
        """Refresh the list of files in the preview selector."""
        if not hasattr(self, "file_selector"):
            # If the UI is not fully initialized yet, just return.
            return

        if self._refreshing:  # Prevent recursion
            return
        self._refreshing = True

        try:
            # Clear the current list
            self.file_selector.clear()

            # Add a placeholder item
            self.file_selector.addItem("Select a file to preview", None)

            # If no results output directory is set, return
            if (
                not hasattr(self, "results_output_directory")
                or not self.results_output_directory
            ):
                return

            if not os.path.exists(self.results_output_directory):
                return

            # Get all files from the output directory and its 'summaries' subdirectory
            files = []
            
            def add_files_from_dir(directory_path, display_prefix=""):
                if os.path.exists(directory_path):
                    for file_name in os.listdir(directory_path):
                        if file_name.endswith(".md"):
                            full_path = os.path.join(directory_path, file_name)
                            display_name_with_prefix = os.path.join(display_prefix, file_name) if display_prefix else file_name
                            files.append({"path": full_path, "display": display_name_with_prefix})

            # Add files from the root of results_output_directory
            add_files_from_dir(self.results_output_directory)

            # Add files from the 'summaries' subdirectory
            summaries_dir_path = os.path.join(self.results_output_directory, SUMMARIES_SUBDIR)
            add_files_from_dir(summaries_dir_path, display_prefix=SUMMARIES_SUBDIR)
            
            # Sort files by modification time (newest first)
            files.sort(key=lambda x: os.path.getmtime(x["path"]), reverse=True)

            # Add files to the selector
            for file_info in files:
                self.file_selector.addItem(file_info["display"], file_info["path"])
        finally:
            self._refreshing = False

    def update_preview(self, index):
        """Update the preview area with the selected file content."""
        # Clear the preview area
        self.preview_area.clear()

        # Get the selected file path
        file_path = self.file_selector.itemData(index)
        if not file_path:
            self.preview_area.setPlaceholderText(
                "Select a file to preview its contents"
            )
            return

        try:
            # Read the file content
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Set the content in the preview area
            self.preview_area.setMarkdown(content)

            # Show a status message
            self.show_status(f"Previewing: {os.path.basename(file_path)}")
        except Exception as e:
            self.preview_area.setPlainText(f"Error loading file: {str(e)}")
            self.show_status(f"Error previewing file: {str(e)}")

    def safely_summarize_with_llm(self):
        """Initiate LLM summarization safely after checks."""
        if (
            not self.markdown_directory
            or not self.results_output_directory
            or not self.selected_llm_provider_id
            or not self.selected_llm_model_name
        ):
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please ensure all required fields are filled out.",
            )
            return

        # Check if markdown directory is selected and exists
        if not hasattr(self, "markdown_directory") or not self.markdown_directory:
            QMessageBox.warning(
                self,
                "Missing Directory",
                "Please select a markdown files directory first.",
            )
            return

        if not os.path.exists(self.markdown_directory):
            QMessageBox.warning(
                self,
                "Invalid Directory",
                f"The directory {self.markdown_directory} does not exist.",
            )
            return

        # Check if results directory is selected and exists
        if (
            not hasattr(self, "results_output_directory")
            or not self.results_output_directory
        ):
            QMessageBox.warning(
                self,
                "Missing Output Directory",
                "Please select a results output directory first.",
            )
            return

        if not os.path.exists(self.results_output_directory):
            # Ask if the directory should be created
            reply = QMessageBox.question(
                self,
                "Create Directory",
                f"The directory {self.results_output_directory} does not exist. Create it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if reply == QMessageBox.StandardButton.Yes:
                try:
                    os.makedirs(self.results_output_directory)
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Directory Creation Failed",
                        f"Failed to create directory: {str(e)}",
                    )
                    return
            else:
                return

        # Get subject name and DOB
        subject_name = self.subject_input.text().strip()
        subject_dob = self.dob_input.text().strip()

        # Get case information
        case_info = self.case_info_input.toPlainText().strip()

        # Check for missing subject name or DOB
        if not subject_name or not subject_dob:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please fill in both Subject Name and Date of Birth.",
            )
            return

        # Now proceed with the LLM summarization
        self.summarize_with_llm()

    def summarize_with_llm(self):
        """Process markdown files to generate summaries using LLM."""
        if (
            not self.markdown_directory
            or not self.results_output_directory
            or not self.selected_llm_provider_id
            or not self.selected_llm_model_name
        ):
            self.status_panel.append_error(
                "Markdown directory, results output directory, or LLM not selected."
            )
            return

        markdown_files = self.get_markdown_files()
        if not markdown_files:
            QMessageBox.warning(
                self, "No Markdown Files", "No markdown files found in the selected directory."
            )
            return

        output_dir = os.path.join(self.results_output_directory, SUMMARIES_SUBDIR)
        os.makedirs(output_dir, exist_ok=True)

        subject_name = self.subject_input.text().strip()
        subject_dob = self.dob_input.text().strip()
        case_info = self.case_info_input.toPlainText().strip()

        # Validate subject information (moved here from individual thread)
        if not subject_name:
            QMessageBox.warning(self, "Missing Information", "Please enter subject's name.")
            return
        if not subject_dob:
            QMessageBox.warning(self, "Missing Information", "Please enter subject's DOB.")
            return
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", subject_dob):
            QMessageBox.warning(self, "Invalid Date Format", "Subject DOB must be YYYY-MM-DD.")
            return

        # Update workflow indicator
        self.workflow_indicator.update_status(
            WorkflowStep.SUMMARIZE_LLM, "in_progress"
        )
        self.llm_process_button.setEnabled(False)

        # ----- NEW APPROACH: Process files one at a time to avoid thread issues -----
        self.process_files_sequentially(
            markdown_files, 
            output_dir, 
            subject_name, 
            subject_dob, 
            case_info,
            self.selected_llm_provider_id,  # Pass LLM info
            self.selected_llm_model_name    # Pass LLM info
        )

    def process_files_sequentially(
        self, markdown_files, output_dir, subject_name, subject_dob, case_info,
        llm_provider_id, llm_model_name # Added LLM params
    ):
        """Processes files sequentially for summarization."""
        self.files_to_process = markdown_files
        self.output_dir = output_dir
        self.subject_name = subject_name
        self.subject_dob = subject_dob
        self.case_info = case_info
        self.processed_files_count = 0
        self.total_files_count = len(markdown_files)
        self.llm_provider_id_for_summary = llm_provider_id # Store for process_next_file
        self.llm_model_name_for_summary = llm_model_name # Store for process_next_file

        if self.total_files_count > 0:
            # Setup progress dialog for the entire batch
            self.progress_dialog = QProgressDialog(
                "Summarizing documents with LLM...",
                "Cancel",
                0,
                self.total_files_count,
                self,
            )
            self.progress_dialog.setWindowTitle("LLM Summarization")
            self.progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.setValue(0)
            self.progress_dialog.show()

            # Initialize results
            self.summary_results = {
                "total": self.total_files_count,
                "processed": 0,
                "skipped": 0,
                "failed": 0,
                "files": [],
            }

            # Set up processing of first file
            self.current_file_index = 0
            self.markdown_files = markdown_files
            self.output_dir = output_dir
            self.subject_name = subject_name
            self.subject_dob = subject_dob
            self.case_info = case_info

            # Process files one at a time using a timer to avoid blocking the UI
            QTimer.singleShot(100, self.process_next_file)

    def process_next_file(self):
        """Process the next file in the queue."""
        # Check if we're done or canceled
        if (
            self.current_file_index >= len(self.markdown_files)
            or self.progress_dialog.wasCanceled()
        ):
            self.finish_processing()
            return

        # Get the current file
        current_file = self.markdown_files[self.current_file_index]
        basename = os.path.splitext(os.path.basename(current_file))[0]

        # Update progress
        self.progress_dialog.setValue(self.current_file_index)
        self.progress_dialog.setLabelText(f"Processing: {basename}")
        self.show_status(
            f"Summarizing file {self.current_file_index + 1}/{len(self.markdown_files)}: {basename}"
        )

        # Check if already processed
        summary_file = os.path.join(self.output_dir, f"{basename}_summary.md")
        if os.path.exists(summary_file):
            self.status_panel.append_details(
                f"File already processed, skipping: {basename}"
            )
            self.summary_results["skipped"] += 1
            self.summary_results["files"].append(
                {
                    "file": current_file,
                    "markdown": current_file,
                    "status": "skipped",
                    "summary": summary_file,
                }
            )

            # Move to next file
            self.current_file_index += 1
            QTimer.singleShot(100, self.process_next_file)
            return

        # Process current file
        try:
            # Clean up previous thread if it exists
            if hasattr(self, 'single_file_thread') and self.single_file_thread is not None:
                try:
                    # Disconnect signals to prevent issues
                    self.single_file_thread.progress_signal.disconnect()
                    self.single_file_thread.finished_signal.disconnect()
                    self.single_file_thread.error_signal.disconnect()
                    
                    # Clean up the thread
                    if self.single_file_thread.isRunning():
                        self.single_file_thread.cleanup()
                    else:
                        self.single_file_thread = None
                except Exception as cleanup_error:
                    self.status_panel.append_details(f"Warning: Thread cleanup error: {cleanup_error}")
            
            # Create LLM thread for just this file
            self.single_file_thread = LLMSummaryThread(
                self,
                markdown_files=[current_file],
                output_dir=self.output_dir,
                subject_name=self.subject_name,
                subject_dob=self.subject_dob,
                case_info=self.case_info,
                status_panel=self.status_panel, # Pass status panel for detailed logging by thread
                llm_provider_id=self.llm_provider_id_for_summary, # Pass stored LLM info
                llm_model_name=self.llm_model_name_for_summary  # Pass stored LLM info
            )

            # Connect signals with queued connections for thread safety
            self.single_file_thread.progress_signal.connect(
                self.update_file_progress, Qt.ConnectionType.QueuedConnection
            )
            self.single_file_thread.finished_signal.connect(
                self.on_file_finished, Qt.ConnectionType.QueuedConnection
            )
            self.single_file_thread.error_signal.connect(
                self.on_file_error, Qt.ConnectionType.QueuedConnection
            )

            # Start processing
            self.status_panel.append_details(f"Starting to process: {basename}")
            self.single_file_thread.start()

        except Exception as e:
            # Handle error and move to next file
            self.status_panel.append_details(
                f"Error setting up processing for {basename}: {str(e)}"
            )

            self.summary_results["failed"] += 1
            self.summary_results["files"].append(
                {
                    "file": current_file,
                    "markdown": current_file,
                    "status": "failed",
                    "error": str(e),
                }
            )

            # Move to next file
            self.current_file_index += 1
            QTimer.singleShot(100, self.process_next_file)

    def update_file_progress(self, percent, message):
        """Update progress for the current file."""
        # Update status panel
        self.status_panel.append_details(message)

        # Also show in status bar
        basename = os.path.basename(self.markdown_files[self.current_file_index])
        self.show_status(
            f"File {self.current_file_index + 1}/{len(self.markdown_files)} ({basename}): {message}"
        )

    def on_file_finished(self, results):
        """Handle completion of a single file."""
        # Since we're only processing one file at a time, get that file's result
        if results.get("files") and len(results["files"]) > 0:
            file_result = results["files"][0]

            if file_result.get("status") == "success":
                self.summary_results["processed"] += 1
            elif file_result.get("status") == "skipped":
                self.summary_results["skipped"] += 1
            else:
                self.summary_results["failed"] += 1

            self.summary_results["files"].append(file_result)

        # Clean up the completed thread
        self._cleanup_current_thread()

        # Move to next file
        self.current_file_index += 1
        QTimer.singleShot(100, self.process_next_file)

    def on_file_error(self, error):
        """Handle error for a single file."""
        # Log the error
        current_file = self.markdown_files[self.current_file_index]
        basename = os.path.basename(current_file)
        self.status_panel.append_error(f"❌ ERROR: {basename} - {error}")

        # Update results
        self.summary_results["failed"] += 1
        self.summary_results["files"].append(
            {
                "file": current_file,
                "markdown": current_file,
                "status": "failed",
                "error": error,
                "message": error
            }
        )

        # Clean up the failed thread
        self._cleanup_current_thread()

        # Move to next file
        self.current_file_index += 1
        QTimer.singleShot(100, self.process_next_file)

    def _cleanup_current_thread(self):
        """Clean up the current thread safely."""
        if hasattr(self, 'single_file_thread') and self.single_file_thread is not None:
            try:
                # Disconnect signals
                self.single_file_thread.progress_signal.disconnect()
                self.single_file_thread.finished_signal.disconnect()
                self.single_file_thread.error_signal.disconnect()
                
                # Clean up the thread
                self.single_file_thread.cleanup()
                self.single_file_thread = None
                
            except Exception as e:
                self.status_panel.append_details(f"Warning: Thread cleanup error: {e}")

    def finish_processing(self):
        """Finalize the processing after all files are done."""
        # Close progress dialog
        self.progress_dialog.close()

        # Calculate final results
        total = self.summary_results["total"]
        processed = self.summary_results["processed"]
        skipped = self.summary_results["skipped"]
        failed = self.summary_results["failed"]

        # Update workflow status
        if processed + skipped == total and failed == 0:
            self.workflow_indicator.update_status(
                WorkflowStep.SUMMARIZE_LLM, "complete"
            )
        elif processed + skipped > 0:
            self.workflow_indicator.update_status(WorkflowStep.SUMMARIZE_LLM, "partial")
        else:
            self.workflow_indicator.update_status(WorkflowStep.SUMMARIZE_LLM, "error")

        # Create detailed results summary
        self.status_panel.append_details("=" * 60)
        self.status_panel.append_details("LLM SUMMARIZATION RESULTS")
        self.status_panel.append_details("=" * 60)
        self.status_panel.append_details(f"Total files: {total}")
        self.status_panel.append_details(f"✅ Successfully processed: {processed}")
        self.status_panel.append_details(f"⚠️  Skipped (already exist): {skipped}")
        self.status_panel.append_details(f"❌ Failed: {failed}")

        # Show individual file results
        if self.summary_results["files"]:
            self.status_panel.append_details("\nDetailed Results:")
            for file_info in self.summary_results["files"]:
                file_name = os.path.basename(file_info.get("file", file_info.get("path", "Unknown")))
                status = file_info.get("status", "unknown")
                message = file_info.get("message", "")
                
                if status == "success":
                    self.status_panel.append_details(f"  ✅ {file_name}: {message}")
                elif status == "skipped":
                    self.status_panel.append_details(f"  ⚠️  {file_name}: {message}")
                else:
                    error = file_info.get("error", "Unknown error")
                    self.status_panel.append_details(f"  ❌ {file_name}: {error}")

        self.status_panel.append_details("=" * 60)

        # Show message with results
        if failed > 0:
            QMessageBox.warning(
                self,
                "Summarization Results",
                f"Summarization completed with some issues.\n\n"
                f"📊 Results Summary:\n"
                f"Total files: {total}\n"
                f"✅ Successfully processed: {processed}\n"
                f"⚠️ Skipped (already processed): {skipped}\n"
                f"❌ Failed: {failed}\n\n"
                f"See the status panel for detailed results.",
            )
        else:
            QMessageBox.information(
                self,
                "Summarization Complete",
                f"All files have been processed successfully! 🎉\n\n"
                f"📊 Results Summary:\n"
                f"Total files: {total}\n"
                f"✅ Successfully processed: {processed}\n"
                f"⚠️ Skipped (already processed): {skipped}",
            )

        # Update status bar
        if failed == 0:
            self.show_status(
                f"✅ LLM summarization complete: {processed + skipped}/{total} files processed successfully"
            )
        else:
            self.show_status(
                f"⚠️ LLM summarization complete: {processed + skipped}/{total} files processed, {failed} failed"
            )

        # Re-enable the button
        self.llm_process_button.setEnabled(True)

        # Refresh file list to show new summaries
        self.refresh_file_list()

        # Update workflow state
        self.check_workflow_state()

    def get_markdown_files(self):
        """Get a list of all markdown files in the markdown directory."""
        # Check if markdown_directory is set
        if not hasattr(self, "markdown_directory") or not self.markdown_directory:
            self.show_status("No markdown directory selected")
            return []

        # Check if the directory exists
        if not os.path.exists(self.markdown_directory):
            self.show_status(
                f"Markdown directory does not exist: {self.markdown_directory}"
            )
            return []

        # Use cached results if available
        if self.markdown_directory in self.cached_markdown_files:
            markdown_files = self.cached_markdown_files[self.markdown_directory]
        else:
            # If not cached, we need to trigger a scan first
            QMessageBox.information(
                self,
                "Directory Scan Required",
                "The directory needs to be scanned first. Please wait for the scan to complete."
            )
            self.start_directory_scan(self.markdown_directory)
            return []

        # If no files found, show a message
        if not markdown_files:
            self.show_status("No markdown files found for summarization")
            return []

        # Log the files found
        self.status_panel.append_details(
            f"Found {len(markdown_files)} markdown files for summarization"
        )
        for file in markdown_files:
            self.status_panel.append_details(f"  - {os.path.basename(file)}")

        return markdown_files

    def combine_summaries(self):
        """Combine all summary markdown files into a single file."""
        # Get the subject name and case information
        subject_name = self.subject_input.text().strip()
        subject_dob = self.dob_input.text().strip()
        case_info = self.case_info_input.toPlainText().strip()

        # Validate required fields
        if not subject_name:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter the subject's name before combining summaries.",
            )
            return

        if not subject_dob:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter the subject's date of birth before combining summaries.",
            )
            return

        if not case_info:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter case information before combining summaries.",
            )
            return

        # Check if the output directory exists
        if not os.path.exists(self.results_output_directory):
            QMessageBox.warning(
                self,
                "No Output Directory",
                "No output directory found. Please select an output directory first.",
            )
            return

        # Get all summary files from the 'summaries' subdirectory
        summary_files = []
        summaries_path = os.path.join(self.results_output_directory, SUMMARIES_SUBDIR)

        if not os.path.exists(summaries_path):
            QMessageBox.warning(
                self,
                "No Summaries Found",
                f"Summaries subdirectory ('{SUMMARIES_SUBDIR}') not found in the output directory.",
            )
            return

        for file in os.listdir(summaries_path):
            if file.endswith("_summary.md"):
                summary_files.append(os.path.join(summaries_path, file))
        
        if not summary_files:
            QMessageBox.warning(
                self,
                "No Summaries Found",
                "No summary files found in the output directory.",
            )
            return

        # Create progress dialog
        progress_dialog = QProgressDialog(
            "Combining summary files...",
            "Cancel",
            0,
            100,
            self,
        )
        progress_dialog.setWindowTitle("Combine Summaries")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.show()

        # Update workflow indicator
        self.workflow_indicator.update_status(
            WorkflowStep.COMBINE_SUMMARIES, "in_progress"
        )

        # Start combining process
        combined_text = f"# Combined Summary for {subject_name}\n\n"
        combined_text += f"Date of Birth: {subject_dob}\n\n"
        combined_text += f"## Case Information\n\n{case_info}\n\n"
        combined_text += f"## Document Summaries\n\n"
        combined_text += f"This document contains summaries of {len(summary_files)} records analyzed with the assistance of the LLM.\n\n"
        combined_text += (
            f"Date Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
        combined_text += "---\n\n"

        # Add each summary to the combined file
        total_files = len(summary_files)
        for i, summary_file in enumerate(summary_files):
            progress_percent = int(((i + 1) / total_files) * 70)

            # Update progress
            self.update_progress(
                progress_dialog,
                progress_percent,
                f"Processing summary {i+1} of {total_files}: {os.path.basename(summary_file)}",
            )

            # Read the summary file
            with open(summary_file, "r", encoding="utf-8") as f:
                summary_text = f.read()

            # Get the original filename from the summary filename
            original_file = os.path.basename(summary_file).replace("_summary.md", "")

            # Add a separator and the summary
            combined_text += f"### {original_file}\n\n"
            combined_text += summary_text + "\n\n---\n\n"

            # Check if canceled
            if progress_dialog.wasCanceled():
                progress_dialog.close()
                self.show_status("Combining summaries canceled by user")
                return

        # Analyze similarities and patterns
        self.update_progress(
            progress_dialog, 80, "Analyzing patterns and similarities..."
        )

        # Add a combined timeline section
        combined_text += "## Combined Timeline\n\n"
        combined_text += "_This section combines all individual timelines from the document summaries._\n\n"

        # Save the combined text to a file
        self.update_progress(progress_dialog, 90, "Saving combined file...")
        combined_file_path = os.path.join(
            self.results_output_directory, COMBINED_SUMMARY_FILENAME
        )

        with open(combined_file_path, "w", encoding="utf-8") as f:
            f.write(combined_text)

        # Complete the progress dialog
        self.update_progress(progress_dialog, 100, "Combine operation complete!")

        # Show success message
        QMessageBox.information(
            self,
            "Combine Complete",
            f"Successfully combined {len(summary_files)} summary files.\n\nOutput file: {combined_file_path}",
        )

        # Update status and workflow
        self.workflow_indicator.update_status(
            WorkflowStep.COMBINE_SUMMARIES, "complete"
        )
        self.show_status(
            f"Combined {len(summary_files)} summary files into {os.path.basename(combined_file_path)}"
        )
        self.status_panel.append_details(f"Created combined summary: {combined_file_path}")

        # Update file list
        self.refresh_file_list()

        # Update workflow state to ensure buttons are properly enabled/disabled
        self.check_workflow_state()

        # Close progress dialog after a delay
        QTimer.singleShot(1000, progress_dialog.close)

    def update_progress(self, dialog, percent, message):
        """Update progress dialog with percentage and message."""
        if dialog and not dialog.wasCanceled():
            dialog.setValue(percent)
            dialog.setLabelText(message)

        # Log message to status panel
        self.status_panel.append_details(message)

    def generate_integrated_analysis(self):
        """Generates an integrated analysis from combined summaries and markdown files."""
        if (
            not self.results_output_directory
            or not self.markdown_directory
            or not self.selected_llm_provider_id
            or not self.selected_llm_model_name
        ):
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please ensure that the results output directory, markdown directory, and LLM are selected.",
            )
            return

        subject_name = self.subject_input.text()
        subject_dob = self.dob_input.text()
        case_info = self.case_info_input.toPlainText()

        combined_summary_filename = f"{subject_name}_Combined_Summaries.md" if subject_name else "Combined_Summaries.md"
        combined_summary_path = os.path.join(
            self.results_output_directory, "summaries", combined_summary_filename
        )

        if not os.path.exists(combined_summary_path):
            QMessageBox.warning(
                self,
                "File Not Found",
                f"Combined summary file not found at: {combined_summary_path}. "
                "Please generate and combine summaries first.",
            )
            return
            
        # Original markdown files
        original_markdown_files = self.get_markdown_files()
        if not original_markdown_files:
            QMessageBox.warning(
                self, "No Markdown Files", "No markdown files found in the selected directory."
            )
            return

        progress_dialog = QProgressDialog(
            "Generating Integrated Analysis...", "Cancel", 0, 0, self
        )
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)
        progress_dialog.show()

        self.integrate_button.setEnabled(False)

        # Create and start the integrated analysis thread
        self.integrated_analysis_thread = IntegratedAnalysisThread(
            self,
            combined_summary_path,
            original_markdown_files,
            self.results_output_directory,
            subject_name,
            subject_dob,
            case_info,
            self.status_panel,
            progress_dialog,
            self.selected_llm_provider_id,
            self.selected_llm_model_name
        )
        self.integrated_analysis_thread.finished_signal.connect(
            self.on_integrated_analysis_finished
        )
        self.integrated_analysis_thread.error_signal.connect(
            self.on_integrated_analysis_error
        )
        self.integrated_analysis_thread.start()

    def on_integrated_analysis_finished(
        self, success, message, file_path, progress_dialog
    ):
        """Handle completion of integrated analysis."""
        # Close the progress dialog
        progress_dialog.close()

        # Update the status
        if success:
            self.workflow_indicator.update_status(
                WorkflowStep.INTEGRATE_ANALYSIS, "complete"
            )
            self.show_status("Integrated analysis complete")
            self.status_panel.append_details(
                f"Created integrated analysis: {file_path}"
            )

            QMessageBox.information(
                self,
                "Integration Complete",
                f"Successfully generated integrated analysis.\n\n{message}\n\nOutput file: {file_path}",
            )
        else:
            self.workflow_indicator.update_status(
                WorkflowStep.INTEGRATE_ANALYSIS, "error"
            )
            self.show_status("Integrated analysis failed")
            self.status_panel.append_details(f"Error: {message}")

            QMessageBox.critical(
                self,
                "Integration Failed",
                f"Failed to generate integrated analysis: {message}",
            )

        # Refresh file list to show new file
        self.refresh_file_list()

        # Update workflow state to ensure buttons are properly enabled/disabled
        self.check_workflow_state()

    def on_integrated_analysis_error(self, error, progress_dialog):
        """Handle error during integrated analysis."""
        # Close the progress dialog
        progress_dialog.close()

        # Update the status
        self.workflow_indicator.update_status(
            WorkflowStep.INTEGRATE_ANALYSIS, "error"
        )
        self.show_status("Integrated analysis failed")
        self.status_panel.append_details(f"Error: {error}")

        # Show error message
        QMessageBox.critical(
            self,
            "Integration Failed",
            f"Failed to generate integrated analysis: {error}"
        )

        # Refresh file list
        self.refresh_file_list()
