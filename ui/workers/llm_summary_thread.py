"""
Worker thread for summarizing markdown files with Claude.
"""

import gc  # Add garbage collection
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QMutex, QThread, QTimer, Signal
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app_config import get_configured_llm_client
from llm_utils import LLMClientFactory, cached_count_tokens, chunk_document_with_overlap
from prompt_manager import PromptManager

# Set up logger for this module
logger = logging.getLogger(__name__)




from pathlib import Path


class LLMSummaryThread(QThread):
    """Worker thread for summarizing markdown files with Claude."""

    progress_signal = Signal(int, str)
    file_progress = Signal(int, str)
    file_finished = Signal(dict)
    file_error = Signal(str)
    
    finished_signal = Signal(dict)
    error_signal = Signal(str)

    def __init__(
        self, 
        parent,
        markdown_files, 
        output_dir, 
        subject_name, 
        subject_dob, 
        case_info,
        status_panel,
        llm_provider_id,
        llm_model_name
    ):
        """Initialize the thread with the markdown files to summarize."""
        super().__init__(parent)
        self.markdown_files = markdown_files
        self.output_dir = output_dir
        self.subject_name = subject_name
        self.subject_dob = subject_dob
        self.case_info = case_info
        self.status_panel = status_panel
        self.llm_provider_id = llm_provider_id
        self.llm_model_name = llm_model_name
        self.llm_client = None
        self._mutex = QMutex()  # For thread-safe operations
        self._is_cancelled = False

    def _safe_emit_progress(self, percent, message):
        """Safely emit progress signal with memory management."""
        try:
            if not self._is_cancelled:
                # Create copies of the data to avoid memory issues
                percent_copy = int(percent)
                message_copy = str(message)
                self.progress_signal.emit(percent_copy, message_copy)
        except Exception as e:
            logger.error(f"Error emitting progress signal: {e}")

    def _safe_emit_file_progress(self, percent, message):
        """Safely emit file progress signal with memory management."""
        try:
            if not self._is_cancelled:
                # Create copies of the data to avoid memory issues
                percent_copy = int(percent)
                message_copy = str(message)
                self.file_progress.emit(percent_copy, message_copy)
        except Exception as e:
            logger.error(f"Error emitting file progress signal: {e}")

    def _safe_emit_finished(self, results):
        """Safely emit finished signal with memory management."""
        try:
            if not self._is_cancelled:
                # Create a clean copy of results to avoid memory issues
                results_copy = {
                    "total": int(results.get("total", 0)),
                    "processed": int(results.get("processed", 0)),
                    "skipped": int(results.get("skipped", 0)),
                    "failed": int(results.get("failed", 0)),
                    "status": str(results.get("status", "unknown")),
                    "message": str(results.get("message", "")),
                    "files": []  # Simplified - avoid passing large data structures
                }
                self.finished_signal.emit(results_copy)
        except Exception as e:
            logger.error(f"Error emitting finished signal: {e}")

    def _safe_emit_error(self, error_message):
        """Safely emit error signal with memory management."""
        try:
            if not self._is_cancelled:
                error_copy = str(error_message)
                self.error_signal.emit(error_copy)
        except Exception as e:
            logger.error(f"Error emitting error signal: {e}")

    def cancel(self):
        """Cancel the operation safely."""
        self._is_cancelled = True
        if self.isRunning():
            self.terminate()
            self.wait(3000)  # Wait up to 3 seconds for clean termination

    def cleanup(self):
        """Clean up resources to prevent memory leaks."""
        try:
            self.cancel()
            self.llm_client = None
            gc.collect()  # Force garbage collection
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def _initialize_llm_client(self):
        """Initialize the LLM client for summarization."""
        try:
            logger.info(f"🔧 Starting LLM client initialization...")
            logger.info(f"🏷️ Provider ID: {self.llm_provider_id}")
            logger.info(f"🏷️ Model Name: {self.llm_model_name}")
            
            if self.status_panel:
                self.status_panel.append_details(f"Initializing LLM client: {self.llm_provider_id}/{self.llm_model_name}")
            
            logger.info("📞 Calling get_configured_llm_client...")
            client_info = get_configured_llm_client(
                provider_id_override=self.llm_provider_id,
                model_override=self.llm_model_name
            )
            logger.info(f"✅ get_configured_llm_client returned: {type(client_info)}")
            
            if client_info:
                logger.info(f"📋 Client info keys: {list(client_info.keys()) if isinstance(client_info, dict) else 'Not a dict'}")
                if client_info.get("client"):
                    self.llm_client = client_info["client"]
                    logger.info(f"✅ LLM client extracted: {type(self.llm_client)}")
                    logger.info(f"🔍 Client provider: {getattr(self.llm_client, 'provider', 'Unknown')}")
                    logger.info(f"🔍 Client is_initialized: {getattr(self.llm_client, 'is_initialized', 'Unknown')}")
                else:
                    logger.error("❌ No 'client' key in client_info")
                    self.llm_client = None
            else:
                logger.error("❌ get_configured_llm_client returned None/empty")
                self.llm_client = None
            
            if self.llm_client and self.llm_client.is_initialized:
                logger.info(f"🎉 LLM client initialization successful!")
                if self.status_panel:
                    self.status_panel.append_details(f"LLM client initialized successfully: {self.llm_provider_id}")
                return True
            else:
                error_msg = f"Failed to get configured LLM client for Provider: {self.llm_provider_id}, Model: {self.llm_model_name}. Review app_config logs and settings."
                logger.error(f"❌ {error_msg}")
                if self.status_panel:
                    self.status_panel.append_details(f"❌ ERROR: {error_msg}")
                logging.error(error_msg)
                self._safe_emit_error(error_msg)
                return False

        except Exception as e:
            error_msg = f"Exception initializing LLM client ({self.llm_provider_id}/{self.llm_model_name}): {str(e)}"
            logger.exception(f"💥 {error_msg}")
            if self.status_panel:
                self.status_panel.append_details(f"❌ ERROR: {error_msg}")
            logging.exception(error_msg)
            self._safe_emit_error(error_msg)
            return False

    def run(self):
        """Run the LLM summarization operations."""
        logger.info("🚀 LLMSummaryThread.run() started")
        logger.info(f"📁 Files to process: {len(self.markdown_files)}")
        logger.info(f"📂 Output directory: {self.output_dir}")
        logger.info(f"👤 Subject: {self.subject_name}")
        logger.info(f"🏗️ LLM Provider: {self.llm_provider_id}, Model: {self.llm_model_name}")
        
        # Log all input files
        for i, file_path in enumerate(self.markdown_files):
            logger.info(f"📄 File {i+1}: {file_path}")
            if not os.path.exists(file_path):
                logger.error(f"❌ File does not exist: {file_path}")
            else:
                file_size = os.path.getsize(file_path)
                logger.info(f"📊 File {i+1} size: {file_size} bytes")
        
        logger.info("🔧 Initializing LLM client...")
        if not self._initialize_llm_client():
            logger.error("❌ LLM client initialization failed")
            self._safe_emit_finished({
                "total": len(self.markdown_files),
                "processed": 0,
                "skipped": 0,
                "failed": len(self.markdown_files),
                "files": [],
                "status": "error",
                "message": "LLM client initialization failed. No files processed."
            })
            return
        logger.info("✅ LLM client initialization successful")

        try:
            logger.info("🔍 Checking LLM client availability...")
            if not self.llm_client or not self.llm_client.is_initialized:
                logger.error(f"❌ LLM client not available - client: {self.llm_client}, initialized: {self.llm_client.is_initialized if self.llm_client else 'N/A'}")
                for markdown_path in self.markdown_files:
                    self.file_error.emit(f"LLM client not available for {os.path.basename(markdown_path)}.")
                self._safe_emit_finished({
                    "total": len(self.markdown_files),
                    "processed": 0,
                    "skipped": 0,
                    "failed": len(self.markdown_files),
                    "files": [],
                    "status": "error",
                    "message": "LLM client became unavailable. No files processed."
                })    
                return
            
            logger.info(f"✅ LLM client available - Provider: {self.llm_client.provider}")
            logger.info("📡 Emitting initial progress signal...")
            self._safe_emit_progress(
                0, f"Starting LLM summarization for {len(self.markdown_files)} files"
            )
            logger.info("✅ Initial progress signal emitted")

            results = {
                "total": len(self.markdown_files),
                "processed": 0,
                "skipped": 0,
                "failed": 0,
                "files": [],
            }

            logger.info(f"🔄 Starting file processing loop for {len(self.markdown_files)} files")
            for i, markdown_path in enumerate(self.markdown_files):
                try:
                    current_file_basename = os.path.basename(markdown_path)
                    logger.info(f"📋 Processing file {i+1}/{len(self.markdown_files)}: {current_file_basename}")
                    file_progress_msg = f"Processing file {i+1} of {len(self.markdown_files)}: {current_file_basename}"
                    
                    logger.info("📡 Emitting file progress signal (0%)...")
                    self._safe_emit_file_progress(0, f"Starting: {file_progress_msg}")
                    logger.info("✅ File progress signal emitted")

                    basename = os.path.splitext(os.path.basename(markdown_path))[0]
                    summary_file = os.path.join(
                        self.output_dir, f"{basename}_summary.md"
                    )
                    logger.info(f"📝 Target summary file: {summary_file}")

                    # Check if file already exists and handle properly
                    logger.info(f"🔍 Checking if summary file exists: {summary_file}")
                    if os.path.exists(summary_file):
                        logger.info(f"⏭️ Skipping {current_file_basename} - summary already exists")
                        self._safe_emit_file_progress(100, f"Skipped: {current_file_basename} (already exists)")
                        results["skipped"] += 1
                        results["files"].append({
                            "path": markdown_path,
                            "summary_path": summary_file,
                            "status": "skipped",
                            "message": "Summary file already exists"
                        })
                        self.file_finished.emit(results["files"][-1])
                        if self.status_panel:
                            self.status_panel.append_details(f"✓ SKIPPED: {current_file_basename} - already processed")
                        continue

                    logger.info(f"📖 Reading file contents: {markdown_path}")
                    self._safe_emit_file_progress(10, f"Reading: {current_file_basename}")
                    with open(markdown_path, "r", encoding="utf-8") as f:
                        markdown_content = f.read()
                    logger.info(f"✅ File read successfully - {len(markdown_content)} characters")
                    self._safe_emit_file_progress(
                        20, f"Successfully read file contents: {len(markdown_content)} bytes"
                    )

                    logger.info(f"🤖 Starting summarization with {self.llm_client.provider}")
                    self._safe_emit_file_progress(30, f"Summarizing: {current_file_basename} with {self.llm_client.provider}")
                    
                    logger.info("🔄 Calling summarize_markdown_file...")
                    summary_content = self.summarize_markdown_file(
                        markdown_path, summary_file, markdown_content
                    )
                    logger.info(f"✅ Summarization completed - Content length: {len(summary_content) if summary_content else 0}")
                    self._safe_emit_file_progress(80, f"Finalizing: {current_file_basename}")

                    if summary_content and summary_content.strip():
                        # Write the summary file
                        with open(summary_file, "w", encoding="utf-8") as f:
                            f.write(summary_content)
                        
                        results["processed"] += 1
                        results["files"].append({
                            "path": markdown_path,
                            "summary_path": summary_file,
                            "status": "success",
                            "message": f"Successfully summarized {len(summary_content)} characters"
                        })
                        if self.status_panel:
                            self.status_panel.append_details(f"✓ SUCCESS: {current_file_basename} - summary created ({len(summary_content)} chars)")
                        self.file_finished.emit(results["files"][-1])
                    else:
                        results["failed"] += 1
                        error_msg = "Summarization returned no content or failed internally."
                        results["files"].append({
                            "path": markdown_path,
                            "summary_path": summary_file,
                            "status": "failed",
                            "error": error_msg,
                            "message": error_msg
                        })
                        if self.status_panel:
                            self.status_panel.append_details(f"❌ FAILED: {current_file_basename} - {error_msg}")
                        self.file_error.emit(f"Summarization failed for {current_file_basename}: {error_msg}")

                except Exception as e:
                    error_message = f"Error summarizing {os.path.basename(markdown_path)}: {str(e)}"
                    logging.exception(error_message)
                    if self.status_panel:
                        self.status_panel.append_details(f"❌ ERROR: {os.path.basename(markdown_path)} - {str(e)}")
                    results["failed"] += 1
                    results["files"].append({
                        "path": markdown_path,
                        "summary_path": os.path.join(self.output_dir, f"{basename}_summary.md"),
                        "status": "failed",
                        "error": str(e),
                        "message": str(e)
                    })
                    self.file_error.emit(error_message)
                finally:
                    overall_progress_pct = int(((i + 1) / len(self.markdown_files)) * 100)
                    self._safe_emit_progress(overall_progress_pct, f"Processed {i+1}/{len(self.markdown_files)} files")

            results["status"] = "completed" if results["failed"] == 0 else "partial_error"
            self._safe_emit_finished(results)

        except Exception as e:
            run_error_msg = f"Critical error in LLM summary thread: {str(e)}"
            logging.exception(run_error_msg)
            if self.status_panel:
                self.status_panel.append_details(f"❌ ERROR: {run_error_msg}")
            self._safe_emit_error(run_error_msg)
            self._safe_emit_finished({
                "total": len(self.markdown_files),
                "processed": results.get("processed", 0) if 'results' in locals() else 0,
                "skipped": results.get("skipped", 0) if 'results' in locals() else 0,
                "failed": len(self.markdown_files) - (results.get("processed", 0) if 'results' in locals() else 0) - (results.get("skipped", 0) if 'results' in locals() else 0),
                "files": results.get("files", []) if 'results' in locals() else [],
                "status": "error",
                "message": run_error_msg
            })

    def create_summary_prompt(self, document_name, markdown_content):
        """
        Create a prompt for the LLM to summarize a document.

        Args:
            document_name: Name of the document
            markdown_content: Content of the markdown file

        Returns:
            Prompt string
        """
        # Construct the path to the prompt template file
        current_script_path = Path(__file__).resolve()
        project_root = current_script_path.parent.parent.parent
        prompt_template_path = project_root / "prompt_templates" / "document_summary_prompt.md"

        try:
            with open(prompt_template_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()
        except FileNotFoundError:
            error_msg = f"Prompt template file not found at {prompt_template_path}"
            if self.status_panel:
                self.status_panel.append_details(f"❌ ERROR: {error_msg}")
            logging.error(error_msg)
            # Return a basic fallback prompt
            return f"""Please provide a comprehensive summary of the following document for {self.subject_name} (DOB: {self.subject_dob}).

Case Context: {self.case_info}

Document: {document_name}

Content:
{markdown_content}

Please include:
1. Document overview
2. Key facts about the subject
3. Timeline of events
4. Significant findings
"""
        except Exception as e:
            error_msg = f"Error reading prompt template: {str(e)}"
            if self.status_panel:
                self.status_panel.append_details(f"❌ ERROR: {error_msg}")
            logging.error(error_msg)
            # Return a basic fallback prompt
            return f"Summarize this document for {self.subject_name}: {markdown_content}"

        try:
            prompt = prompt_template.format(
                document_content=markdown_content,
                subject_name=self.subject_name,
                subject_dob=self.subject_dob,
                document_name=document_name,
                case_info=self.case_info
            )
            return prompt
        except Exception as e:
            error_msg = f"Error formatting prompt template: {str(e)}"
            if self.status_panel:
                self.status_panel.append_details(f"❌ ERROR: {error_msg}")
            logging.error(error_msg)
            # Return a basic fallback prompt
            return f"Summarize this document for {self.subject_name}: {markdown_content}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, Exception)),
        reraise=True
    )
    def process_api_response(self, prompt, system_prompt):
        """Process API response with tenacity retry handling."""
        try:
            logger.info("🔄 Starting process_api_response...")
            
            # First check if the LLM client is properly initialized
            if not self.llm_client:
                raise Exception("LLM client not initialized")

            if not self.llm_client.is_initialized:
                raise Exception("LLM client not properly initialized")

            # Log request details
            provider = getattr(self.llm_client, "provider", "unknown")
            logger.info(f"📡 Making API request to provider: {provider}")
            logger.info(f"📏 Prompt length: {len(prompt)} characters")
            logger.info(f"📏 System prompt length: {len(system_prompt)} characters")
            
            # Generate the response using the configured client
            logger.info("🚀 Calling llm_client.generate_response...")
            
            # Track the start time for timeout monitoring
            api_start_time = time.time()
            
            # Emit progress updates during long API calls
            if self.status_panel:
                self.status_panel.append_details(f"📡 Making API request to {provider}...")
            
            response = self.llm_client.generate_response(
                prompt_text=prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                model=self.llm_model_name,  # Add model parameter for Azure OpenAI
            )
            
            # Calculate API call duration
            api_duration = time.time() - api_start_time
            logger.info(f"✅ API response received after {api_duration:.1f} seconds")
            
            if self.status_panel:
                self.status_panel.append_details(f"✅ API response received ({api_duration:.1f}s)")

            # Check response
            if not response.get("success"):
                error_msg = response.get("error", "Unknown error")
                logger.error(f"❌ API response indicates failure: {error_msg}")
                
                # Check for specific error types that should trigger retry
                if any(keyword in error_msg.lower() for keyword in 
                       ["rate limit", "timeout", "connection", "429", "502", "503", "504"]):
                    raise ConnectionError(f"Retryable API error: {error_msg}")
                else:
                    raise Exception(f"Non-retryable API error: {error_msg}")

            # Check if the response is empty
            content = response.get("content", "").strip()
            if not content:
                logger.error("❌ LLM returned empty response")
                raise Exception("LLM returned empty response")

            logger.info(f"✅ API response successful - Content length: {len(content)} characters")
            
            # Return content directly without aggressive cleanup
            # The aggressive cleanup might be causing the double free
            return content

        except Exception as e:
            # Log the error but let tenacity handle retries
            logger.error(f"❌ Error in process_api_response: {str(e)}")
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in 
                   ["rate limit", "timeout", "connection", "429", "502", "503", "504"]):
                # This is a retryable error - tenacity will handle it
                logger.info("🔄 Retryable error detected, tenacity will retry...")
                raise ConnectionError(str(e))
            else:
                # This is a non-retryable error
                logger.error("🚫 Non-retryable error detected, failing immediately")
                raise Exception(str(e))

    def summarize_markdown_file(self, markdown_path, summary_file, markdown_content):
        """
        Summarize a markdown file using the LLM, with chunking for large files.

        Args:
            markdown_path: Path to the markdown file
            summary_file: Path to save the summary
            markdown_content: Content of the markdown file

        Returns:
            Summary content string (not filename)
        """
        try:
            # Log beginning of file processing
            document_name = os.path.basename(markdown_path)

            # Verify file exists and is readable
            if not os.path.exists(markdown_path):
                raise Exception(f"File does not exist: {markdown_path}")

            if not os.path.isfile(markdown_path):
                raise Exception(f"Path is not a file: {markdown_path}")

            # Check file size
            try:
                file_stats = os.stat(markdown_path)
                file_size = file_stats.st_size

                if file_size == 0:
                    raise Exception(f"File is empty: {markdown_path}")

                if file_size > 10_000_000:  # 10MB limit
                    raise Exception(f"File is too large ({file_size} bytes): {markdown_path}")
            except Exception as e:
                raise Exception(f"Error accessing file: {str(e)}")

            # Verify output directory is writable
            output_dir = os.path.dirname(summary_file)
            if not os.path.exists(output_dir):
                try:
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

            # IMPORTANT: Don't skip existing files here - let caller handle that
            # This method should always generate new content when called

            # Check if file is large enough to need chunking
            try:
                # Start with character-based estimation to avoid unnecessary API calls
                estimated_tokens = len(markdown_content) // 4  # Reasonable approximation
                logger.info(f"📏 Estimated tokens (character-based): {estimated_tokens}")

                # Only count tokens with API if the document might be near our chunking threshold
                if estimated_tokens > 25000:  # Lower threshold for safety
                    logger.info("🔢 Document large enough for API token counting...")
                    token_count_result = cached_count_tokens(self.llm_client, text=markdown_content)
                    if not token_count_result["success"]:
                        logger.warning("⚠️ API token counting failed, using character-based estimation")
                        # Use character-based estimation as fallback
                        token_count = {"success": True, "token_count": estimated_tokens}
                    else:
                        logger.info(f"✅ API token count successful: {token_count_result['token_count']} tokens")
                        token_count = token_count_result
                else:
                    # Small document, use estimation
                    logger.info("📄 Small document, using character-based estimation")
                    token_count = {"success": True, "token_count": estimated_tokens}
            except Exception as e:
                logger.error(f"❌ Error in token counting: {str(e)}")
                # Use character-based estimation as fallback
                estimated_tokens = len(markdown_content) // 4
                token_count = {"success": True, "token_count": estimated_tokens}

            # Process based on document size
            if token_count["success"] and token_count["token_count"] > 30000:
                # Document is large, use chunking
                logger.info(f"📊 Document requires chunking - Token count: {token_count['token_count']}")
                try:
                    logger.info("✂️ Starting document chunking...")
                    # Use model-aware chunking
                    chunks = chunk_document_with_overlap(
                        markdown_content,
                        client=self.llm_client,
                        model_name=self.llm_model_name,  # Pass model name for dynamic sizing
                        overlap=2000,  # Overlap for better continuity
                    )
                    logger.info(f"✅ Document split into {len(chunks)} chunks")
                    
                    # Estimate processing time (2-3 minutes per chunk is typical)
                    estimated_minutes = len(chunks) * 2.5
                    logger.info(f"⏱️ Estimated processing time: {estimated_minutes:.1f} minutes for {len(chunks)} chunks")
                    
                    if self.status_panel:
                        self.status_panel.append_details(f"📊 Document split into {len(chunks)} chunks (est. {estimated_minutes:.1f} min)")
                    
                    # Log chunk sizes for debugging
                    for i, chunk in enumerate(chunks):
                        logger.info(f"📋 Chunk {i+1}/{len(chunks)}: {len(chunk)} characters")

                    # Process each chunk separately
                    chunk_summaries = []

                    # If we only have one chunk, process as single document
                    if len(chunks) == 1 and len(chunks[0]) >= len(markdown_content) * 0.95:
                        # Single large chunk - process normally
                        prompt = self.create_summary_prompt(document_name, markdown_content)
                        
                        # Get system prompt from template
                        try:
                            app_dir = Path(__file__).parent.parent.parent
                            template_dir = app_dir / 'prompt_templates'
                            prompt_manager = PromptManager(template_dir=template_dir)
                            system_prompt = prompt_manager.get_template(
                                "document_analysis_system_prompt",
                                subject_name=self.subject_name,
                                subject_dob=self.subject_dob,
                                case_info=self.case_info
                            )
                        except Exception as e:
                            logging.error(f"Error loading system prompt template: {e}")
                            system_prompt = f"You are analyzing documents for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}"

                        final_content = self.process_api_response(prompt, system_prompt)
                    else:
                        # Multiple chunks - process each separately then combine
                        logger.info(f"🔄 Processing {len(chunks)} chunks separately...")
                        chunk_start_time = time.time()
                        
                        for i, chunk in enumerate(chunks):
                            logger.info(f"🎯 Starting processing of chunk {i+1}/{len(chunks)}")
                            
                            # Update progress for this chunk
                            chunk_progress = int((i / len(chunks)) * 50) + 30  # 30-80% for chunk processing
                            self._safe_emit_file_progress(chunk_progress, f"Processing chunk {i+1}/{len(chunks)}")
                            
                            if self.status_panel:
                                self.status_panel.append_details(f"🔍 Processing chunk {i+1} of {len(chunks)} chunks")
                            
                            chunk_prompt = self.create_summary_prompt(
                                f"{document_name} (chunk {i+1}/{len(chunks)})", chunk
                            )
                            logger.info(f"📝 Created prompt for chunk {i+1}/{len(chunks)} - Prompt length: {len(chunk_prompt)}")

                            # Get chunk-specific system prompt
                            try:
                                app_dir = Path(__file__).parent.parent.parent
                                template_dir = app_dir / 'prompt_templates'
                                prompt_manager = PromptManager(template_dir=template_dir)
                                chunk_system_prompt = prompt_manager.get_template(
                                    "document_analysis_system_prompt",
                                    subject_name=self.subject_name,
                                    subject_dob=self.subject_dob,
                                    case_info=f"{self.case_info} (Chunk {i+1} of {len(chunks)})"
                                )
                            except Exception as e:
                                logging.error(f"Error loading chunk system prompt template: {e}")
                                chunk_system_prompt = f"You are analyzing chunk {i+1}/{len(chunks)} of a document for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}"

                            logger.info(f"🚀 Processing chunk {i+1}/{len(chunks)} with API...")
                            chunk_content = self.process_api_response(chunk_prompt, chunk_system_prompt)
                            logger.info(f"✅ Chunk {i+1}/{len(chunks)} processed successfully - Content length: {len(chunk_content)}")
                            
                            # Create chunk summary and append to list
                            chunk_summary = f"## Chunk {i+1}/{len(chunks)} Summary\n\n{chunk_content}"
                            chunk_summaries.append(chunk_summary)
                            
                            # Force garbage collection after each chunk to manage memory
                            # Note: We don't use explicit del statements as they can cause
                            # memory corruption with Python's reference counting
                            gc.collect()  # Encourage garbage collection after each chunk
                            
                            # Update progress after chunk completion with time estimate
                            chunk_done_progress = int(((i + 1) / len(chunks)) * 50) + 30
                            
                            # Calculate remaining time estimate
                            if i > 0:  # Only calculate after first chunk
                                elapsed_time = time.time() - chunk_start_time
                                avg_time_per_chunk = elapsed_time / (i + 1)
                                remaining_chunks = len(chunks) - (i + 1)
                                estimated_remaining_minutes = (remaining_chunks * avg_time_per_chunk) / 60
                                
                                progress_msg = f"Completed chunk {i+1}/{len(chunks)} (est. {estimated_remaining_minutes:.1f} min remaining)"
                            else:
                                progress_msg = f"Completed chunk {i+1}/{len(chunks)}"
                            
                            self._safe_emit_file_progress(chunk_done_progress, progress_msg)

                        # Combine all chunk summaries
                        logger.info(f"🔗 Combining {len(chunk_summaries)} chunk summaries...")
                        combined_chunks = "\n\n".join(chunk_summaries)
                        logger.info(f"📄 Combined chunks length: {len(combined_chunks)} characters")

                        # Create a meta-summary prompt
                        logger.info("🎯 Creating meta-analysis prompt for combined chunks...")
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
2. **Citations**: Include the file name and page number where possible for each extracted piece of information
3. **Key Facts**: Extract key facts and information about the subject from across all chunks
4. **Timeline**: Consolidate any timeline information from the chunks into a single, chronological timeline
5. **Major Findings**: Identify significant findings, patterns, or inconsistencies across the document
6. **Integration**: Connect information across chunks, identify overarching themes, and create a cohesive summary

