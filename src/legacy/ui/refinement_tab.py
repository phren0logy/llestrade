"""
Refinement tab module for the Forensic Psych Report Drafter.
Handles the report refinement with extended thinking functionality.
"""

import logging
import os
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
)

from src.config.config import DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE, DEFAULT_TIMEOUT
from src.core.file_utils import read_file_content, read_file_preview, write_file_content
from src.common.llm.factory import create_provider
from src.core.prompt_manager import PromptManager
from ui.base_tab import BaseTab
from ui.components.file_selector import FileSelector
from ui.components.results_viewer import ResultsViewer
from ui.components.status_panel import StatusPanel
from ui.components.workflow_indicator import WorkflowIndicator


class RefinementThread(QThread):
    """Thread for running report refinement in the background."""

    update_signal = Signal(str)
    thinking_signal = Signal(str)
    result_signal = Signal(str)
    finished_signal = Signal()

    def __init__(
        self, report_path, instructions, template_path=None, transcript_path=None, prompt_manager=None
    ):
        """Initialize the refinement thread.
        
        Args:
            report_path: Path to the report file
            instructions: Instructions for refinement
            template_path: Optional path to template file
            transcript_path: Optional path to transcript file
            prompt_manager: Optional PromptManager instance
        """
        super().__init__()
        self.report_path = report_path
        self.instructions = instructions
        self.template_path = template_path
        self.transcript_path = transcript_path
        self.prompt_manager = prompt_manager

    def run(self):
        """Run the report refinement process."""
        try:
            # Read the report content
            self.update_signal.emit(f"Reading report from {self.report_path}")
            report_content = read_file_content(self.report_path)

            # Read template content if available
            template_content = ""
            if self.template_path:
                self.update_signal.emit(f"Reading template from {self.template_path}")
                template_content = read_file_content(self.template_path)
                self.update_signal.emit("Template loaded successfully")

            # Read transcript content if available
            transcript_content = ""
            if self.transcript_path:
                self.update_signal.emit(
                    f"Reading transcript from {self.transcript_path}"
                )
                transcript_content = read_file_content(self.transcript_path)
                self.update_signal.emit("Transcript loaded successfully")

            # Create LLM provider using factory
            self.update_signal.emit("Initializing LLM provider...")
            llm_provider = create_provider(
                provider="anthropic",  # Force Anthropic for Claude 4 Sonnet with reasoning
                timeout=DEFAULT_TIMEOUT * 10,  # Increased timeout for refinement (5 minutes)
                max_retries=3,
                debug=True
            )

            if not llm_provider or not llm_provider.initialized:
                raise Exception("Failed to initialize Anthropic provider. Please check your ANTHROPIC_API_KEY.")

            # Build the refinement prompt using the prompt manager
            if hasattr(self, 'prompt_manager') and self.prompt_manager is not None:
                try:
                    prompt = self.prompt_manager.get_template(
                        "refinement_prompt",
                        instructions=self.instructions,
                        report_content=report_content,
                        template_section=f"<template>\n{template_content}\n</template>" if template_content else "",
                        transcript_section=f"<transcript>\n{transcript_content}\n</transcript>" if transcript_content else ""
                    )
                except Exception as e:
                    self.update_signal.emit(f"Error building prompt: {str(e)}")
                    prompt = self._build_fallback_prompt(report_content, template_content, transcript_content)
            else:
                prompt = self._build_fallback_prompt(report_content, template_content, transcript_content)

            # Generate response with thinking
            self.update_signal.emit("Sending report to Claude 4 Sonnet for refinement...")

            # Use the generate_with_thinking method
            response = llm_provider.generate_with_thinking(
                prompt=prompt,
                model="claude-sonnet-4-20250514",  # Updated to Claude 4 Sonnet
                max_tokens=64000,
                temperature=1.0,  # Required for thinking mode
                thinking_budget=32000,
            )

            # Check if the response was successful
            if not response["success"]:
                error_message = response.get("error", "Unknown error occurred")
                self.update_signal.emit(f"Error: {error_message}")
                return

            # Extract content and thinking from the response
            refined_report = response["content"]
            thinking_process = response.get("thinking", "No thinking process available")

            # Output the thinking process for visibility
            if thinking_process:
                self.thinking_signal.emit("Thinking process from Claude:")

                # Split thinking by lines to make it more readable in the UI
                thinking_lines = thinking_process.strip().split("\n")
                for line in thinking_lines:
                    if line.strip():
                        self.thinking_signal.emit(line.strip())

            # Send the result
            self.update_signal.emit("Refinement complete!")
            self.result_signal.emit(refined_report)

        except Exception as e:
            self.update_signal.emit(f"Error: {str(e)}")

        # Signal that processing is complete
        self.finished_signal.emit()


