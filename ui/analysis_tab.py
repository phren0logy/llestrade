"""
Analysis tab module for the Forensic Psych Report Drafter.
Handles document summarization, integration, and analysis using LLM.
"""

import os
import re
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
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

from config import DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE
from ui.base_tab import BaseTab
from ui.components.file_selector import FileSelector
from ui.components.status_panel import StatusPanel
from ui.components.workflow_indicator import WorkflowIndicator, WorkflowStep
from ui.workers.integrated_analysis_thread import IntegratedAnalysisThread
from ui.workers.llm_summary_thread import LLMSummaryThread


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

        # Initialize the base tab
        super().__init__(parent, status_bar)

        # Set the tab title
        self.setWindowTitle("Analysis & Integration")

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

        # Create operation buttons group
        operations_group = QGroupBox("Analysis Operations")
        operations_layout = QVBoxLayout()

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

        self.file_selector = QComboBox()
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

        # Add status panel at the bottom
        self.status_panel = StatusPanel()
        main_layout.addWidget(self.status_panel)

        # Set the main layout
        self.layout.addLayout(main_layout)

    def on_markdown_folder_selected(self, directory):
        """Handle selection of markdown folder directory."""
        if not directory:
            return

        self.markdown_directory = directory
        self.status_panel.append_details(f"Markdown directory set to: {directory}")
        self.check_workflow_state()

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
            try:
                markdown_files = [
                    f for f in os.listdir(self.markdown_directory) if f.endswith(".md")
                ]
                has_markdown = bool(markdown_files)
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
                # Look for summary files in the root directory
                summary_files = [
                    f
                    for f in os.listdir(self.results_output_directory)
                    if f.endswith("_summary.md")
                ]
                has_summaries = bool(summary_files)
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
                    self.results_output_directory, "combined_summary.md"
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
                self.llm_process_button.setEnabled(
                    has_markdown and valid_subject and valid_dob
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
        """Refresh the list of available files in the combobox."""
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

        # Get all files from the output directory
        files = []

        # Look for all markdown files in the output directory
        for file in os.listdir(self.results_output_directory):
            if file.endswith(".md"):
                files.append(os.path.join(self.results_output_directory, file))

        # Sort files by modification time (newest first)
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

        # Add files to the selector
        for file in files:
            display_name = os.path.basename(file)
            self.file_selector.addItem(display_name, file)

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
        """Safely summarize markdown files with LLM after validating directories."""
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
                "Directory Not Found",
                f"The selected markdown directory does not exist: {self.markdown_directory}",
            )
            return

        # Check if results output directory is selected and exists
        if (
            not hasattr(self, "results_output_directory")
            or not self.results_output_directory
        ):
            QMessageBox.warning(
                self,
                "Missing Directory",
                "Please select a results output directory first.",
            )
            return

        if not os.path.exists(self.results_output_directory):
            try:
                os.makedirs(self.results_output_directory)
                self.status_panel.append_details(
                    f"Created results output directory: {self.results_output_directory}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Directory Creation Error",
                    f"Failed to create results output directory: {str(e)}",
                )
                return

        # Now proceed with the LLM summarization
        self.summarize_with_llm()

    def summarize_with_llm(self):
        """Summarize the markdown files with LLM."""
        # Get the subject name and case information
        subject_name = self.subject_input.text().strip()
        subject_dob = self.dob_input.text().strip()
        case_info = self.case_info_input.toPlainText().strip()

        # Validate required fields
        if not subject_name:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter the subject's name before summarizing.",
            )
            return

        if not subject_dob:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter the subject's date of birth before summarizing.",
            )
            return

        # Validate date of birth format
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", subject_dob):
            QMessageBox.warning(
                self,
                "Invalid Date Format",
                "Please enter the date of birth in YYYY-MM-DD format.",
            )
            return

        # Get markdown files from the selected markdown directory
        markdown_files = self.get_markdown_files()
        if not markdown_files:
            QMessageBox.warning(
                self,
                "No Files Found",
                "No markdown files found for summarization. Please check the selected directory.",
            )
            return

        # Set output directory to the root directory instead of a subdirectory
        output_dir = self.results_output_directory
        self.status_panel.append_details(f"Using output directory: {output_dir}")

        # Update workflow indicator
        self.workflow_indicator.update_status(WorkflowStep.SUMMARIZE_LLM, "in_progress")

        # Create progress dialog
        progress_dialog = QProgressDialog(
            "Summarizing documents with LLM...",
            "Cancel",
            0,
            len(markdown_files),
            self,
        )
        progress_dialog.setWindowTitle("LLM Summarization")
        progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.show()

        # Create thread for LLM processing
        self.llm_thread = LLMSummaryThread(
            markdown_files,
            output_dir,  # Now using the root output directory
            subject_name,
            subject_dob,
            case_info,
        )
        self.llm_thread.progress_signal.connect(
            lambda pct, msg: self.update_llm_progress(pct, msg)
        )
        self.llm_thread.finished_signal.connect(
            lambda results: self.on_llm_summarization_finished(results, progress_dialog)
        )
        self.llm_thread.error_signal.connect(
            lambda error: self.on_llm_summarization_error(error, progress_dialog)
        )

        # Connect the cancel button of the progress dialog to stop the thread
        progress_dialog.canceled.connect(self.llm_thread.terminate)

        # Start the thread
        self.llm_thread.start()

    def get_markdown_files(self):
        """Get a list of all markdown files in the markdown directory."""
        markdown_files = []

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

        # Get all markdown files in the directory
        if os.path.isdir(self.markdown_directory):
            for file in os.listdir(self.markdown_directory):
                if file.endswith(".md"):
                    markdown_files.append(os.path.join(self.markdown_directory, file))

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

    def update_llm_progress(self, percent, message):
        """Update the progress for LLM summarization."""
        # Update status panel
        self.status_panel.append_details(message)

        # Update the status bar
        self.show_status(f"LLM: {message}", percent)

    def on_llm_summarization_finished(self, results, progress_dialog):
        """Handle completion of LLM summarization."""
        try:
            # Close the progress dialog
            progress_dialog.close()

            # Safely handle the results - check if it's a dictionary
            if not isinstance(results, dict):
                # Handle string or other unexpected types
                self.show_status(
                    f"LLM summarization completed with unexpected result format"
                )
                self.status_panel.append_details(
                    f"Unexpected result format: {type(results)}"
                )
                self.workflow_indicator.update_status(
                    WorkflowStep.SUMMARIZE_LLM, "error"
                )

                # Show error message
                QMessageBox.warning(
                    self,
                    "Summarization Result Error",
                    f"LLM summarization completed but returned an unexpected result format. Please check logs.",
                )
                return

            # Update status message
            try:
                num_success = sum(
                    1 for r in results.get("files", []) if r.get("status") == "success"
                )
                num_total = results.get("total", 0)
                self.show_status(
                    f"LLM summarization completed: {num_success}/{num_total} files processed"
                )

                # Show detailed results in the console
                for result in results.get("files", []):
                    if result.get("status") == "success":
                        self.status_panel.append_details(
                            f"Summarized: {os.path.basename(result.get('file', 'unknown'))}"
                        )
                    else:
                        self.status_panel.append_details(
                            f"Failed to summarize {os.path.basename(result.get('file', 'unknown'))}: {result.get('error', 'Unknown error')}"
                        )
            except Exception as e:
                # Handle any other errors in processing the results
                self.status_panel.append_details(f"Error processing results: {str(e)}")
                num_success = 0
                num_total = 0

            # Update workflow indicator
            if num_success == num_total and num_total > 0:
                self.workflow_indicator.update_status(
                    WorkflowStep.SUMMARIZE_LLM, "complete"
                )
            elif num_success > 0:
                self.workflow_indicator.update_status(
                    WorkflowStep.SUMMARIZE_LLM, "partial"
                )
            else:
                self.workflow_indicator.update_status(
                    WorkflowStep.SUMMARIZE_LLM, "error"
                )

            # Show message box with results
            QMessageBox.information(
                self,
                "Summarization Complete",
                f"LLM summarization completed.\n\n{num_success} of {num_total} files were successfully summarized.\n\n"
                f"Summaries saved to: {self.results_output_directory}",
            )

            # Update file list
            self.refresh_file_list()

        except Exception as e:
            # Catch any unexpected errors to prevent crashes
            self.status_panel.append_details(
                f"Error in summarization completion handler: {str(e)}"
            )
            self.show_status("Error finishing LLM summarization")
            self.workflow_indicator.update_status(WorkflowStep.SUMMARIZE_LLM, "error")

    def on_llm_summarization_error(self, error, progress_dialog):
        """Handle error in LLM summarization."""
        # Close the progress dialog
        if progress_dialog and progress_dialog.isVisible():
            progress_dialog.close()

        # Update workflow indicator
        self.workflow_indicator.update_status(WorkflowStep.SUMMARIZE_LLM, "error")

        # Show error in status panel
        self.status_panel.append_details(f"LLM summarization error: {error}")

        # Show error message box
        QMessageBox.critical(
            self,
            "LLM Summarization Error",
            f"An error occurred during LLM summarization:\n\n{error}",
        )

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

        # Get all summary files from the output directory
        summary_files = []
        for file in os.listdir(self.results_output_directory):
            if file.endswith("_summary.md"):
                summary_files.append(os.path.join(self.results_output_directory, file))

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
        combined_file = os.path.join(
            self.results_output_directory, "combined_summary.md"
        )

        with open(combined_file, "w", encoding="utf-8") as f:
            f.write(combined_text)

        # Complete the progress dialog
        self.update_progress(progress_dialog, 100, "Combine operation complete!")

        # Show success message
        QMessageBox.information(
            self,
            "Combine Complete",
            f"Successfully combined {len(summary_files)} summary files.\n\nOutput file: {combined_file}",
        )

        # Update status and workflow
        self.workflow_indicator.update_status(
            WorkflowStep.COMBINE_SUMMARIES, "complete"
        )
        self.show_status(
            f"Combined {len(summary_files)} summary files into {os.path.basename(combined_file)}"
        )
        self.status_panel.append_details(f"Created combined summary: {combined_file}")

        # Update file list
        self.refresh_file_list()

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
        """Generate an integrated analysis from the combined summary."""
        # Get the subject name and case information
        subject_name = self.subject_input.text().strip()
        subject_dob = self.dob_input.text().strip()
        case_info = self.case_info_input.toPlainText().strip()

        # Validate required fields
        if not subject_name:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter the subject's name before generating an integrated analysis.",
            )
            return

        if not subject_dob:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter the subject's date of birth before generating an integrated analysis.",
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
        combined_file = os.path.join(
            self.results_output_directory, "combined_summary.md"
        )
        if not os.path.exists(combined_file):
            QMessageBox.warning(
                self,
                "No Combined Summary",
                "No combined summary file found. Please combine summaries first.",
            )
            return

        # Update workflow indicator
        self.workflow_indicator.update_status(
            WorkflowStep.INTEGRATE_ANALYSIS, "in_progress"
        )

        # Create a progress dialog
        progress_dialog = QProgressDialog(
            "Generating integrated analysis...",
            "Cancel",
            0,
            100,
            self,
        )
        progress_dialog.setWindowTitle("Integrated Analysis")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setValue(10)
        progress_dialog.show()

        # Create a worker thread for integrated analysis
        self.integrated_thread = IntegratedAnalysisThread(
            combined_file,
            self.results_output_directory,
            subject_name,
            subject_dob,
            case_info,
        )

        # Connect signals
        self.integrated_thread.progress_signal.connect(
            lambda pct, msg: self.update_progress(progress_dialog, pct, msg)
        )
        self.integrated_thread.finished_signal.connect(
            lambda success, message, file_path: self.on_integrated_analysis_finished(
                success, message, file_path, progress_dialog
            )
        )
        self.integrated_thread.error_signal.connect(
            lambda error: self.on_integrated_analysis_error(error, progress_dialog)
        )

        # Connect cancel signal
        progress_dialog.canceled.connect(self.integrated_thread.terminate)

        # Start the thread
        self.integrated_thread.start()

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

    def on_integrated_analysis_error(self, error, progress_dialog):
        """Handle error in integrated analysis."""
        # Close the progress dialog
        if progress_dialog and progress_dialog.isVisible():
            progress_dialog.close()

        # Update workflow indicator
        self.workflow_indicator.update_status(WorkflowStep.INTEGRATE_ANALYSIS, "error")

        # Show error message
        self.status_panel.append_details(f"Integration error: {error}")

        QMessageBox.critical(
            self,
            "Integration Error",
            f"An error occurred during integrated analysis:\n\n{error}",
        )