## Chunk Summaries
{combined_chunks}
"""

                        # Get meta system prompt
                        try:
                            app_dir = Path(__file__).parent.parent.parent
                            template_dir = app_dir / 'prompt_templates'
                            prompt_manager = PromptManager(template_dir=template_dir)
                            meta_system_prompt = prompt_manager.get_template(
                                "document_analysis_system_prompt",
                                subject_name=self.subject_name,
                                subject_dob=self.subject_dob,
                                case_info=f"{self.case_info} (Meta-analysis of {len(chunks)} chunks)"
                            )
                        except Exception as e:
                            logging.error(f"Error loading meta system prompt template: {e}")
                            meta_system_prompt = f"You are analyzing a large document for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}"
                        
                        logger.info("🚀 Starting meta-analysis API call...")
                        final_content = self.process_api_response(meta_prompt, meta_system_prompt)
                        logger.info(f"✅ Meta-analysis completed - Final content length: {len(final_content)}")

                except Exception as e:
                    raise Exception(f"Error in chunk processing: {str(e)}")

            else:
                # Document is small enough for a single chunk
                try:
                    # Create the prompt
                    prompt = self.create_summary_prompt(document_name, markdown_content)

                    # Get system prompt from template
                    try:
                        app_dir = Path(__file__).parent.parent.parent
                        template_dir = app_dir / 'prompt_templates'
                        prompt_manager = PromptManager(template_dir=template_dir)
                        system_prompt = prompt_manager.get_template(
                            "document_analysis_system_prompt",
                            subject_name=self.subject_name,
                            subject_dob=self.subject_dob,
                            case_info=self.case_info
                        )
                    except Exception as e:
                        logging.error(f"Error loading system prompt template: {e}")
                        system_prompt = f"You are analyzing documents for {self.subject_name} (DOB: {self.subject_dob}). The following case information provides context: {self.case_info}"

                    # Check if API client is initialized
                    if not self.llm_client:
                        self._initialize_llm_client()
                        if not self.llm_client:
                            raise Exception("Failed to initialize LLM client")

                    # Process with LLM
                    final_content = self.process_api_response(prompt, system_prompt)

                except Exception as e:
                    raise Exception(f"Error in LLM processing: {str(e)}")

            # Create the final formatted content
            formatted_content = f"# Summary of {document_name}\n\n"
            formatted_content += f"## Document Analysis for {self.subject_name} (DOB: {self.subject_dob})\n\n"
            formatted_content += final_content

            return formatted_content

        except Exception as e:
            # Add full traceback for debugging
            import traceback
            error_details = traceback.format_exc()
            logging.error(f"Error in summarize_markdown_file: {str(e)}\n{error_details}")
            raise Exception(f"Failed to summarize {os.path.basename(markdown_path)}: {str(e)}")
