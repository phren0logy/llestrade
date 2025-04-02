"""
Worker thread for summarizing markdown files with Claude.
"""

import os

from PyQt6.QtCore import QThread, pyqtSignal

from llm_utils import LLMClient


class LLMSummaryThread(QThread):
    """Worker thread for summarizing markdown files with Claude."""

    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, markdown_files, output_dir, subject_name, case_info):
        """Initialize the thread with the markdown files to summarize."""
        super().__init__()
        self.markdown_files = markdown_files
        self.output_dir = output_dir
        self.subject_name = subject_name
        self.case_info = case_info
        self.llm_client = LLMClient()

    def run(self):
        """Run the LLM summarization operations."""
        try:
            # Send initial progress
            self.progress_signal.emit(
                0, f"Starting LLM summarization for {len(self.markdown_files)} files"
            )

            # Create summaries directory if it doesn't exist
            summaries_dir = os.path.join(self.output_dir, "summaries")
            os.makedirs(summaries_dir, exist_ok=True)

            # Process files in batches to update progress
            total_files = len(self.markdown_files)
            results = {
                "total": total_files,
                "processed": 0,
                "skipped": 0,
                "failed": 0,
                "files": [],
            }

            # Process each file and update progress
            for i, markdown_path in enumerate(self.markdown_files):
                try:
                    # Update progress
                    progress_pct = int((i / total_files) * 100)
                    self.progress_signal.emit(
                        progress_pct, f"Summarizing: {os.path.basename(markdown_path)}"
                    )

                    # Get basename for output file
                    basename = os.path.splitext(os.path.basename(markdown_path))[0]
                    summary_file = os.path.join(summaries_dir, f"{basename}_summary.md")

                    # Check if already processed
                    if os.path.exists(summary_file):
                        results["skipped"] += 1
                        results["files"].append(
                            {
                                "markdown": markdown_path,
                                "status": "skipped",
                                "summary": summary_file,
                            }
                        )
                        continue

                    # Process the file with Claude
                    summary_path = self.summarize_markdown_file(
                        markdown_path, summary_file
                    )

                    # Update results
                    results["processed"] += 1
                    results["files"].append(
                        {
                            "markdown": markdown_path,
                            "status": "processed",
                            "summary": summary_path,
                        }
                    )

                except Exception as e:
                    results["failed"] += 1
                    results["files"].append(
                        {"markdown": markdown_path, "status": "failed", "error": str(e)}
                    )

            # Signal completion with results
            self.finished_signal.emit(results)

        except Exception as e:
            self.error_signal.emit(f"Error during LLM summarization: {str(e)}")

    def summarize_markdown_file(self, markdown_path, summary_file):
        """
        Summarize a markdown file using the LLM.

        Args:
            markdown_path: Path to the markdown file
            summary_file: Path to save the summary

        Returns:
            Path to the summary file
        """
        # Read the markdown content
        with open(markdown_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()

        # Create the prompt for Claude
        document_name = os.path.basename(markdown_path)
        prompt = self.create_summary_prompt(document_name, markdown_content)

        # Call Claude with the prompt
        response = self.llm_client.generate_response(
            prompt_text=prompt,
            system_prompt=f"You are analyzing documents for {self.subject_name}. The following case information provides context: {self.case_info}",
            temperature=0.1,  # Low temperature for more factual responses
        )

        if not response["success"]:
            raise Exception(
                f"LLM processing failed: {response.get('error', 'Unknown error')}"
            )

        # Write the summary to a file
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(f"# Summary of {document_name}\n\n")
            f.write(f"## Document Analysis for {self.subject_name}\n\n")
            f.write(response["content"])

        return summary_file

    def create_summary_prompt(self, document_name, markdown_content):
        """
        Create a prompt for Claude to summarize a document.

        Args:
            document_name: Name of the document
            markdown_content: Content of the markdown file

        Returns:
            Prompt string
        """
        return f"""
# Document Analysis Task

## Document Information
- **Subject Name**: {self.subject_name}
- **Document**: {document_name}

## Case Background
{self.case_info}

## Instructions
Please analyze the following document and provide a comprehensive summary that includes:

- Key facts and information about the subject
- Significant events and dates mentioned
- Family relationships and social history
- Relevant family history or relationships
- Educational history
- Employment history
- Military career history
- Legal issues or encounters with law enforcement
- Substance use and treatment history
- Medical and psychiatric history
- Any notable statements or quotes
- Notable patterns of behavior
- Adverse life events
- A timeline of events in a markdown table format with columns for Date, Event, and Significance



Keep your analysis focused on factual information directly stated in the document. 
Organize the timeline chronologically with the most recent events at the bottom.

## Document Content
{markdown_content}"""
