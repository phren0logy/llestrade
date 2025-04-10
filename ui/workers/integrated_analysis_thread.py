"""
Worker thread for generating an integrated analysis with Claude's thinking model.
"""

import os
import time
import traceback

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication

from llm_utils import LLMClient


class IntegratedAnalysisThread(QThread):
    """Worker thread for generating an integrated analysis with Claude's thinking model."""

    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool, str, str)  # success, message, file_path
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

    def process_api_response(self, prompt, system_prompt, use_gemini=False):
        """Process API response with detailed error handling and retries."""
        max_retries = 3
        retry_count = 0
        retry_delay = 2  # seconds
        timeout_seconds = 600  # 10 minutes timeout for long analysis

        while retry_count < max_retries:
            try:
                # Log which provider is being used
                if use_gemini:
                    provider = "Google Gemini"
                    self.progress_signal.emit(
                        45, "Using Gemini API for large token context"
                    )
                else:
                    provider = "Anthropic Claude"
                    self.progress_signal.emit(45, "Using Claude API")

                self.progress_signal.emit(
                    50,
                    f"Sending request to {provider} (attempt {retry_count + 1}/{max_retries})...",
                )

                # Create a detailed log of the API parameters
                self.progress_signal.emit(
                    50, f"System prompt length: {len(system_prompt)} chars"
                )
                self.progress_signal.emit(50, f"Prompt length: {len(prompt)} chars")

                # Time the API call for debugging
                start_time = time.time()

                # Set a timer to update the progress dialog and keep UI responsive during long API calls
                elapsed = 0
                last_update = 0

                # Create a background task with progress updates
                from PyQt6.QtCore import QEventLoop, QTimer

                # Prepare the request parameters
                if use_gemini:
                    # For Gemini, we may need to include system prompt in the main prompt
                    combined_prompt = f"{system_prompt}\n\n{prompt}"
                    request_params = {
                        "prompt_text": combined_prompt,
                        "system_prompt": "",  # Empty for Gemini which may not support separate system prompts
                        "temperature": 0.1,
                        "use_gemini": True,  # Force using Gemini
                    }
                else:
                    # For Claude, use normal approach
                    request_params = {
                        "prompt_text": prompt,
                        "system_prompt": system_prompt,
                        "temperature": 0.1,
                        "model": "claude-3-7-sonnet-20250219",
                    }

                # Create an event to track API response completion
                response = None
                api_error = None
                api_complete = False

                # Start the API call in the current thread, but use a timer to update progress
                # This won't block the UI thread but will keep our current thread busy
                def make_api_call():
                    nonlocal response, api_error, api_complete
                    try:
                        response = self.llm_client.generate_response(**request_params)
                        api_complete = True
                    except Exception as e:
                        api_error = e
                        api_complete = True

                # Start API call in a parallel thread
                import threading

                api_thread = threading.Thread(target=make_api_call)
                api_thread.daemon = True
                api_thread.start()

                # Update progress while waiting for the API call to complete
                wait_interval = 1.0  # Update every second
                while not api_complete:
                    # Update elapsed time
                    elapsed = time.time() - start_time

                    # Send progress update every 5 seconds
                    if elapsed - last_update >= 5:
                        self.progress_signal.emit(
                            52,
                            f"Still waiting for response from {provider}... (elapsed: {int(elapsed)}s)",
                        )
                        last_update = elapsed

                    # Check for timeout
                    if elapsed > timeout_seconds:
                        self.progress_signal.emit(
                            50, f"API request timed out after {timeout_seconds} seconds"
                        )
                        api_thread.join(0.1)  # Try to join but don't block
                        raise Exception(
                            f"API request timed out after {timeout_seconds} seconds"
                        )

                    # Sleep briefly to avoid hammering the CPU
                    time.sleep(wait_interval)

                    # Process UI events
                    QApplication.processEvents()

                # Check for API errors
                if api_error:
                    raise api_error

                # Log response time
                elapsed_time = time.time() - start_time
                self.progress_signal.emit(
                    75, f"API response received in {elapsed_time:.2f} seconds"
                )

                # Check response
                if not response["success"]:
                    error_msg = response.get("error", "Unknown error")
                    self.progress_signal.emit(
                        50, f"LLM API returned error: {error_msg}"
                    )

                    # Check for specific error types that should trigger retry
                    if (
                        "rate limit" in error_msg.lower()
                        or "timeout" in error_msg.lower()
                    ):
                        if retry_count < max_retries - 1:
                            retry_count += 1
                            wait_time = retry_delay * (
                                2**retry_count
                            )  # Exponential backoff
                            self.progress_signal.emit(
                                50,
                                f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/{max_retries})",
                            )
                            time.sleep(wait_time)
                            continue

                    # If we get here, either we've exhausted retries or it's a non-retryable error
                    raise Exception(f"LLM API error: {error_msg}")

                self.progress_signal.emit(
                    78, f"LLM response received: {len(response['content'])} chars"
                )

                # Check if the response is empty
                if not response.get("content"):
                    self.progress_signal.emit(50, "LLM returned empty response")
                    raise Exception("LLM returned empty response")

                # Log token usage for debugging
                if "usage" in response:
                    usage = response["usage"]
                    self.progress_signal.emit(
                        79,
                        f"Token usage - Input: {usage.get('input_tokens', 'unknown')}, Output: {usage.get('output_tokens', 'unknown')}",
                    )

                return response

            except Exception as e:
                error_details = traceback.format_exc()

                # Determine if we should retry
                should_retry = False
                error_msg = str(e).lower()

                # Common retryable errors
                retryable_errors = [
                    "timeout",
                    "connection",
                    "network",
                    "rate limit",
                    "too many requests",
                    "server error",
                    "503",
                    "502",
                    "504",
                    "429",
                    "500",
                ]

                for err in retryable_errors:
                    if err in error_msg:
                        should_retry = True
                        break

                if should_retry and retry_count < max_retries - 1:
                    retry_count += 1
                    wait_time = retry_delay * (2**retry_count)  # Exponential backoff
                    self.progress_signal.emit(
                        50,
                        f"Retryable error: {str(e)}. Retrying in {wait_time} seconds... (attempt {retry_count + 1}/{max_retries})",
                    )
                    time.sleep(wait_time)
                else:
                    # We've exhausted retries or hit a non-retryable error
                    self.progress_signal.emit(
                        50,
                        f"Error in API processing (final): {str(e)}\n{error_details}",
                    )
                    raise Exception(f"API processing error: {str(e)}")

        # If we get here, we've exhausted all retries
        raise Exception(f"Failed to get API response after {max_retries} attempts")

    def run(self):
        """Run the integrated analysis."""
        try:
            # Define the output file path
            integrated_file = os.path.join(self.output_dir, "integrated_analysis.md")

            # Check if the integrated analysis already exists
            if os.path.exists(integrated_file):
                self.progress_signal.emit(
                    100, "Integrated analysis file already exists, skipping generation."
                )
                success_message = (
                    f"Using existing integrated analysis file for {self.subject_name}"
                )
                self.finished_signal.emit(True, success_message, integrated_file)
                return

            # Send initial progress
            self.progress_signal.emit(0, "Starting integrated analysis...")

            # Read the combined summary content
            with open(self.combined_file, "r", encoding="utf-8") as f:
                combined_content = f.read()

            # Update progress
            self.progress_signal.emit(20, "Creating prompt for analysis...")

            # Create the prompt for analysis
            prompt = self.create_integrated_prompt(combined_content)

            # Count tokens to determine which LLM to use
            self.progress_signal.emit(
                30, "Counting tokens to select appropriate model..."
            )
            token_count_result = self.llm_client.count_tokens(text=prompt)

            use_gemini = False
            if token_count_result["success"]:
                token_count = token_count_result["token_count"]
                self.progress_signal.emit(35, f"Token count: {token_count}")

                # Use Gemini for large token counts (>120k)
                if token_count > 120000:
                    use_gemini = True
                    self.progress_signal.emit(38, "Using Gemini for large token count")
                else:
                    self.progress_signal.emit(
                        38, "Using Claude for token count <= 120k"
                    )
            else:
                self.progress_signal.emit(
                    35, "Token counting failed, using Claude as default"
                )

            # Update progress
            self.progress_signal.emit(40, "Sending for analysis...")

            # Use specific model based on token count
            system_prompt = f"You are analyzing documents for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}"

            # Use our new process_api_response method to handle timeouts, retries and errors
            response = self.process_api_response(prompt, system_prompt, use_gemini)

            # Update progress
            self.progress_signal.emit(80, "Processing response...")

            if not response["success"]:
                raise Exception(
                    f"LLM processing failed: {response.get('error', 'Unknown error')}"
                )

            # Write the integrated analysis to a file
            with open(integrated_file, "w", encoding="utf-8") as f:
                f.write(f"# Integrated Analysis for {self.subject_name}\n\n")
                f.write(f"**Date of Birth:** {self.subject_dob}\n\n")
                f.write(f"*Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
                f.write(response["content"])

            # Update progress
            self.progress_signal.emit(100, "Integrated analysis complete!")

            # Signal completion
            success_message = (
                f"Successfully generated integrated analysis for {self.subject_name}"
            )
            self.finished_signal.emit(True, success_message, integrated_file)

        except Exception as e:
            error_message = f"Error during integrated analysis: {str(e)}"
            self.error_signal.emit(error_message)

    def create_integrated_prompt(self, combined_content):
        """
        Create a prompt for the LLM to generate an integrated analysis.

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
   - Include source information when possible, including the original file name and page number

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
