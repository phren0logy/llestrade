"""
Prompts tab module for the Forensic Psych Report Drafter.
Handles the markdown processing and template generation functionality.
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE, DEFAULT_TIMEOUT
from file_utils import read_file_content, read_file_preview, write_file_content
from ingest_markdown import generate_template_fragments, ingest_and_split_markdown
from llm_utils import LLMClient, combine_transcript_with_fragments
from ui.base_tab import BaseTab
from ui.components.file_selector import FileSelector
from ui.components.progress_dialog import ProgressDialog
from ui.components.results_viewer import ResultsViewer
from ui.components.status_panel import StatusPanel
from ui.components.workflow_indicator import WorkflowIndicator
from ui.workers.prompt_runner_thread import PromptRunnerThread


class PromptsTab(BaseTab):
    """
    Tab for processing markdown templates with transcripts to generate LLM prompts.
    Provides UI for selecting files, viewing templates, and generating prompts.
    """

    def __init__(self, parent=None, status_bar=None):
        """Initialize the Prompts tab."""
        # Initialize state variables
        self.current_prompts = []
        self.current_markdown_path = None
        self.current_transcript_path = None

        # Create UI elements that will be referenced in check_ready_state
        self.process_button = None
        self.export_button = None
        self.run_prompts_button = None
        self.markdown_selector = None
        self.transcript_selector = None
        self.workflow_indicator = None

        # Initialize the base tab
        super().__init__(parent, status_bar)

    def setup_ui(self):
        """Set up the UI components for the Prompts tab."""
        # Create workflow indicator
        self.workflow_indicator = WorkflowIndicator()
        self.workflow_indicator.add_step(
            1, "1. Select Files", "Select template files to process"
        )
        self.workflow_indicator.add_step(
            2, "2. Process Template", "Process template with parameters"
        )
        self.workflow_indicator.add_step(3, "3. Review", "Review generated prompts")
        self.layout.addWidget(self.workflow_indicator)

        # Create file selectors
        file_selectors_layout = QHBoxLayout()

        # Add markdown file selector
        self.markdown_selector = FileSelector(
            title="Markdown Template",
            button_text="Select Markdown File",
            file_mode=QFileDialog.FileMode.ExistingFile,
            file_filter="Markdown Files (*.md)",
            placeholder_text="No markdown template selected",
            callback=self.on_markdown_selected,
        )
        file_selectors_layout.addWidget(self.markdown_selector)

        # Add transcript file selector
        self.transcript_selector = FileSelector(
            title="Transcript File",
            button_text="Select Transcript File",
            file_mode=QFileDialog.FileMode.ExistingFile,
            file_filter="Text Files (*.txt *.md)",
            placeholder_text="No transcript selected",
            callback=self.on_transcript_selected,
        )
        file_selectors_layout.addWidget(self.transcript_selector)

        self.layout.addLayout(file_selectors_layout)

        # Create template and prompt view
        self.results_viewer = ResultsViewer(
            header_labels=["Templates", "Type", "Status"],
            placeholder_text="Select a template file to view its contents",
        )
        self.results_viewer.item_selected.connect(self.on_template_selected)
        self.layout.addWidget(self.results_viewer)

        # Add action buttons
        button_layout = QHBoxLayout()

        # Add process button
        self.process_button = QPushButton("Process Template")
        self.process_button.setEnabled(False)
        self.process_button.clicked.connect(self.process_template)
        button_layout.addWidget(self.process_button)

        # Add export button
        self.export_button = QPushButton("Export Prompts")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_prompts)
        button_layout.addWidget(self.export_button)

        # Add run prompts button
        self.run_prompts_button = QPushButton("Run Prompts and Save Results")
        self.run_prompts_button.setEnabled(False)
        self.run_prompts_button.clicked.connect(self.run_prompts_and_save)
        button_layout.addWidget(self.run_prompts_button)

        self.layout.addLayout(button_layout)

        # Add status panel
        self.status_panel = StatusPanel("Processing Status")
        self.layout.addWidget(self.status_panel)

        # Update UI state
        self.check_ready_state()

    def on_markdown_selected(self, file_path):
        """Handle markdown file selection."""
        # Store the path
        self.current_markdown_path = file_path
        self.load_markdown_preview()
        self.check_ready_state()
        self.workflow_indicator.update_status(1, "in_progress")
        self.workflow_indicator.set_status_message("Markdown template selected")

    def on_transcript_selected(self, file_path):
        """Handle transcript file selection."""
        # Store the path
        self.current_transcript_path = file_path
        self.load_transcript_preview()
        self.check_ready_state()
        self.workflow_indicator.update_status(1, "in_progress")
        self.workflow_indicator.set_status_message("Transcript file selected")

    def on_template_selected(self, item, column):
        """Handle template item selection in the tree view."""
        # Get item data
        template_name = item.text(0)
        template_type = item.text(1)

        # Display the appropriate content based on the type
        if template_type == "Template":
            # Display the original template
            self.display_template_content(template_name)
        elif template_type == "Prompt":
            # Display the generated prompt
            self.display_prompt_content(template_name)

    def display_template_content(self, template_name):
        """Display the content of a template."""
        # Find the template content
        for template in self.current_templates:
            if template["name"] == template_name:
                self.results_viewer.set_content(template["content"])
                return

        self.results_viewer.set_content(f"Template '{template_name}' not found.")

    def display_prompt_content(self, template_name):
        """Display the content of a prompt."""
        # Find the prompt content
        for prompt in self.current_prompts:
            if prompt["template_name"] == template_name:
                self.results_viewer.set_content(prompt["content"])
                return

        self.results_viewer.set_content(f"Prompt for '{template_name}' not found.")

    def load_markdown_preview(self):
        """Load and display a preview of the selected markdown file."""
        if not self.current_markdown_path:
            return

        # Read the file content
        content = read_file_preview(self.current_markdown_path, max_lines=20)

        # Display preview
        self.results_viewer.set_content(
            f"Preview of {os.path.basename(self.current_markdown_path)}:\n\n{content}"
        )

    def load_transcript_preview(self):
        """Load and display a preview of the selected transcript file."""
        if not self.current_transcript_path:
            return

        # Read the file content
        content = read_file_preview(self.current_transcript_path, max_lines=20)

        # Display preview
        self.results_viewer.set_content(
            f"Preview of {os.path.basename(self.current_transcript_path)}:\n\n{content}"
        )

    def check_ready_state(self):
        """Check if all requirements are met to enable the process button."""
        # Check if both a markdown template and transcript have been selected
        has_markdown = self.markdown_selector.selected_path is not None
        has_transcript = self.transcript_selector.selected_path is not None
        ready = has_markdown and has_transcript
        
        # Enable or disable the process button based on ready state
        self.process_button.setEnabled(ready)
        
        # Check if we have processed prompts
        has_prompts = len(self.current_prompts) > 0
        
        # Debug info
        self.status_panel.append_details(f"Check ready state - has prompts: {has_prompts}, count: {len(self.current_prompts)}")
        
        # Enable/disable the export and run prompts buttons based on having prompts
        self.export_button.setEnabled(has_prompts)
        self.run_prompts_button.setEnabled(has_prompts)
        
        # Update the workflow indicator steps
        if has_markdown and has_transcript:
            self.workflow_indicator.update_status(1, "complete")
            current_step = 2
        else:
            self.workflow_indicator.update_status(1, "not_started")
            current_step = 1
            
        if has_prompts:
            self.workflow_indicator.update_status(2, "complete")
            self.workflow_indicator.update_status(3, "in_progress")
        else:
            self.workflow_indicator.update_status(2, "not_started")
            self.workflow_indicator.update_status(3, "not_started")
        
        # Show status message
        status_message = "Ready to process" if ready else "Select markdown template and transcript"
        self.show_status(status_message)

    def process_template(self):
        """Process the selected template with the transcript."""
        if not self.current_markdown_path or not self.current_transcript_path:
            self.show_status(
                "Please select both a markdown template and transcript file"
            )
            return

        try:
            # Show processing status
            self.show_status(
                f"Processing template: {os.path.basename(self.current_markdown_path)}"
            )
            self.status_panel.append_details(
                f"Reading markdown file: {self.current_markdown_path}"
            )

            # Read the template and transcript
            markdown_content = read_file_content(self.current_markdown_path)
            transcript_content = read_file_content(self.current_transcript_path)

            # Process the template
            self.status_panel.append_details("Generating template fragments...")
            # First split the markdown into parts, then generate fragments
            markdown_parts = ingest_and_split_markdown(self.current_markdown_path)
            self.current_templates = generate_template_fragments(markdown_parts)

            # Combine with transcript to create prompts
            self.status_panel.append_details("Combining with transcript...")
            self.current_prompts = []

            for template in self.current_templates:
                # Combine the template content with the transcript
                prompt = {
                    "template_name": template["name"],
                    "content": combine_transcript_with_fragments(
                        transcript_content, template["content"]
                    ),
                }
                self.current_prompts.append(prompt)

            # Debug info
            prompt_count = len(self.current_prompts)
            self.status_panel.append_details(f"Generated {prompt_count} prompts")
            print(f"DEBUG: Generated {prompt_count} prompts")

            # Update the tree view with templates and prompts
            self.results_viewer.clear_tree()

            # Add templates
            template_root = self.results_viewer.add_tree_item(None, "Templates")
            for template in self.current_templates:
                self.results_viewer.add_tree_item(
                    template_root,
                    template["name"],
                    **{"1": "Template", "2": "Original"},
                )

            # Add prompts
            prompt_root = self.results_viewer.add_tree_item(None, "Prompts")
            for prompt in self.current_prompts:
                self.results_viewer.add_tree_item(
                    prompt_root,
                    prompt["template_name"],
                    **{"1": "Prompt", "2": "Generated"},
                )

            # Expand both roots
            template_root.setExpanded(True)
            prompt_root.setExpanded(True)

            # Select the first prompt
            if self.current_prompts:
                prompt_item = prompt_root.child(0)
                self.results_viewer.tree.setCurrentItem(prompt_item)
                self.display_prompt_content(prompt_item.text(0))

            # Update status
            self.show_status(f"Generated {len(self.current_prompts)} prompts")

            # IMPORTANT: Directly set the buttons without using check_ready_state
            if self.current_prompts:
                print(f"DEBUG: Enabling buttons directly")
                self.export_button.setEnabled(True)
                self.run_prompts_button.setEnabled(True)

            # Now update workflow indicators
            self.check_ready_state()

        except Exception as e:
            self.show_status(f"Error processing template: {str(e)}")
            self.status_panel.append_details(f"Error: {str(e)}")

    def export_prompts(self):
        """Export the generated prompts to files."""
        if not self.current_prompts:
            self.show_status("No prompts to export")
            return

        # Ask user for export directory
        export_dir = QFileDialog.getExistingDirectory(
            self, "Select Export Directory", "", QFileDialog.Option.ShowDirsOnly
        )

        if not export_dir:
            return

        try:
            # Export each prompt
            exported_count = 0
            for prompt in self.current_prompts:
                # Create filename from template name
                filename = f"{prompt['template_name']}_prompt.txt"
                file_path = os.path.join(export_dir, filename)

                # Write the prompt to file
                write_file_content(file_path, prompt["content"])
                exported_count += 1

                self.status_panel.append_details(f"Exported: {filename}")

            # Update status
            self.show_status(f"Exported {exported_count} prompts to {export_dir}")

        except Exception as e:
            self.show_status(f"Error exporting prompts: {str(e)}")
            self.status_panel.append_details(f"Error: {str(e)}")

    def run_prompts_and_save(self):
        """Run all prompts through Claude and save the results to a file."""
        if not self.current_prompts:
            self.show_status("No prompts to run")
            return

        # Ask user for output directory
        output_dir = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", "", QFileDialog.Option.ShowDirsOnly
        )

        if not output_dir:
            return

        try:
            # Create progress dialog
            progress_dialog = ProgressDialog(
                "Running Prompts", "Processing prompts through Claude...", parent=self
            )

            # Create and configure the prompt runner thread
            self.prompt_runner_thread = PromptRunnerThread(
                self.current_prompts, output_dir, self.current_transcript_path
            )

            # Connect signals
            self.prompt_runner_thread.progress_signal.connect(
                progress_dialog.update_progress
            )
            self.prompt_runner_thread.finished_signal.connect(
                self.on_prompt_runner_finished
            )
            self.prompt_runner_thread.error_signal.connect(self.on_prompt_runner_error)

            # Start the thread
            self.prompt_runner_thread.start()
            progress_dialog.exec()

        except Exception as e:
            self.show_status(f"Error running prompts: {str(e)}")
            self.status_panel.append_details(f"Error: {str(e)}")

    def on_prompt_runner_finished(self, results):
        """Handle completion of prompt runner thread."""
        # Show summary of results
        elapsed_time = results["elapsed_time"]
        minutes = int(elapsed_time / 60)
        seconds = int(elapsed_time % 60)

        summary = (
            f"Processed {results['processed']} prompts in {minutes}m {seconds}s. "
            f"Failed: {results['failed']}. "
            f"Results saved to: {results['output_path']}"
        )

        self.show_status(summary)
        self.status_panel.append_details(summary)

        # Offer to open the output file
        reply = QMessageBox.question(
            self,
            "Open Results File",
            f"Would you like to view the generated report?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply == QMessageBox.StandardButton.Yes:
            with open(results["output_path"], "r", encoding="utf-8") as f:
                content = f.read()
            self.results_viewer.set_content(content)

    def on_prompt_runner_error(self, error_message):
        """Handle errors from the prompt runner thread."""
        self.show_status(f"Error running prompts: {error_message}")
        self.status_panel.append_details(f"Error: {error_message}")

    def show_status(self, message):
        """Show a status message in both status indicators."""
        self.status_panel.update_summary(message)
        self.workflow_indicator.set_status_message(message)
        # Also call the base class method
        super().show_status(message)
