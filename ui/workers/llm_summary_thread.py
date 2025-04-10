"""
Worker thread for summarizing markdown files with Claude.
"""

import logging
import os
import time

from PyQt6.QtCore import QThread, pyqtSignal

from llm_utils import LLMClient


def chunk_document_with_overlap(text, client, max_chunk_size=60000, overlap=1000):
    """
    Split a document into chunks of approximately max_chunk_size tokens with overlap.

    Args:
        text: The document text to chunk
        client: An instance of LLMClient to use for token counting
        max_chunk_size: Maximum tokens per chunk (default: 60000)
        overlap: Number of tokens to overlap between chunks (default: 1000)

    Returns:
        List of text chunks
    """
    # Calculate a safe max chunk size accounting for summary prompt and response
    safe_max_chunk_size = (
        max_chunk_size - 5000
    )  # Reserve tokens for prompt and other content

    # We'll use paragraphs as our base unit to avoid splitting mid-sentence
    paragraphs = [p for p in text.split("\n\n") if p.strip()]

    chunks = []
    current_paragraphs = []
    overlap_paragraphs = []

    i = 0
    while i < len(paragraphs):
        # Add the current paragraph
        current_paragraphs.append(paragraphs[i])

        # Check if we have enough paragraphs to test the size
        if len(current_paragraphs) % 10 == 0 or i == len(paragraphs) - 1:
            current_text = "\n\n".join(current_paragraphs)

            # Try to count tokens accurately
            token_count_result = client.count_tokens(text=current_text)

            # Get token count or estimate if counting failed
            if token_count_result["success"] and "token_count" in token_count_result:
                token_count = token_count_result["token_count"]
            else:
                # Fallback to a character-based estimation (more conservative than word-based)
                token_count = len(current_text) // 3  # Roughly 3 chars per token

            # If we've exceeded the safe limit, create a chunk
            if token_count > safe_max_chunk_size and len(current_paragraphs) > 1:
                # Remove the last paragraph that pushed us over the limit
                if i < len(paragraphs) - 1 or token_count > max_chunk_size:
                    current_paragraphs.pop()
                    i -= 1  # Adjust index to process this paragraph again

                # Create chunk from current paragraphs
                chunk_text = "\n\n".join(current_paragraphs)
                chunks.append(chunk_text)

                # Prepare overlap for next chunk (up to 5 paragraphs)
                overlap_size = min(len(current_paragraphs), 5)
                overlap_paragraphs = current_paragraphs[-overlap_size:]

                # Check if the overlap text itself is too large
                overlap_text = "\n\n".join(overlap_paragraphs)
                overlap_token_result = client.count_tokens(text=overlap_text)

                # If overlap is too large or token counting fails, reduce it
                if (
                    not overlap_token_result["success"]
                    or overlap_token_result.get("token_count", safe_max_chunk_size)
                    > safe_max_chunk_size // 2
                ):
                    # Try with fewer paragraphs, down to just one
                    for test_size in range(overlap_size - 1, 0, -1):
                        test_paragraphs = current_paragraphs[-test_size:]
                        test_text = "\n\n".join(test_paragraphs)
                        test_result = client.count_tokens(text=test_text)

                        if (
                            test_result["success"]
                            and test_result["token_count"] <= safe_max_chunk_size // 2
                        ):
                            overlap_paragraphs = test_paragraphs
                            break
                    else:
                        # Even a single paragraph is too big, use an empty list
                        overlap_paragraphs = []

                # Start a new chunk with the (potentially reduced) overlap paragraphs
                current_paragraphs = overlap_paragraphs.copy()

        i += 1

    # Add the last chunk if it wasn't already added
    if current_paragraphs and (
        not chunks or "\n\n".join(current_paragraphs) != chunks[-1]
    ):
        chunks.append("\n\n".join(current_paragraphs))

    return chunks


