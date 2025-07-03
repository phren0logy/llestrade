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

from src.config.app_config import get_configured_llm_provider
from src.common.llm.factory import create_provider
from src.common.llm.tokens import count_tokens_cached, TokenCounter
from src.common.llm.chunking import ChunkingStrategy
from src.core.prompt_manager import PromptManager
from .base_worker_thread import BaseWorkerThread

# Memory debugging imports
try:
    import psutil
    import tracemalloc
    MEMORY_DEBUG = True
except ImportError:
    MEMORY_DEBUG = False
    psutil = None
    tracemalloc = None

# Set up logger for this module
logger = logging.getLogger(__name__)




from pathlib import Path


class LLMSummaryThread(BaseWorkerThread):
    """Worker thread for summarizing markdown files with LLM providers."""

    # Additional signals specific to this worker
    file_progress = Signal(int, str)
    file_finished = Signal(dict)
    file_error = Signal(str)
    finished_signal = Signal(dict)

    def __init__(
        self, 
        parent,
        markdown_files, 
        output_dir, 
        subject_name, 
        subject_dob, 
        case_info,
        llm_provider_id,
        llm_model_name
    ):
        """Initialize the thread with the markdown files to summarize."""
        super().__init__(parent, operation_name="LLMSummary")
        self.markdown_files = markdown_files
        self.output_dir = output_dir
        self.subject_name = subject_name
        self.subject_dob = subject_dob
        self.case_info = case_info
        self.llm_provider_id = llm_provider_id
        self.llm_model_name = llm_model_name
        self.llm_provider = None

    def _safe_emit_progress(self, percent, message):
        """Safely emit progress signal with memory management."""
        # Use base class method
        self.emit_progress(percent, message)

    def _safe_emit_file_progress(self, percent, message):
        """Safely emit file progress signal with memory management."""
        self.safe_emit(self.file_progress, int(percent), str(message))

    def _safe_emit_finished(self, results):
        """Safely emit finished signal with memory management."""
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
        self.safe_emit(self.finished_signal, results_copy)

    def _safe_emit_error(self, error_message):
        """Safely emit error signal with memory management."""
        self.safe_emit(self.error_signal, str(error_message))
    
    def _safe_emit_status(self, message: str, message_type: str = "info"):
        """Safely emit status updates via signal instead of direct UI access."""
        self.status_signal.emit({
            "type": message_type,
            "message": message
        })

    def cancel(self):
        """Cancel the operation safely."""
        # Call base class cancel method
        super().cancel()
        if self.isRunning():
            self.terminate()
            self.wait(3000)  # Wait up to 3 seconds for clean termination

    def cleanup(self):
        """Clean up resources to prevent memory leaks."""
        try:
            self.cancel()
            
            # Safely clean up LLM provider
            if hasattr(self, 'llm_provider') and self.llm_provider is not None:
                # Disconnect any signals if connected
                try:
                    if hasattr(self.llm_provider, 'deleteLater'):
                        self.llm_provider.deleteLater()
                except Exception:
                    pass
                self.llm_provider = None
            
            # Clear any cached data
            self.markdown_files = []
            self.output_dir = None
            
            # Force garbage collection
            gc.collect()
            
            # Call base class cleanup
            super().cleanup()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

    def _initialize_llm_provider(self):
        """Initialize the LLM provider for summarization."""
        try:
            self.logger.info(f"🔧 Starting LLM provider initialization...")
            self.logger.info(f"🏷️ Provider ID: {self.llm_provider_id}")
            self.logger.info(f"🏷️ Model Name: {self.llm_model_name}")
            
            # Use signal instead of direct UI access
            self._safe_emit_status(f"Initializing LLM provider: {self.llm_provider_id}/{self.llm_model_name}")
            
            self.logger.info("📞 Calling get_configured_llm_provider...")
            provider_info = get_configured_llm_provider(
                provider_id_override=self.llm_provider_id,
                model_override=self.llm_model_name
            )
            self.logger.info(f"✅ get_configured_llm_provider returned: {type(provider_info)}")
            
            if provider_info:
                self.logger.info(f"📋 Provider info keys: {list(provider_info.keys()) if isinstance(provider_info, dict) else 'Not a dict'}")
                if provider_info.get("provider"):
                    self.llm_provider = provider_info["provider"]
                    self.logger.info(f"✅ LLM provider extracted: {type(self.llm_provider)}")
                    self.logger.info(f"🔍 Provider class: {self.llm_provider.__class__.__name__}")
                    self.logger.info(f"🔍 Provider initialized: {getattr(self.llm_provider, 'initialized', 'Unknown')}")
                else:
                    self.logger.error("❌ No 'provider' key in provider_info")
                    self.llm_provider = None
            else:
                self.logger.error("❌ get_configured_llm_provider returned None/empty")
                self.llm_provider = None
            
            if self.llm_provider and self.llm_provider.initialized:
                self.logger.info(f"🎉 LLM provider initialization successful!")
                # Use signal instead of direct UI access
                self._safe_emit_status(f"LLM provider initialized successfully: {self.llm_provider_id}", "info")
                return True
            else:
                error_msg = f"Failed to get configured LLM provider for Provider: {self.llm_provider_id}, Model: {self.llm_model_name}. Review app_config logs and settings."
                self.logger.error(f"❌ {error_msg}")
                # Use signal instead of direct UI access
                self._safe_emit_status(f"❌ ERROR: {error_msg}", "error")
                logging.error(error_msg)
                self._safe_emit_error(error_msg)
                return False

        except Exception as e:
            error_msg = f"Exception initializing LLM provider ({self.llm_provider_id}/{self.llm_model_name}): {str(e)}"
            logger.exception(f"💥 {error_msg}")
            # Use signal instead of direct UI access
            self._safe_emit_status(f"❌ ERROR: {error_msg}", "error")
            logging.exception(error_msg)
            self._safe_emit_error(error_msg)
            return False

    def run(self):
        """Run the LLM summarization operations."""
        # Call base class run() first
        super().run()
        
        self.logger.info("🚀 LLMSummaryThread.run() started")
        self.logger.info(f"📁 Files to process: {len(self.markdown_files)}")
        self.logger.info(f"📂 Output directory: {self.output_dir}")
        self.logger.info(f"👤 Subject: {self.subject_name}")
        self.logger.info(f"🏗️ LLM Provider: {self.llm_provider_id}, Model: {self.llm_model_name}")
        
        # Log all input files
        for i, file_path in enumerate(self.markdown_files):
            self.logger.info(f"📄 File {i+1}: {file_path}")
            if not os.path.exists(file_path):
                self.logger.error(f"❌ File does not exist: {file_path}")
            else:
                file_size = os.path.getsize(file_path)
                self.logger.info(f"📊 File {i+1} size: {file_size} bytes")
        
        self.logger.info("🔧 Initializing LLM provider...")
        if not self._initialize_llm_provider():
            self.logger.error("❌ LLM provider initialization failed")
            self._safe_emit_finished({
                "total": len(self.markdown_files),
                "processed": 0,
                "skipped": 0,
                "failed": len(self.markdown_files),
                "files": [],
                "status": "error",
                "message": "LLM provider initialization failed. No files processed."
            })
            return
        self.logger.info("✅ LLM provider initialization successful")

        try:
            self.logger.info("🔍 Checking LLM provider availability...")
            if not self.llm_provider or not self.llm_provider.initialized:
                self.logger.error(f"❌ LLM provider not available - provider: {self.llm_provider}, initialized: {self.llm_provider.initialized if self.llm_provider else 'N/A'}")
                for markdown_path in self.markdown_files:
                    self.file_error.emit(f"LLM provider not available for {os.path.basename(markdown_path)}.")
                self._safe_emit_finished({
                    "total": len(self.markdown_files),
                    "processed": 0,
                    "skipped": 0,
                    "failed": len(self.markdown_files),
                    "files": [],
                    "status": "error",
                    "message": "LLM provider became unavailable. No files processed."
                })    
                return
            
            self.logger.info(f"✅ LLM provider available - Provider: {self.llm_provider.__class__.__name__}")
            self.logger.info("📡 Emitting initial progress signal...")
            self._safe_emit_progress(
                0, f"Starting LLM summarization for {len(self.markdown_files)} files"
            )
            self.logger.info("✅ Initial progress signal emitted")

            results = {
                "total": len(self.markdown_files),
                "processed": 0,
                "skipped": 0,
                "failed": 0,
                "files": [],
            }

            self.logger.info(f"🔄 Starting file processing loop for {len(self.markdown_files)} files")
            for i, markdown_path in enumerate(self.markdown_files):
                try:
                    current_file_basename = os.path.basename(markdown_path)
                    self.logger.info(f"📋 Processing file {i+1}/{len(self.markdown_files)}: {current_file_basename}")
                    file_progress_msg = f"Processing file {i+1} of {len(self.markdown_files)}: {current_file_basename}"
                    
                    self.logger.info("📡 Emitting file progress signal (0%)...")
                    self._safe_emit_file_progress(0, f"Starting: {file_progress_msg}")
                    self.logger.info("✅ File progress signal emitted")

                    basename = os.path.splitext(os.path.basename(markdown_path))[0]
                    summary_file = os.path.join(
                        self.output_dir, f"{basename}_summary.md"
                    )
                    self.logger.info(f"📝 Target summary file: {summary_file}")

                    # Check if file already exists and handle properly
                    self.logger.info(f"🔍 Checking if summary file exists: {summary_file}")
                    if os.path.exists(summary_file):
                        self.logger.info(f"⏭️ Skipping {current_file_basename} - summary already exists")
                        self._safe_emit_file_progress(100, f"Skipped: {current_file_basename} (already exists)")
                        results["skipped"] += 1
                        results["files"].append({
                            "path": markdown_path,
                            "summary_path": summary_file,
                            "status": "skipped",
                            "message": "Summary file already exists"
                        })
                        self.file_finished.emit(results["files"][-1])
                        # Use signal instead of direct UI access
                        self._safe_emit_status(f"✓ SKIPPED: {current_file_basename} - already processed")
                        continue

                    self.logger.info(f"📖 Reading file contents: {markdown_path}")
                    self._safe_emit_file_progress(10, f"Reading: {current_file_basename}")
                    with open(markdown_path, "r", encoding="utf-8") as f:
                        markdown_content = f.read()
                    self.logger.info(f"✅ File read successfully - {len(markdown_content)} characters")
                    self._safe_emit_file_progress(
                        20, f"Successfully read file contents: {len(markdown_content)} bytes"
                    )

                    self.logger.info(f"🤖 Starting summarization with {self.llm_provider.__class__.__name__}")
                    self._safe_emit_file_progress(30, f"Summarizing: {current_file_basename} with {self.llm_provider.__class__.__name__}")
                    
                    self.logger.info("🔄 Calling summarize_markdown_file...")
                    summary_content = self.summarize_markdown_file(
                        markdown_path, summary_file, markdown_content
                    )
                    self.logger.info(f"✅ Summarization completed - Content length: {len(summary_content) if summary_content else 0}")
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
                        # Use signal instead of direct UI access
                        self._safe_emit_status(f"✓ SUCCESS: {current_file_basename} - summary created ({len(summary_content)} chars)")
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
                        self._safe_emit_status(f"❌ FAILED: {current_file_basename} - {error_msg}", "error")
                        self.file_error.emit(f"Summarization failed for {current_file_basename}: {error_msg}")

                except Exception as e:
                    error_message = f"Error summarizing {os.path.basename(markdown_path)}: {str(e)}"
                    logging.exception(error_message)
                    # Use signal instead of direct UI access
                    self._safe_emit_status(f"❌ ERROR: {os.path.basename(markdown_path)} - {str(e)}", "error")
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
            self.handle_error(e, {"stage": "main_run", "files_count": len(self.markdown_files)})
            self._safe_emit_status(f"❌ ERROR: {run_error_msg}", "error")
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
            self._safe_emit_status(f"❌ ERROR: {error_msg}", "error")
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
            self._safe_emit_status(f"❌ ERROR: {error_msg}", "error")
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
            self._safe_emit_status(f"❌ ERROR: {error_msg}", "error")
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
            self.logger.info("🔄 Starting process_api_response...")
            
            # First check if the LLM provider is properly initialized
            if not self.llm_provider:
                raise Exception("LLM provider not initialized")

            if not self.llm_provider.initialized:
                raise Exception("LLM provider not properly initialized")

            # Log request details
            provider_name = self.llm_provider.__class__.__name__
            self.logger.info(f"📡 Making API request to provider: {provider_name}")
            self.logger.info(f"📏 Prompt length: {len(prompt)} characters")
            self.logger.info(f"📏 System prompt length: {len(system_prompt)} characters")
            
            # Log memory usage before API call if debugging
            if MEMORY_DEBUG and psutil:
                process = psutil.Process()
                mem_info = process.memory_info()
                self.logger.info(f"📊 Memory before API call - RSS: {mem_info.rss / 1024 / 1024:.1f} MB, VMS: {mem_info.vms / 1024 / 1024:.1f} MB")
            
            # Generate the response using the configured provider
            self.logger.info("🚀 Calling llm_provider.generate...")
            
            # Track the start time for timeout monitoring
            api_start_time = time.time()
            
            # Emit progress updates during long API calls
            # Use signal instead of direct UI access
            self._safe_emit_status(f"📡 Making API request to {provider_name}...")
            
            response = self.llm_provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                model=self.llm_model_name,  # Add model parameter for Azure OpenAI
            )
            
            # Calculate API call duration
            api_duration = time.time() - api_start_time
            self.logger.info(f"✅ API response received after {api_duration:.1f} seconds")
            
            # Log memory usage if debugging
            if MEMORY_DEBUG and psutil:
                process = psutil.Process()
                mem_info = process.memory_info()
                self.logger.info(f"📊 Memory after API call - RSS: {mem_info.rss / 1024 / 1024:.1f} MB, VMS: {mem_info.vms / 1024 / 1024:.1f} MB")
            
            self._safe_emit_status(f"✅ API response received ({api_duration:.1f}s)")

            # Check response
            if not response.get("success"):
                error_msg = response.get("error", "Unknown error")
                self.logger.error(f"❌ API response indicates failure: {error_msg}")
                
                # Check for specific error types that should trigger retry
                if any(keyword in error_msg.lower() for keyword in 
                       ["rate limit", "timeout", "connection", "429", "502", "503", "504"]):
                    raise ConnectionError(f"Retryable API error: {error_msg}")
                else:
                    raise Exception(f"Non-retryable API error: {error_msg}")

            # Check if the response is empty
            content = response.get("content", "").strip()
            if not content:
                self.logger.error("❌ LLM returned empty response")
                raise Exception("LLM returned empty response")

            self.logger.info(f"✅ API response successful - Content length: {len(content)} characters")
            
            # Return content directly
            return content

        except Exception as e:
            # Log the error but let tenacity handle retries
            self.logger.error(f"❌ Error in process_api_response: {str(e)}")
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in 
                   ["rate limit", "timeout", "connection", "429", "502", "503", "504"]):
                # This is a retryable error - tenacity will handle it
                self.logger.info("🔄 Retryable error detected, tenacity will retry...")
                raise ConnectionError(str(e))
            else:
                # This is a non-retryable error
                self.logger.error("🚫 Non-retryable error detected, failing immediately")
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
                self.logger.info(f"📏 Estimated tokens (character-based): {estimated_tokens}")

                # Only count tokens with API if the document might be near our chunking threshold
                if estimated_tokens > 25000:  # Lower threshold for safety
                    self.logger.info("🔢 Document large enough for API token counting...")
                    token_count_result = count_tokens_cached(self.llm_provider, text=markdown_content)
                    if not token_count_result["success"]:
                        self.logger.warning("⚠️ API token counting failed, using character-based estimation")
                        # Use character-based estimation as fallback
                        token_count = {"success": True, "token_count": estimated_tokens}
                    else:
                        self.logger.info(f"✅ API token count successful: {token_count_result['token_count']} tokens")
                        token_count = token_count_result
                else:
                    # Small document, use estimation
                    self.logger.info("📄 Small document, using character-based estimation")
                    token_count = {"success": True, "token_count": estimated_tokens}
            except Exception as e:
                self.logger.error(f"❌ Error in token counting: {str(e)}")
                # Use character-based estimation as fallback
                estimated_tokens = len(markdown_content) // 4
                token_count = {"success": True, "token_count": estimated_tokens}

            # Process based on document size
            if token_count["success"] and token_count["token_count"] > 30000:
                # Document is large, use chunking
                self.logger.info(f"📊 Document requires chunking - Token count: {token_count['token_count']}")
                try:
                    self.logger.info("✂️ Starting document chunking...")
                    # Use markdown-aware chunking
                    # Get model context window to determine chunk size
                    context_window = TokenCounter.get_model_context_window(self.llm_model_name)
                    # Use a conservative chunk size (leave room for prompts)
                    max_tokens_per_chunk = int(context_window * 0.5)
                    
                    chunks = ChunkingStrategy.markdown_headers(
                        text=markdown_content,
                        max_tokens=max_tokens_per_chunk,
                        overlap=2000 * 4  # Convert overlap tokens to characters (approx)
                    )
                    self.logger.info(f"✅ Document split into {len(chunks)} chunks")
                    
                    # Estimate processing time (2-3 minutes per chunk is typical)
                    estimated_minutes = len(chunks) * 2.5
                    self.logger.info(f"⏱️ Estimated processing time: {estimated_minutes:.1f} minutes for {len(chunks)} chunks")
                    
                    self._safe_emit_status(f"📊 Document split into {len(chunks)} chunks (est. {estimated_minutes:.1f} min)")
                    
                    # Log chunk sizes for debugging
                    for i, chunk in enumerate(chunks):
                        self.logger.info(f"📋 Chunk {i+1}/{len(chunks)}: {len(chunk)} characters")

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
                        self.logger.info(f"🔄 Processing {len(chunks)} chunks separately...")
                        chunk_start_time = time.time()
                        
                        for i, chunk in enumerate(chunks):
                            self.logger.info(f"🎯 Starting processing of chunk {i+1}/{len(chunks)}")
                            
                            # Update progress for this chunk
                            chunk_progress = int((i / len(chunks)) * 50) + 30  # 30-80% for chunk processing
                            self._safe_emit_file_progress(chunk_progress, f"Processing chunk {i+1}/{len(chunks)}")
                            
                            self._safe_emit_status(f"🔍 Processing chunk {i+1} of {len(chunks)} chunks")
                            
                            chunk_prompt = self.create_summary_prompt(
                                f"{document_name} (chunk {i+1}/{len(chunks)})", chunk
                            )
                            self.logger.info(f"📝 Created prompt for chunk {i+1}/{len(chunks)} - Prompt length: {len(chunk_prompt)}")

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

                            self.logger.info(f"🚀 Processing chunk {i+1}/{len(chunks)} with API...")
                            chunk_content = self.process_api_response(chunk_prompt, chunk_system_prompt)
                            self.logger.info(f"✅ Chunk {i+1}/{len(chunks)} processed successfully - Content length: {len(chunk_content)}")
                            
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
                        self.logger.info(f"🔗 Combining {len(chunk_summaries)} chunk summaries...")
                        combined_chunks = "\n\n".join(chunk_summaries)
                        self.logger.info(f"📄 Combined chunks length: {len(combined_chunks)} characters")

                        # Create a meta-summary prompt
                        self.logger.info("🎯 Creating meta-analysis prompt for combined chunks...")
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
                        
                        self.logger.info("🚀 Starting meta-analysis API call...")
                        final_content = self.process_api_response(meta_prompt, meta_system_prompt)
                        self.logger.info(f"✅ Meta-analysis completed - Final content length: {len(final_content)}")

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

                    # Check if API provider is initialized
                    if not self.llm_provider:
                        self._initialize_llm_provider()
                        if not self.llm_provider:
                            raise Exception("Failed to initialize LLM provider")

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