class RefinementTab(BaseTab):
    """
    Tab for report refinement using Claude's extended thinking.
    Provides UI for selecting a report, providing refinement instructions,
    and viewing the refined output.
    """

    def __init__(self, parent=None, status_bar=None):
        """Initialize the Refinement tab."""
        # Initialize state variables
        self.current_report_path = None
        self.current_template_path = None
        self.current_transcript_path = None
        self.refinement_thread = None
        
        # Initialize prompt manager
        self.prompt_manager = self._initialize_prompt_manager()

        # Initialize the base tab
        super().__init__(parent, status_bar)

    def setup_ui(self):
        """Set up the UI components for the Refinement tab."""
        # Do NOT call super().setup_ui() as it raises NotImplementedError
        # The layout is already created in BaseTab.__init__

        # Create and add the workflow indicator
        self.workflow_indicator = WorkflowIndicator()
        self.workflow_indicator.add_step(
            1, "1. Select Report", "Select a report to refine"
        )
        self.workflow_indicator.add_step(
            2, "2. Add Instructions", "Add refinement instructions"
        )
        self.workflow_indicator.add_step(
            3, "3. Refine Report", "Process the report with LLM"
        )
        self.workflow_indicator.add_step(
            4, "4. Save Results", "Save the refined report"
        )
        self.layout.addWidget(self.workflow_indicator)

        # Create file selector
        self.report_selector = FileSelector(
            title="Draft Report File",
            button_text="Select Draft Report",
            file_mode=QFileDialog.FileMode.ExistingFile,
            file_filter="Markdown Files (*.md);;Text Files (*.txt)",
            placeholder_text="No report selected",
            callback=self.on_report_selected,
        )
        self.layout.addWidget(self.report_selector)

        # Create template file selector
        self.template_selector = FileSelector(
            title="Template File (Optional)",
            button_text="Select Template",
            file_mode=QFileDialog.FileMode.ExistingFile,
            file_filter="Markdown Files (*.md);;Text Files (*.txt)",
            placeholder_text="No template selected",
            callback=self.on_template_selected,
        )
        self.layout.addWidget(self.template_selector)

        # Create transcript file selector
        self.transcript_selector = FileSelector(
            title="Transcript File (Optional)",
            button_text="Select Transcript",
            file_mode=QFileDialog.FileMode.ExistingFile,
            file_filter="Text Files (*.txt);;Markdown Files (*.md)",
            placeholder_text="No transcript selected",
            callback=self.on_transcript_selected,
        )
        self.layout.addWidget(self.transcript_selector)

        # Create instruction input area
        instruction_layout = QVBoxLayout()
        instruction_layout.addWidget(QLabel("Refinement Instructions:"))

        self.instruction_text = QTextEdit()
        self.instruction_text.setMinimumHeight(100)

        # Set placeholder text
        self.instruction_text.setPlaceholderText(
            """Enter instructions for refining the report..."""
        )

        instruction_layout.addWidget(self.instruction_text)

        self.layout.addLayout(instruction_layout)

        # Create results viewer
        self.results_viewer = ResultsViewer(
            header_labels=["Files", "Type", "Status"],
            placeholder_text="Select a report and provide refinement instructions",
        )
        self.layout.addWidget(self.results_viewer)

        # Add action buttons
        button_layout = QHBoxLayout()

        # Add refine button
        self.refine_button = QPushButton("Refine Report & Auto-Save Results")
        self.refine_button.setEnabled(False)
        self.refine_button.clicked.connect(self.refine_report)
        button_layout.addWidget(self.refine_button)

        # Add save-as button
        self.save_as_button = QPushButton("Save Results to Different Location")
        self.save_as_button.setEnabled(False)
        self.save_as_button.clicked.connect(
            lambda: self.save_refined_report(auto_save=False)
        )
        button_layout.addWidget(self.save_as_button)

        self.layout.addLayout(button_layout)

        # Add status panel
        self.status_panel = StatusPanel("Refinement Status")
        self.layout.addWidget(self.status_panel)

        # Connect signals after all UI elements are created
        self.instruction_text.textChanged.connect(self.check_ready_state)

        # Set initial instruction text from template
        try:
            default_instruction = self.prompt_manager.get_template("refinement_instructions")
            self.instruction_text.setText(default_instruction)
        except Exception as e:
            logging.error(f"Failed to load refinement instructions: {e}")
            # Fallback to hardcoded instructions if template loading fails
            default_instruction = """This draft report, wrapped in <draft> tags, is a rough draft of a forensic psychiatric report. Perform the following steps in sequential order to improve the report:
            1. Ignore the contents of block quotes. The errors belong to the source document being quoted. Never modify the contents of block quotes.
            2. Check each section for information that is repeated in other sections. Put this information in the most appropriate section. If a template is provided, it will be wrapped in <template> tags. If duplicate information is found, after placing it in the most appropriate section, reference that section in other parts of the report where that information was removed.
            3. After making those changes, revise the document for readability. Preserve details that are important for accurate diagnosis and formulation. Make sure that verbs are in past tense for information that came from the interview. Do not use the word "denied," instead say "did not report," "did not endorse," etc.
            4. Check the report against a transcript, if provided. The transcript is wrapped in <transcript> tags. Pay careful attention to direct quotes. Minor changes in directly quoted statements from the transcript, such as punctuation and capitalization, or removal of words with an ellipsis, are acceptable and do not need to be changed.
            5. Use words instead of numerals for one through ten, and numbers for 11 and above. Spell out decades, such as "twenties" instead of 20s.
            6. Some information may not appear in the transcript, such as quotes from other documents or psychometric testing. Do not make changes to this information that does not appear in the transcript. Do make a note of it in your thinking.
            7. Output only the final revised report."""
            self.instruction_text.setText(default_instruction)

        # Update UI state
        self.check_ready_state()

    def _initialize_prompt_manager(self) -> PromptManager:
        """Initialize and return a PromptManager instance.
        
        Returns:
            PromptManager: Initialized prompt manager
        """
        try:
            # Look for prompt templates in the application directory
            app_dir = Path(__file__).parent.parent
            template_dir = app_dir / 'prompt_templates'
            
            # Fall back to current directory if not found
            if not template_dir.exists():
                template_dir = Path('prompt_templates')
                
            return PromptManager(template_dir=template_dir)
            
        except Exception as e:
            logging.error(f"Failed to initialize prompt manager: {e}")
            # Return a dummy prompt manager that will use fallback prompts
            return type('DummyPromptManager', (), {
                'get_template': lambda self, name, **kwargs: ""
            })()
            
    def _build_fallback_prompt(self, report_content: str, template_content: str = "", transcript_content: str = "") -> str:
        """Build a fallback prompt when template loading fails.
        
        Args:
            report_content: Content of the report
            template_content: Optional template content
            transcript_content: Optional transcript content
            
        Returns:
            Formatted prompt string
        """
        prompt = f"""
        Please help refine the following report, following these instructions:
        
        {self.instructions}
        
        Here is the report:
        
        <draft>
        {report_content}
        </draft>
        """

        # Add template content if available
        if template_content:
            prompt += f"""
            
            Here is the template to follow:
            
            <template>
            {template_content}
            </template>
            """

        # Add transcript content if available
        if transcript_content:
            prompt += f"""
            
            Here is the transcript:
            
            <transcript>
            {transcript_content}
            </transcript>
            """
            
        return prompt
            
    def on_report_selected(self, file_path):
        """Handle report file selection."""
        self.current_report_path = file_path
        self.load_report_preview()
        self.check_ready_state()
        self.workflow_indicator.update_status(1, "complete")
        self.workflow_indicator.set_status_message("Report selected")

    def load_report_preview(self):
        """Load and display a preview of the selected report file."""
        if not self.current_report_path:
            return

        # Read the file content
        content = read_file_preview(self.current_report_path, max_lines=30)

        # Display preview
        self.results_viewer.set_content(
            f"Preview of {os.path.basename(self.current_report_path)}:\n\n{content}"
        )

    def check_ready_state(self):
        """Check if all requirements are met to enable the refine button."""
        # A report must be selected and instructions provided to refine
        has_report = self.current_report_path is not None
        has_instructions = self.instruction_text.toPlainText().strip() != ""

        # Template and transcript are optional
        ready = has_report and has_instructions

        # Update button state
        self.refine_button.setEnabled(ready)

        # Update workflow indicator
        if has_report:
            self.workflow_indicator.update_status(1, "complete")
        else:
            self.workflow_indicator.update_status(1, "not_started")

        if has_instructions:
            self.workflow_indicator.update_status(2, "complete")
        else:
            self.workflow_indicator.update_status(2, "not_started")

        # Update the status message
        status_message = (
            "Ready to refine" if ready else "Select report and provide instructions"
        )
        self.workflow_indicator.set_status_message(status_message)

    def refine_report(self):
        """Start the report refinement process."""
        if not self.current_report_path:
            self.show_status("Please select a report file")
            return

        instructions = self.instruction_text.toPlainText().strip()
        if not instructions:
            self.show_status("Please provide refinement instructions")
            return

        # Update the workflow indicator
        self.workflow_indicator.update_status(3, "in_progress")
        self.workflow_indicator.set_status_message("Refining report...")

        # Create and start the refinement thread
        self.refinement_thread = RefinementThread(
            report_path=self.current_report_path,
            instructions=instructions,
            template_path=self.current_template_path,
            transcript_path=self.current_transcript_path,
            prompt_manager=self.prompt_manager
        )

        # Connect signals
        self.refinement_thread.update_signal.connect(self.update_refinement_status)
        self.refinement_thread.thinking_signal.connect(self.update_thinking_status)
        self.refinement_thread.result_signal.connect(self.set_refinement_result)
        self.refinement_thread.finished_signal.connect(self.refinement_completed)

        # Start processing
        self.refinement_thread.start()

        # Disable buttons during processing
        self.refine_button.setEnabled(False)

        # Show status
        self.show_status("Refining report... Please wait")
        self.status_panel.update_summary("Refinement in progress")
        self.status_panel.append_details(f"Refining report: {self.current_report_path}")
        if self.current_template_path:
            self.status_panel.append_details(
                f"Using template: {self.current_template_path}"
            )
        if self.current_transcript_path:
            self.status_panel.append_details(
                f"Using transcript: {self.current_transcript_path}"
            )
        self.status_panel.append_details(f"Instructions: {instructions[:100]}...")

    def update_refinement_status(self, message):
        """Update the status panel with a refinement message."""
        self.status_panel.append_details(message)
        self.workflow_indicator.set_status_message(message)

    def update_thinking_status(self, thinking):
        """Update the status panel with thinking process."""
        self.status_panel.append_details(f"Claude thinking: {thinking}")

        # Store thinking process for later saving
        if not hasattr(self, "thinking_process"):
            self.thinking_process = []
        self.thinking_process.append(thinking)

    def set_refinement_result(self, result):
        """Set the refinement result in the results viewer."""
        self.refined_report = result
        self.results_viewer.set_content(result)
        self.save_as_button.setEnabled(True)

    def refinement_completed(self):
        """Handle completion of report refinement."""
        # Re-enable buttons
        self.refine_button.setEnabled(True)

        # Update status
        self.show_status("Refinement complete")
        self.status_panel.update_summary("Report refinement complete")

        # Update workflow indicator
        self.workflow_indicator.update_status(3, "complete")
        self.workflow_indicator.set_status_message("Refinement complete")

        # Auto-save results
        if hasattr(self, "refined_report"):
            self.status_panel.append_details("Auto-saving results...")
            self.save_refined_report(auto_save=True)

    def save_refined_report(self, auto_save=False):
        """Save the refined report to a file."""
        if not hasattr(self, "refined_report"):
            self.show_status("No refined report to save")
            return

        if auto_save and not self.current_report_path:
            self.show_status("Cannot auto-save without a source report file")
            return

        # Get the directory of the original report
        if self.current_report_path:
            original_dir = os.path.dirname(self.current_report_path)
            original_filename = os.path.basename(self.current_report_path)
            base_name, ext = os.path.splitext(original_filename)
        else:
            # Fallback if no report path is available
            original_dir = os.getcwd()
            base_name = "refined_report"
            ext = ".md"

        if auto_save:
            # Auto-save to the same directory as the original report
            report_save_path = os.path.join(original_dir, f"{base_name}_refined{ext}")
            thinking_save_path = os.path.join(original_dir, f"{base_name}_thinking.md")
        else:
            # Ask user for save location
            report_save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Refined Report",
                os.path.join(original_dir, f"{base_name}_refined{ext}"),
                "Markdown Files (*.md);;Text Files (*.txt)",
            )

            if not report_save_path:
                return

            # Generate thinking path based on report path
            thinking_save_path = f"{os.path.splitext(report_save_path)[0]}_thinking.md"

        try:
            # Write the refined report to file
            write_file_content(report_save_path, self.refined_report)

            # Save thinking process if available
            if hasattr(self, "thinking_process") and self.thinking_process:
                write_file_content(thinking_save_path, "\n".join(self.thinking_process))
                self.status_panel.append_details(
                    f"Saved thinking to: {thinking_save_path}"
                )

            # Update status
            self.show_status(f"Saved refined report to {report_save_path}")
            self.status_panel.append_details(f"Saved report to: {report_save_path}")

        except Exception as e:
            self.show_status(f"Error saving files: {str(e)}")

    def show_status(self, message):
        """Show a status message in both status indicators."""
        self.status_panel.update_summary(message)
        self.workflow_indicator.set_status_message(message)
        # Also call the base class method
        super().show_status(message)

    def on_template_selected(self, file_path):
        """Handle template file selection."""
        self.current_template_path = file_path
        self.load_template_preview()
        self.check_ready_state()

    def load_template_preview(self):
        """Load and display a preview of the selected template file."""
        if not self.current_template_path:
            return

        # Read the file content
        content = read_file_preview(self.current_template_path, max_lines=30)

        # Display preview (append to existing content if report is already loaded)
        current_content = self.results_viewer.get_content()
        if current_content and "Preview of" in current_content:
            self.results_viewer.set_content(
                f"{current_content}\n\n------\n\nPreview of Template {os.path.basename(self.current_template_path)}:\n\n{content}"
            )
        else:
            self.results_viewer.set_content(
                f"Preview of Template {os.path.basename(self.current_template_path)}:\n\n{content}"
            )

    def on_transcript_selected(self, file_path):
        """Handle transcript file selection."""
        self.current_transcript_path = file_path
        self.load_transcript_preview()
        self.check_ready_state()

    def load_transcript_preview(self):
        """Load and display a preview of the selected transcript file."""
        if not self.current_transcript_path:
            return

        # Read the file content
        content = read_file_preview(self.current_transcript_path, max_lines=30)

        # Display preview (append to existing content if report is already loaded)
        current_content = self.results_viewer.get_content()
        if current_content and "Preview of" in current_content:
            self.results_viewer.set_content(
                f"{current_content}\n\n------\n\nPreview of Transcript {os.path.basename(self.current_transcript_path)}:\n\n{content}"
            )
        else:
            self.results_viewer.set_content(
                f"Preview of Transcript {os.path.basename(self.current_transcript_path)}:\n\n{content}"
            )