class LLMSummaryThread(QThread):
    """Worker thread for summarizing markdown files with Claude."""

    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(
        self, markdown_files, output_dir, subject_name, subject_dob, case_info
    ):
        """Initialize the thread with the markdown files to summarize."""
        super().__init__()
        self.markdown_files = markdown_files
        self.output_dir = output_dir
        self.subject_name = subject_name
        self.subject_dob = subject_dob
        self.case_info = case_info
        self.llm_client = None
        self._initialize_llm_client()

    def _initialize_llm_client(self):
        """Initialize LLM client with better error handling."""
        try:
            self.progress_signal.emit(0, "Initializing LLM client...")
            from llm_utils import LLMClient

            self.llm_client = LLMClient()
            # Test connection by sending a simple request
            test_result = self.llm_client.count_tokens(text="Test connection")
            if not test_result["success"]:
                error_msg = f"LLM client initialization test failed: {test_result.get('error', 'Unknown error')}"
                logging.error(error_msg)
                self.progress_signal.emit(0, error_msg)
            else:
                self.progress_signal.emit(0, "LLM client initialized successfully")
        except Exception as e:
            error_msg = f"Error initializing LLM client: {str(e)}"
            logging.error(error_msg)
            self.progress_signal.emit(0, error_msg)

    def run(self):
        """Run the LLM summarization operations."""
        try:
            # Verify LLM client is properly initialized
            if not self.llm_client:
                self._initialize_llm_client()
                if not self.llm_client:
                    raise Exception("Failed to initialize LLM client")

            # Check API connectivity
            connectivity_check = self.llm_client.count_tokens(text="Connectivity test")
            if not connectivity_check["success"]:
                raise Exception(
                    f"LLM API connectivity issue: {connectivity_check.get('error', 'Unknown error')}"
                )

            # Send initial progress
            self.progress_signal.emit(
                0, f"Starting LLM summarization for {len(self.markdown_files)} files"
            )

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
                    summary_file = os.path.join(
                        self.output_dir, f"{basename}_summary.md"
                    )

                    # Check if already processed
                    if os.path.exists(summary_file):
                        results["skipped"] += 1
                        results["files"].append(
                            {
                                "file": markdown_path,
                                "markdown": markdown_path,
                                "status": "skipped",
                                "summary": summary_file,
                            }
                        )
                        continue

                    # Process the file with Claude
                    try:
                        self.progress_signal.emit(
                            0,
                            f"Starting file processing: {os.path.basename(markdown_path)}",
                        )
                        summary_path = self.summarize_markdown_file(
                            markdown_path, summary_file
                        )
                        self.progress_signal.emit(
                            0,
                            f"Successfully summarized: {os.path.basename(markdown_path)}",
                        )

                        # Update results
                        results["processed"] += 1
                        results["files"].append(
                            {
                                "file": markdown_path,
                                "markdown": markdown_path,
                                "status": "success",  # Use "success" to be consistent
                                "summary": summary_path,
                            }
                        )
                    except Exception as e:
                        import traceback

                        error_details = traceback.format_exc()
                        error_msg = f"Summarization error for {os.path.basename(markdown_path)}: {str(e)}\n{error_details}"
                        self.progress_signal.emit(0, error_msg)

                        # Add to failed results
                        results["failed"] += 1
                        results["files"].append(
                            {
                                "file": markdown_path,
                                "markdown": markdown_path,
                                "status": "failed",
                                "error": str(e),
                                "error_details": error_details,
                            }
                        )
                except Exception as e:
                    import traceback

                    error_msg = str(e)
                    error_details = traceback.format_exc()
                    # Log detailed error information
                    self.progress_signal.emit(
                        0,
                        f"Error processing {os.path.basename(markdown_path)}: {error_msg}\n{error_details}",
                    )

                    results["failed"] += 1
                    results["files"].append(
                        {
                            "file": markdown_path,
                            "markdown": markdown_path,
                            "status": "failed",
                            "error": error_msg,
                            "error_details": error_details,
                        }
                    )

            # Signal completion with results
            self.progress_signal.emit(100, "Summarization complete")
            self.finished_signal.emit(results)

        except Exception as e:
            import traceback

            error_msg = f"Error during LLM summarization: {str(e)}"
            error_details = traceback.format_exc()
            self.progress_signal.emit(0, f"{error_msg}\n{error_details}")

            # Also emit the error signal for the UI to handle
            self.error_signal.emit(error_msg)

            # Make sure we don't crash silently
            import logging

            logging.error(f"Critical error in LLM summarization thread: {error_msg}")
            logging.error(error_details)

    def create_summary_prompt(self, document_name, markdown_content):
        """
        Create a prompt for Claude to summarize a document.

        Args:
            document_name: Name of the document
            markdown_content: Content of the markdown file

        Returns:
            Prompt string
        """
        self.progress_signal.emit(0, f"Creating prompt for {document_name}")
        prompt = f"""
## Document Content
<document-content>
{markdown_content}
</document-content>

# Document Analysis Task

## Document Information
- **Subject Name**: {self.subject_name}
- **Date of Birth**: {self.subject_dob}
- **Document**: {document_name}

## Case Background
{self.case_info}

## Instructions
Please analyze the document content above, wrapped in "document-content" tags, and provide a comprehensive summary that includes:

- Key facts and information about the subject
- Significant events and dates mentioned
- Family and romantic relationships
- Early childhood history
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

Inlude the page number for each of the items above.

## Timeline Instructions
- Create a timeline of events in a markdown table format with columns for Date, Event, and Significance
- Using the subject's date of birth ({self.subject_dob}), calculate the subject's age at each event when relevant
- When exact dates aren't provided, estimate years when possible and mark them with "(est.)"
- Organize the timeline chronologically with the most recent events at the bottom
- If there are multiple events on the same date, list them in the order they occurred
- If there are multiple events with the same date and significance, list them in the order they occurred

Keep your analysis focused on factual information directly stated in the document.
"""
        self.progress_signal.emit(0, f"Prompt created: {len(prompt)} characters")
        return prompt

    def test_llm_availability(self):
        """Test if the LLM client is available and working."""
        if not self.llm_client:
            self.progress_signal.emit(0, "LLM client not initialized")
            return False

        try:
            test_result = self.llm_client.count_tokens(text="Test connection")
            if not test_result["success"]:
                self.progress_signal.emit(
                    0,
                    f"LLM API test failed: {test_result.get('error', 'Unknown error')}",
                )
                return False

            # Check which provider is being used
            if (
                hasattr(self.llm_client, "anthropic_initialized")
                and self.llm_client.anthropic_initialized
            ):
                self.progress_signal.emit(0, "Using Anthropic API for summarization")
            elif (
                hasattr(self.llm_client, "gemini_initialized")
                and self.llm_client.gemini_initialized
            ):
                self.progress_signal.emit(0, "Using Gemini API for summarization")
            else:
                self.progress_signal.emit(
                    0, "Using unknown API provider for summarization"
                )

            return True
        except Exception as e:
            self.progress_signal.emit(0, f"Error testing LLM availability: {str(e)}")
            return False

    def process_api_response(self, prompt, system_prompt):
        """Process API response with detailed error handling and retries."""
        max_retries = 3
        retry_count = 0
        retry_delay = 2  # seconds

        while retry_count < max_retries:
            try:
                # First verify the LLM is available
                if not self.test_llm_availability():
                    # Try reinitializing
                    self.progress_signal.emit(
                        0, "LLM API not available, attempting to reinitialize"
                    )
                    self._initialize_llm_client()

                    if not self.test_llm_availability():
                        raise Exception(
                            "LLM API still not available after reinitialization"
                        )

                self.progress_signal.emit(
                    0,
                    f"Sending request to LLM API (attempt {retry_count + 1}/{max_retries})...",
                )

                # Create a detailed log of the API parameters
                self.progress_signal.emit(
                    0, f"Using model: {type(self.llm_client).__name__}"
                )
                self.progress_signal.emit(
                    0, f"System prompt length: {len(system_prompt)} chars"
                )
                self.progress_signal.emit(0, f"Prompt length: {len(prompt)} chars")

                # Log which provider is being used
                if (
                    hasattr(self.llm_client, "anthropic_initialized")
                    and self.llm_client.anthropic_initialized
                ):
                    provider = "Anthropic Claude"
                elif (
                    hasattr(self.llm_client, "gemini_initialized")
                    and self.llm_client.gemini_initialized
                ):
                    provider = "Google Gemini"
                else:
                    provider = "Unknown Provider"

                self.progress_signal.emit(0, f"Using {provider} for generation")

                # Time the API call for debugging
                start_time = time.time()

                # Try to send the request
                response = self.llm_client.generate_response(
                    prompt_text=prompt,
                    system_prompt=system_prompt,
                    temperature=0.1,
                    max_tokens=32000,  # Ensure adequate token limits
                )

                # Log response time
                elapsed_time = time.time() - start_time
                self.progress_signal.emit(
                    0, f"API response received in {elapsed_time:.2f} seconds"
                )

                # Check response
                if not response["success"]:
                    error_msg = response.get("error", "Unknown error")
                    self.progress_signal.emit(0, f"LLM API returned error: {error_msg}")

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
                                0,
                                f"Retrying in {wait_time} seconds... (attempt {retry_count + 1}/{max_retries})",
                            )
                            time.sleep(wait_time)
                            continue

                    # If we get here, either we've exhausted retries or it's a non-retryable error
                    raise Exception(f"LLM API error: {error_msg}")

                self.progress_signal.emit(
                    0, f"LLM response received: {len(response['content'])} chars"
                )

                # Check if the response is empty
                if not response.get("content"):
                    self.progress_signal.emit(0, "LLM returned empty response")
                    raise Exception("LLM returned empty response")

                # Log token usage for debugging
                if "usage" in response:
                    usage = response["usage"]
                    self.progress_signal.emit(
                        0,
                        f"Token usage - Input: {usage.get('input_tokens', 'unknown')}, Output: {usage.get('output_tokens', 'unknown')}",
                    )

                return response["content"]

            except Exception as e:
                import traceback

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
                        0,
                        f"Retryable error: {str(e)}. Retrying in {wait_time} seconds... (attempt {retry_count + 1}/{max_retries})",
                    )
                    time.sleep(wait_time)
                else:
                    # We've exhausted retries or hit a non-retryable error
                    self.progress_signal.emit(
                        0, f"Error in API processing (final): {str(e)}\n{error_details}"
                    )
                    raise Exception(f"API processing error: {str(e)}")

        # If we get here, we've exhausted all retries
        raise Exception(f"Failed to get API response after {max_retries} attempts")

    def summarize_markdown_file(self, markdown_path, summary_file):
        """
        Summarize a markdown file using the LLM, with chunking for large files.

        Args:
            markdown_path: Path to the markdown file
            summary_file: Path to save the summary

        Returns:
            Path to the summary file
        """
        try:
            # Log beginning of file processing
            document_name = os.path.basename(markdown_path)
            self.progress_signal.emit(0, f"Starting to process {document_name}")

            # Verify file exists and is readable
            if not os.path.exists(markdown_path):
                raise Exception(f"File does not exist: {markdown_path}")

            if not os.path.isfile(markdown_path):
                raise Exception(f"Path is not a file: {markdown_path}")

            # Check if the file is readable by attempting to get its stats
            try:
                file_stats = os.stat(markdown_path)
                file_size = file_stats.st_size
                self.progress_signal.emit(0, f"File size: {file_size} bytes")

                if file_size == 0:
                    raise Exception(f"File is empty: {markdown_path}")

                if file_size > 10_000_000:  # 10MB limit
                    raise Exception(
                        f"File is too large ({file_size} bytes): {markdown_path}"
                    )
            except Exception as e:
                raise Exception(f"Error accessing file: {str(e)}")

            # Read the markdown content
            try:
                self.progress_signal.emit(0, f"Reading file: {document_name}")
                with open(markdown_path, "r", encoding="utf-8") as f:
                    markdown_content = f.read()
                self.progress_signal.emit(
                    0, f"Successfully read file contents: {len(markdown_content)} bytes"
                )
            except UnicodeDecodeError:
                # Try with different encoding if UTF-8 fails
                try:
                    self.progress_signal.emit(
                        0, f"UTF-8 decoding failed, trying latin-1"
                    )
                    with open(markdown_path, "r", encoding="latin-1") as f:
                        markdown_content = f.read()
                    self.progress_signal.emit(
                        0,
                        f"Successfully read file with latin-1 encoding: {len(markdown_content)} bytes",
                    )
                except Exception as e:
                    raise Exception(f"Failed to read file with any encoding: {str(e)}")
            except PermissionError:
                raise Exception(f"Permission denied when reading file: {markdown_path}")
            except Exception as e:
                raise Exception(f"Error reading markdown file: {str(e)}")

            document_name = os.path.basename(markdown_path)

            # Verify output directory is writable
            output_dir = os.path.dirname(summary_file)
            if not os.path.exists(output_dir):
                try:
                    self.progress_signal.emit(
                        0, f"Creating output directory: {output_dir}"
                    )
                    os.makedirs(output_dir)
                except Exception as e:
                    raise Exception(f"Failed to create output directory: {str(e)}")

            # Test write permissions
            try:
                test_file = os.path.join(output_dir, ".test_write_permission")
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
            except Exception as e:
                raise Exception(f"Output directory is not writable: {str(e)}")

            # Check if summary file already exists
            if os.path.exists(summary_file):
                self.progress_signal.emit(
                    0, f"Summary file for {document_name} already exists, skipping."
                )
                return summary_file

            # Check if file is large enough to need chunking
            try:
                self.progress_signal.emit(0, f"Counting tokens in document")
                token_count_result = self.llm_client.count_tokens(text=markdown_content)
                if not token_count_result["success"]:
                    self.progress_signal.emit(
                        0,
                        f"Token counting failed: {token_count_result.get('error', 'Unknown error')}",
                    )
                    # Use character-based estimation as fallback
                    estimated_tokens = len(markdown_content) // 4
                    self.progress_signal.emit(
                        0,
                        f"Using character-based token estimate: ~{estimated_tokens} tokens",
                    )
                    token_count = {"success": True, "token_count": estimated_tokens}
                else:
                    token_count = token_count_result
                    self.progress_signal.emit(
                        0, f"File token count: {token_count['token_count']}"
                    )
            except Exception as e:
                self.progress_signal.emit(0, f"Error counting tokens: {str(e)}")
                # Use character-based estimation as fallback
                estimated_tokens = len(markdown_content) // 4
                self.progress_signal.emit(
                    0,
                    f"Using character-based token estimate: ~{estimated_tokens} tokens",
                )
                token_count = {"success": True, "token_count": estimated_tokens}

            if token_count["success"] and token_count["token_count"] > 30000:
                # Document is large, use chunking with specified parameters (60000 tokens, 1000 overlap)
                self.progress_signal.emit(
                    0,
                    f"Document {document_name} is large. Chunking with 60000 token size and 1000 token overlap.",
                )

                try:
                    # Split the document into chunks using the chunk_document_with_overlap function
                    self.progress_signal.emit(
                        0, "Breaking document into manageable chunks..."
                    )
                    chunks = chunk_document_with_overlap(
                        markdown_content,
                        self.llm_client,
                        max_chunk_size=60000,
                        overlap=1000,
                    )
                    self.progress_signal.emit(
                        0, f"Document split into {len(chunks)} chunks"
                    )

                    # Process each chunk separately
                    chunk_summaries = []
                    for i, chunk in enumerate(chunks):
                        self.progress_signal.emit(
                            0, f"Processing chunk {i+1}/{len(chunks)}..."
                        )

                        # Create a prompt for this specific chunk
                        chunk_prompt = self.create_summary_prompt(
                            f"{document_name} (chunk {i+1}/{len(chunks)})", chunk
                        )

                        # Send to LLM for summarization with retries
                        chunk_system_prompt = f"You are analyzing chunk {i+1}/{len(chunks)} of a document for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}"

                        self.progress_signal.emit(
                            0, f"Summarizing chunk {i+1}/{len(chunks)}..."
                        )

                        # Use Claude for each chunk summary
                        chunk_content = self.process_api_response(
                            chunk_prompt, chunk_system_prompt
                        )

                        # Store the chunk summary
                        chunk_summaries.append(
                            f"## Chunk {i+1}/{len(chunks)} Summary\n\n{chunk_content}"
                        )

                        self.progress_signal.emit(
                            0, f"Successfully summarized chunk {i+1}/{len(chunks)}"
                        )

                    # Combine all chunk summaries into a single text
                    self.progress_signal.emit(0, "Combining chunk summaries...")
                    combined_chunks = "\n\n".join(chunk_summaries)

                    # Combine the summaries using Anthropic's extended thinking functionality
                    self.progress_signal.emit(
                        0,
                        "Using Anthropic's extended thinking to create integrated summary...",
                    )

                    # Create a meta-summary prompt
                    meta_prompt = f"""
# Document Integration Task

## Document Information
- **Subject Name**: {self.subject_name}
- **Date of Birth**: {self.subject_dob}
- **Document**: {document_name}

## Document Analysis Context
The document was too large and had to be analyzed in {len(chunks)} separate chunks.
Below are the summaries for each chunk of the document.

## Instructions
Please analyze all the chunk summaries and create a unified, coherent summary of the entire document with the following elements:

1. **Document Overview**: Provide an overall summary of what the document contains
2. **Citations**: Include the  page number where possible for each extracted piece of information
2. **Key Facts**: Extract key facts and information about the subject from across all chunks
3. **Timeline**: Consolidate any timeline information from the chunks into a single, chronological timeline
4. **Major Findings**: Identify significant findings, patterns, or inconsistencies across the document
5. **Integration**: Use your thinking capabilities to connect information across chunks, identify overarching themes, and create a cohesive summary

Use extended thinking to work through the document summaries systematically before producing your final response.

## Chunk Summaries
{combined_chunks}
"""

                    # Verify that Anthropic is available
                    if (
                        not hasattr(self.llm_client, "anthropic_initialized")
                        or not self.llm_client.anthropic_initialized
                    ):
                        # Check if Gemini is available as an alternative
                        if (
                            hasattr(self.llm_client, "gemini_initialized")
                            and self.llm_client.gemini_initialized
                        ):
                            self.progress_signal.emit(
                                0,
                                "Anthropic not available, using Gemini's long context and step-by-step thinking capabilities",
                            )
                            # Use Gemini's thinking capability
                            thinking_response = self.llm_client.generate_response_with_gemini_thinking(
                                prompt_text=meta_prompt,
                                system_prompt=f"You are analyzing a large document for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}",
                                temperature=0.3,  # Lower temperature for more factual responses
                                max_output_tokens=32000,  # Gemini 1.5 Pro supports very large outputs
                            )

                            if not thinking_response["success"]:
                                raise Exception(
                                    f"Failed to combine chunks with Gemini thinking: {thinking_response.get('error', 'Unknown error')}"
                                )

                            # Log thinking process if available
                            if thinking_response.get("thinking"):
                                self.progress_signal.emit(
                                    0,
                                    f"Gemini performed {len(thinking_response['thinking'])} characters of reasoning process",
                                )

                                # Save thinking to a separate file for reference
                                thinking_file = os.path.join(
                                    os.path.dirname(summary_file),
                                    f"{os.path.basename(summary_file).replace('.md', '')}_gemini_reasoning.md",
                                )
                                with open(thinking_file, "w", encoding="utf-8") as f:
                                    f.write(
                                        f"# Gemini Analysis Reasoning Process for {document_name}\n\n"
                                    )
                                    f.write(
                                        "Gemini 2.5 Pro used its 2M token context window to analyze the document chunks.\n\n"
                                    )
                                    f.write(thinking_response["thinking"])

                                self.progress_signal.emit(
                                    0,
                                    f"Saved Gemini reasoning process to {thinking_file}",
                                )

                            final_content = thinking_response["content"]
                        else:
                            self.progress_signal.emit(
                                0,
                                "Warning: Neither Anthropic nor Gemini thinking capabilities available, using standard API call",
                            )
                            # Use standard API call as fallback
                            response = self.llm_client.generate_response(
                                prompt_text=meta_prompt,
                                system_prompt=f"You are analyzing a large document for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}",
                                temperature=0.1,
                            )

                            if not response["success"]:
                                raise Exception(
                                    f"Failed to combine chunks: {response.get('error', 'Unknown error')}"
                                )

                            final_content = response["content"]
                    else:
                        # Use extended thinking functionality
                        self.progress_signal.emit(
                            0,
                            "Using Anthropic's extended thinking capability to create integrated analysis...",
                        )

                        thinking_response = self.llm_client.generate_response_with_extended_thinking(
                            prompt_text=meta_prompt,
                            system_prompt=f"You are analyzing a large document for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}",
                            temperature=0.1,  # Lower temperature for more factual responses
                            thinking_budget_tokens=16000,  # Allocate sufficient tokens for thinking
                        )

                        if not thinking_response["success"]:
                            raise Exception(
                                f"Failed to combine chunks with extended thinking: {thinking_response.get('error', 'Unknown error')}"
                            )

                        # Log thinking process if available
                        if thinking_response.get("thinking"):
                            self.progress_signal.emit(
                                0,
                                f"Claude performed {len(thinking_response['thinking'])} characters of thinking",
                            )

                            # Save thinking to a separate file for reference
                            thinking_file = os.path.join(
                                os.path.dirname(summary_file),
                                f"{os.path.basename(summary_file).replace('.md', '')}_thinking.md",
                            )
                            with open(thinking_file, "w", encoding="utf-8") as f:
                                f.write(
                                    f"# Analysis Thinking Process for {document_name}\n\n"
                                )
                                f.write(thinking_response["thinking"])

                            self.progress_signal.emit(
                                0, f"Saved thinking process to {thinking_file}"
                            )

                        final_content = thinking_response["content"]

                    self.progress_signal.emit(
                        0,
                        f"Successfully generated integrated summary from {len(chunks)} chunks",
                    )

                except Exception as e:
                    self.progress_signal.emit(0, f"Error in chunk processing: {str(e)}")
                    raise Exception(f"Error in chunk processing: {str(e)}")
            else:
                # Document is small enough for a single chunk
                self.progress_signal.emit(
                    0,
                    f"Document {document_name} is of manageable size. Processing as a single unit.",
                )

                try:
                    # Create the prompt
                    self.progress_signal.emit(0, f"Creating prompt for document")
                    prompt = self.create_summary_prompt(document_name, markdown_content)
                    self.progress_signal.emit(
                        0, f"Created prompt: {len(prompt)} characters"
                    )

                    # Process the API request with detailed logging
                    system_prompt = f"You are analyzing documents for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}"

                    # Log API request details
                    self.progress_signal.emit(0, f"Sending request to LLM API")
                    self.progress_signal.emit(
                        0, f"System prompt length: {len(system_prompt)}"
                    )
                    self.progress_signal.emit(0, f"Prompt length: {len(prompt)}")

                    # Check if API client is initialized
                    if not self.llm_client:
                        self.progress_signal.emit(
                            0, "LLM client not initialized. Attempting to reinitialize."
                        )
                        self._initialize_llm_client()
                        if not self.llm_client:
                            raise Exception("Failed to initialize LLM client")

                    # Log which API we're using
                    if (
                        hasattr(self.llm_client, "anthropic_initialized")
                        and self.llm_client.anthropic_initialized
                    ):
                        self.progress_signal.emit(0, "Using Anthropic Claude API")
                    elif (
                        hasattr(self.llm_client, "gemini_initialized")
                        and self.llm_client.gemini_initialized
                    ):
                        self.progress_signal.emit(0, "Using Google Gemini API")
                    else:
                        self.progress_signal.emit(0, "Using unknown API provider")

                    # Use the new response processing method with enhanced logging
                    final_content = self.process_api_response(prompt, system_prompt)

                    self.progress_signal.emit(
                        0,
                        f"Successfully generated summary: {len(final_content)} characters",
                    )
                except Exception as e:
                    self.progress_signal.emit(0, f"Error in LLM processing: {str(e)}")
                    raise Exception(f"Error in LLM processing: {str(e)}")

            # Write the summary to a file
            try:
                # First create a temporary file to avoid partial writes
                temp_summary_file = f"{summary_file}.tmp"

                self.progress_signal.emit(0, f"Writing summary to temporary file")
                with open(temp_summary_file, "w", encoding="utf-8") as f:
                    f.write(f"# Summary of {document_name}\n\n")
                    f.write(
                        f"## Document Analysis for {self.subject_name} (DOB: {self.subject_dob})\n\n"
                    )
                    f.write(final_content)

                # Now rename the temporary file to the final file
                self.progress_signal.emit(0, f"Renaming temporary file to final file")
                # On Windows, we might need to remove the target file first
                if os.path.exists(summary_file):
                    os.remove(summary_file)
                os.rename(temp_summary_file, summary_file)

                self.progress_signal.emit(
                    0, f"Successfully wrote summary to {summary_file}"
                )
            except PermissionError:
                raise Exception(
                    f"Permission denied when writing summary file: {summary_file}"
                )
            except IOError as e:
                raise Exception(f"I/O error writing summary file: {str(e)}")
            except Exception as e:
                self.progress_signal.emit(0, f"Error writing summary file: {str(e)}")
                raise Exception(f"Error writing summary file: {str(e)}")

            return summary_file

        except Exception as e:
            # Add full traceback for debugging
            import traceback

            error_details = traceback.format_exc()
            self.progress_signal.emit(
                0, f"Error in summarize_markdown_file: {str(e)}\n{error_details}"
            )
            raise Exception(
                f"Failed to summarize {os.path.basename(markdown_path)}: {str(e)}"
            )
