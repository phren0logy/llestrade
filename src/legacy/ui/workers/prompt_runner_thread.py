"""
Worker thread for running prompts through Claude and saving results.
"""

import os
import time
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from src.core.file_utils import write_file_content
from src.common.llm.factory import create_provider


class PromptRunnerThread(QThread):
    """Worker thread for running prompts through Claude and saving results."""

    progress_signal = Signal(int, str)
    finished_signal = Signal(dict)
    error_signal = Signal(str)

    def __init__(self, prompts, output_dir, transcript_path):
        """Initialize the thread with the prompts to run."""
        super().__init__()
        self.prompts = prompts
        self.output_dir = output_dir
        self.transcript_path = transcript_path
        self.llm_provider = create_provider(provider="auto")

    def run(self):
        """Run the prompts through the LLM and save results."""
        try:
            # Send initial progress
            self.progress_signal.emit(
                0, f"Starting to process {len(self.prompts)} prompts"
            )

            # Create output file path with date and transcript name
            current_date = datetime.now().strftime("%Y-%m-%d")
            transcript_filename = os.path.basename(self.transcript_path)
            transcript_name = os.path.splitext(transcript_filename)[0]
            output_filename = (
                f"{current_date}-report-objective-section-{transcript_name}.md"
            )
            output_path = os.path.join(self.output_dir, output_filename)

            # Initialize results tracking
            results = {
                "processed": 0,
                "failed": 0,
                "output_path": output_path,
                "start_time": time.time(),
            }

            # Combined output content
            combined_output = f"# Report for {transcript_name}\n\n"
            combined_output += (
                f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            )

            # Process each prompt
            for i, prompt in enumerate(self.prompts):
                try:
                    # Update progress
                    progress_pct = int((i / len(self.prompts)) * 100)
                    self.progress_signal.emit(
                        progress_pct,
                        f"Processing prompt {i+1}/{len(self.prompts)}: {prompt['template_name']}",
                    )

                    # Send prompt to Claude
                    response = self.llm_provider.generate(
                        prompt=prompt["content"],
                        temperature=0.1,
                    )

                    if response["success"]:
                        # Add content to combined output
                        combined_output += f"\n## {prompt['template_name']}\n\n"
                        combined_output += response["content"]
                        combined_output += "\n\n---\n\n"

                        results["processed"] += 1
                    else:
                        self.progress_signal.emit(
                            progress_pct,
                            f"Failed to process prompt {i+1}: {response.get('error', 'Unknown error')}",
                        )
                        results["failed"] += 1
                except Exception as e:
                    self.progress_signal.emit(
                        progress_pct, f"Error processing prompt {i+1}: {str(e)}"
                    )
                    results["failed"] += 1

            # Write the combined output to file
            write_file_content(output_path, combined_output)

            # Calculate elapsed time
            results["elapsed_time"] = time.time() - results["start_time"]

            # Send finished signal
            self.progress_signal.emit(100, "Completed processing prompts")
            self.finished_signal.emit(results)

        except Exception as e:
            self.error_signal.emit(f"Error in prompt runner thread: {str(e)}")