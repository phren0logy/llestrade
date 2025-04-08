"""
Worker thread for generating an integrated analysis with Claude's thinking model.
"""

import os
import time
from PyQt6.QtCore import QThread, pyqtSignal

from llm_utils import LLMClient


class IntegratedAnalysisThread(QThread):
    """Worker thread for generating an integrated analysis with Claude's thinking model."""

    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, combined_file, output_dir, subject_name, subject_dob, case_info):
        """Initialize the thread with the combined summary file."""
        super().__init__()
        self.combined_file = combined_file
        self.output_dir = output_dir
        self.subject_name = subject_name
        self.subject_dob = subject_dob
        self.case_info = case_info
        self.llm_client = LLMClient()

    def run(self):
        """Run the integrated analysis."""
        try:
            # Send initial progress
            self.progress_signal.emit(0, "Starting integrated analysis...")

            # Read the combined summary content
            with open(self.combined_file, "r", encoding="utf-8") as f:
                combined_content = f.read()

            # Update progress
            self.progress_signal.emit(20, "Creating prompt for Claude...")

            # Create the prompt for Claude's thinking
            prompt = self.create_integrated_prompt(combined_content)

            # Update progress
            self.progress_signal.emit(40, "Sending to Claude for analysis...")

            # Call Claude with the prompt and extended thinking
            response = self.llm_client.generate_response(
                prompt_text=prompt,
                system_prompt=f"You are analyzing documents for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}",
                temperature=0.1,  # Low temperature for more factual responses
                model="claude-3-7-sonnet-20250219",  # Use the latest model with high context
            )

            # Update progress
            self.progress_signal.emit(80, "Processing response...")

            if not response["success"]:
                raise Exception(
                    f"LLM processing failed: {response.get('error', 'Unknown error')}"
                )

            # Define the output file
            integrated_file = os.path.join(self.output_dir, "integrated_analysis.md")

            # Write the integrated analysis to a file
            with open(integrated_file, "w", encoding="utf-8") as f:
                f.write(f"# Integrated Analysis for {self.subject_name}\n\n")
                f.write(f"**Date of Birth:** {self.subject_dob}\n\n")
                f.write(f"*Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
                f.write(response["content"])

            # Update progress
            self.progress_signal.emit(100, "Integrated analysis complete!")

            # Signal completion
            self.finished_signal.emit(integrated_file)

        except Exception as e:
            self.error_signal.emit(f"Error during integrated analysis: {str(e)}")

    def create_integrated_prompt(self, combined_content):
        """
        Create a prompt for Claude to generate an integrated analysis.

        Args:
            combined_content: Content of the combined summary file

        Returns:
            Prompt string
        """
        return f"""
# Integrated Document Analysis Task

## Subject Information
- **Subject Name**: {self.subject_name}
- **Date of Birth**: {self.subject_dob}

## Case Background
{self.case_info}

## Instructions
I'm providing you with multiple document summaries that contain information about the subject (or subjects). Please analyze all of these summaries and create a comprehensive integrated report per subject that includes:

1. **Executive Summary**: A clear, concise overview of the subject based on all documents (700-1000 words).

2. **Comprehensive Timeline**: Create a single, unified timeline that combines all events from the individual document timelines. The timeline should:
   - Be in chronological order (oldest to newest)
   - Be formatted as a markdown table with columns for Date, Event, Significance, and Source Document Name(s)
   - Calculate the subject's age at each significant event when relevant (using DOB: {self.subject_dob})
   - Remove duplicate events, preserving multiple Source Document Names
   - Resolve any conflicting information if possible (noting discrepancies) - document all resolved and unresolved discrepancies in a separate section
   - Include source information when possible

3. **Key Findings**: Synthesize the most important information about:
   - Family relationships and social history
   - Educational and employment background
   - Legal history and interactions with authorities
   - Substance use and treatment history
   - Medical and psychiatric history
   - Notable patterns of behavior
   - Adverse life events

4. **Significant Observations**: Highlight particularly noteworthy information that appears across multiple documents or seems especially relevant.

Please use your thinking capabilities to connect information across documents, identify patterns, and create a coherent narrative from these separate summaries. When information appears contradictory, note the discrepancy rather than trying to resolve it definitively.

## Combined Document Summaries
{combined_content}
"""
