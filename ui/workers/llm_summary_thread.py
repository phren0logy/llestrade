"""
Worker thread for summarizing markdown files with Claude.
"""

import os

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
            token_count_result = client.count_tokens(
                messages=[{"role": "user", "content": current_text}]
            )

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
                overlap_token_result = client.count_tokens(
                    messages=[{"role": "user", "content": overlap_text}]
                )

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
                        test_result = client.count_tokens(
                            messages=[{"role": "user", "content": test_text}]
                        )

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
        self.llm_client = LLMClient()

    def run(self):
        """Run the LLM summarization operations."""
        try:
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
                    summary_path = self.summarize_markdown_file(
                        markdown_path, summary_file
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
                    results["failed"] += 1
                    results["files"].append(
                        {
                            "file": markdown_path,
                            "markdown": markdown_path,
                            "status": "failed",
                            "error": str(e),
                        }
                    )

            # Signal completion with results
            self.finished_signal.emit(results)

        except Exception as e:
            self.error_signal.emit(f"Error during LLM summarization: {str(e)}")

    def summarize_markdown_file(self, markdown_path, summary_file):
        """
        Summarize a markdown file using the LLM, with chunking for large files.

        Args:
            markdown_path: Path to the markdown file
            summary_file: Path to save the summary

        Returns:
            Path to the summary file
        """
        # Read the markdown content
        with open(markdown_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()

        document_name = os.path.basename(markdown_path)

        # Check if summary file already exists
        if os.path.exists(summary_file):
            self.progress_signal.emit(
                0, f"Summary file for {document_name} already exists, skipping."
            )
            return summary_file

        # Check if file is large enough to need chunking
        token_count = self.llm_client.count_tokens(
            messages=[{"role": "user", "content": markdown_content}]
        )

        if token_count["success"] and token_count["token_count"] > 30000:
            # Document is large, use chunking with specified parameters (60000 tokens, 1000 overlap)
            self.progress_signal.emit(
                0,
                f"Document {document_name} is large. Chunking with 60000 token size and 1000 token overlap.",
            )

            # Create combined summaries filename
            combined_summaries_file = os.path.join(
                os.path.dirname(summary_file),
                f"{os.path.splitext(os.path.basename(summary_file))[0]}_combined_chunks.md",
            )

            # Check if combined summaries file exists
            if os.path.exists(combined_summaries_file):
                self.progress_signal.emit(
                    0, f"Using existing combined chunk summaries for {document_name}"
                )
                with open(combined_summaries_file, "r", encoding="utf-8") as f:
                    combined_summaries = f.read()

                # Check the token size of the combined summaries
                token_count_result = self.llm_client.count_tokens(
                    messages=[{"role": "user", "content": combined_summaries}]
                )

                if not token_count_result["success"]:
                    raise Exception(
                        f"Failed to count tokens in combined summaries file: {token_count_result.get('error', 'Unknown error')}"
                    )

                token_count = token_count_result["token_count"]
                self.progress_signal.emit(
                    0, f"Combined summaries token count: {token_count}"
                )

                # Check if token count is within limits for meta-summary
                if token_count > 120000:
                    warning_message = f"Combined summaries file is too large ({token_count} tokens > 120,000 tokens). Skipping meta-summary generation."
                    self.progress_signal.emit(0, warning_message)

                    # Return the combined summaries file instead of creating a meta-summary
                    with open(summary_file, "w", encoding="utf-8") as f:
                        f.write(f"# Summary of {document_name} (No Meta-Summary)\n\n")
                        f.write(
                            f"## Document Analysis for {self.subject_name} (DOB: {self.subject_dob})\n\n"
                        )
                        f.write(
                            f"**Note:** This document is too large for meta-summary generation. Using the raw combined chunk summaries instead.\n\n"
                        )
                        f.write(combined_summaries)

                    return summary_file

                # Proceed with meta-summary generation
                chunks_count = combined_summaries.count("## Chunk")
                self.progress_signal.emit(
                    0,
                    f"Creating meta-summary from existing {chunks_count} chunk summaries for {document_name}",
                )

                meta_prompt = f"""
                I've analyzed {document_name} in multiple chunks. Below are the summaries for each chunk.
                Please create a unified, coherent summary that integrates all information without redundancy.
                Ensure the final summary follows the original instructions for document analysis, including
                the timeline in a markdown table format.
                
                {combined_summaries}
                """

                meta_response = self.llm_client.generate_response(
                    prompt_text=meta_prompt,
                    system_prompt=f"You are creating a unified summary for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}",
                    temperature=0.1,
                )

                if not meta_response["success"]:
                    raise Exception(
                        f"Meta-summary failed: {meta_response.get('error', 'Unknown error')}"
                    )

                final_content = meta_response["content"]
            else:
                # Proceed with normal chunking and individual summarization
                chunks = chunk_document_with_overlap(
                    markdown_content, self.llm_client, 60000, 1000
                )
                summaries = []

                self.progress_signal.emit(
                    0, f"Document {document_name} split into {len(chunks)} chunks."
                )

                for i, chunk in enumerate(chunks):
                    # Update progress
                    self.progress_signal.emit(
                        0, f"Processing chunk {i+1}/{len(chunks)} of {document_name}"
                    )

                    # Create prompt for this chunk
                    chunk_prompt = self.create_summary_prompt(
                        f"{document_name} (part {i+1}/{len(chunks)})", chunk
                    )

                    # Process with LLM
                    response = self.llm_client.generate_response(
                        prompt_text=chunk_prompt,
                        system_prompt=f"You are analyzing part {i+1}/{len(chunks)} of a document for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}",
                        temperature=0.1,
                    )

                    if not response["success"]:
                        raise Exception(
                            f"LLM processing failed on chunk {i+1}: {response.get('error', 'Unknown error')}"
                        )

                    summaries.append(response["content"])

                # If multiple chunks, generate a meta-summary
                if len(summaries) > 1:
                    self.progress_signal.emit(
                        0,
                        f"Creating meta-summary from {len(summaries)} chunk summaries for {document_name}",
                    )

                    combined_summaries = "\n\n".join(
                        [
                            f"## Chunk {i+1}/{len(chunks)} Summary\n{summary}"
                            for i, summary in enumerate(summaries)
                        ]
                    )

                    # Check the token size of the combined summaries
                    token_count_result = self.llm_client.count_tokens(
                        messages=[{"role": "user", "content": combined_summaries}]
                    )

                    if not token_count_result["success"]:
                        raise Exception(
                            f"Failed to count tokens in combined summaries: {token_count_result.get('error', 'Unknown error')}"
                        )

                    token_count = token_count_result["token_count"]
                    self.progress_signal.emit(
                        0, f"Combined summaries token count: {token_count}"
                    )

                    # Save combined summaries to file (regardless of size)
                    self.progress_signal.emit(
                        0, f"Saving combined chunk summaries for {document_name}"
                    )
                    with open(combined_summaries_file, "w", encoding="utf-8") as f:
                        f.write(f"# Combined Chunk Summaries for {document_name}\n\n")
                        f.write(combined_summaries)

                    # Check if token count is within limits for meta-summary
                    if token_count > 120000:
                        warning_message = f"Combined summaries is too large ({token_count} tokens > 120,000 tokens). Skipping meta-summary generation."
                        self.progress_signal.emit(0, warning_message)

                        # Return the combined summaries as the summary instead of creating a meta-summary
                        with open(summary_file, "w", encoding="utf-8") as f:
                            f.write(
                                f"# Summary of {document_name} (No Meta-Summary)\n\n"
                            )
                            f.write(
                                f"## Document Analysis for {self.subject_name} (DOB: {self.subject_dob})\n\n"
                            )
                            f.write(
                                f"**Note:** This document is too large for meta-summary generation. Using the raw combined chunk summaries instead.\n\n"
                            )
                            f.write(combined_summaries)

                        return summary_file
                    else:
                        # Proceed with meta-summary generation
                        meta_prompt = f"""
                        I've analyzed {document_name} in {len(chunks)} chunks. Below are the summaries for each chunk.
                        Please create a unified, coherent summary that integrates all information without redundancy.
                        Ensure the final summary follows the original instructions for document analysis, including
                        the timeline in a markdown table format.
                        
                        {combined_summaries}
                        """

                        meta_response = self.llm_client.generate_response(
                            prompt_text=meta_prompt,
                            system_prompt=f"You are creating a unified summary for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}",
                            temperature=0.1,
                        )

                        if not meta_response["success"]:
                            raise Exception(
                                f"Meta-summary failed: {meta_response.get('error', 'Unknown error')}"
                            )

                        final_content = meta_response["content"]
                else:
                    final_content = summaries[0]
        else:
            # Document is small enough for a single chunk
            self.progress_signal.emit(
                0,
                f"Document {document_name} is of manageable size. Processing as a single unit.",
            )

            prompt = self.create_summary_prompt(document_name, markdown_content)
            response = self.llm_client.generate_response(
                prompt_text=prompt,
                system_prompt=f"You are analyzing documents for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}",
                temperature=0.1,
            )

            if not response["success"]:
                raise Exception(
                    f"LLM processing failed: {response.get('error', 'Unknown error')}"
                )

            final_content = response["content"]

        # Write the summary to a file
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(f"# Summary of {document_name}\n\n")
            f.write(
                f"## Document Analysis for {self.subject_name} (DOB: {self.subject_dob})\n\n"
            )
            f.write(final_content)

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

## Timeline Instructions
- Create a timeline of events in a markdown table format with columns for Date, Event, and Significance
- Using the subject's date of birth ({self.subject_dob}), calculate the subject's age at each event when relevant
- When exact dates aren't provided, estimate years when possible and mark them with "(est.)"
- Organize the timeline chronologically with the most recent events at the bottom
- If there are multiple events on the same date, list them in the order they occurred
- If there are multiple events with the same date and significance, list them in the order they occurred

Keep your analysis focused on factual information directly stated in the document.
"""
