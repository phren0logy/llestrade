"""
Worker thread for generating an integrated analysis with Claude's thinking model.
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import QObject, QThread, Signal

from src.config.app_config import get_configured_llm_provider
from .base_worker_thread import BaseWorkerThread
from PySide6.QtCore import Qt
from src.common.llm.providers import AnthropicProvider, GeminiProvider
from src.common.llm.base import BaseLLMProvider
from src.common.llm.factory import create_provider
from src.common.llm.tokens import count_tokens_cached, TokenCounter
from src.common.llm.chunking import ChunkingStrategy
from src.core.prompt_manager import PromptManager


class IntegratedAnalysisThread(BaseWorkerThread):
    """Worker thread for generating an integrated analysis with LLM providers."""

    # Additional signals specific to this worker
    finished_signal = Signal(bool, str, str)  # success, message, file_path

    def __init__(self, 
                 parent, 
                 combined_summary_path, 
                 original_markdown_files, 
                 output_dir, 
                 subject_name, 
                 subject_dob, 
                 case_info,
                 progress_dialog, # This is QProgressDialog instance
                 llm_provider_id, 
                 llm_model_name):
        """Initialize the thread."""
        super().__init__(parent, operation_name="IntegratedAnalysis")
        self.combined_summary_path = combined_summary_path
        self.original_markdown_files = original_markdown_files
        self.output_dir = output_dir
        self.subject_name = subject_name
        self.subject_dob = subject_dob
        self.case_info = case_info
        self.progress_dialog = progress_dialog # Store the QProgressDialog
        self.llm_provider_id = llm_provider_id
        self.llm_model_name = llm_model_name
        
        self.llm_provider: Optional[BaseLLMProvider] = None
        self.llm_provider_label: Optional[str] = None
        self.llm_effective_model: Optional[str] = None

    def _safe_emit_status(self, message: str, message_type: str = "info"):
        """Safely emit status updates via signal instead of direct UI access."""
        self.status_signal.emit({
            "type": message_type,
            "message": message
        })

    def _initialize_llm_provider(self) -> bool:
        """Initialize LLM provider using specified provider and model."""
        try:
            self.progress_signal.emit(5, f"Initializing LLM: {self.llm_provider_id} ({self.llm_model_name})...")
            self._safe_emit_status(
                f"Attempting to initialize LLM provider for integrated analysis: Provider ID: {self.llm_provider_id}, Model: {self.llm_model_name}"
            )
            
            provider_info = get_configured_llm_provider(
                provider_id_override=self.llm_provider_id,
                model_override=self.llm_model_name
            )

            if provider_info and provider_info.get("provider"):
                self.llm_provider = provider_info["provider"]
                if self.llm_provider.initialized:
                    self.llm_provider_label = provider_info.get("provider_label", self.llm_provider_id)
                    self.llm_effective_model = provider_info.get("effective_model_name", self.llm_model_name)
                    self._safe_emit_status(
                        f"Successfully initialized LLM provider: {self.llm_provider_label} ({self.llm_effective_model}) for integrated analysis."
                    )
                    self.progress_signal.emit(10, f"LLM provider {self.llm_provider_label} initialized.")
                    return True
                else:
                    error_msg = f"LLM provider for {provider_info.get('provider_label', self.llm_provider_id)} could not be initialized (initialized flag is false)."
                    self._safe_emit_status(error_msg, "error")
                    logging.error(error_msg)
                    self.error_signal.emit(error_msg)
                    return False
            else:
                error_msg = f"Failed to get configured LLM provider for Provider: {self.llm_provider_id}, Model: {self.llm_model_name}. Review app_config logs and settings."
                self._safe_emit_status(error_msg, "error")
                logging.error(error_msg)
                self.error_signal.emit(error_msg)
                return False
        except Exception as e:
            error_msg = f"Exception initializing LLM provider ({self.llm_provider_id}/{self.llm_model_name}) for integrated analysis: {str(e)}"
            self._safe_emit_status(error_msg, "error")
            logging.exception(error_msg)
            self.error_signal.emit(error_msg)
            return False

    def process_api_response(self, prompt: str, system_prompt: str) -> Optional[Dict[str, Any]]:
        """Process API response with detailed error handling and retries using the configured LLM provider."""
        max_retries = 3
        retry_count = 0
        retry_delay = 5  # seconds, increased from 2
        timeout_seconds = 900  # 15 minutes timeout for potentially very long analysis

        if not self.llm_provider or not self.llm_provider.initialized:
            err_msg = "LLM provider not initialized. Cannot process API response."
            self._safe_emit_status(err_msg)
            raise Exception(err_msg)

        while retry_count < max_retries:
            try:
                provider_name = self.llm_provider_label or self.llm_provider.__class__.__name__
                self.progress_signal.emit(
                    50,
                    f"Sending request to {provider_name} (Attempt {retry_count + 1}/{max_retries})...",
                )
                self._safe_emit_status(f"Sending request to {provider_name} for integrated analysis. Attempt {retry_count + 1}.")
                
                # Log prompt lengths for debugging
                # self._safe_emit_status(f"System prompt length: {len(system_prompt)} chars, User prompt length: {len(prompt)} chars")

                start_time = time.time()
                api_complete = False
                response_data = None
                api_error = None

                def make_api_call_wrapper():
                    nonlocal response_data, api_error, api_complete
                    try:
                        request_params = {
                            "prompt": prompt,
                            "system_prompt": system_prompt,
                            "temperature": 0.1, # Default, can be adjusted if needed
                            "model": self.llm_effective_model # Use the specific model for the provider
                        }
                        # Some providers might not expect a model param if it's part of their endpoint (e.g. Azure)
                        # The create_provider in llm should handle this, but good to be mindful.
                        # For now, we assume model is generally required or ignored if not applicable by the provider.

                        self._safe_emit_status(f"Using model: {self.llm_effective_model} with {provider_name}") 
                        response_data = self.llm_provider.generate(**request_params)
                        api_complete = True
                    except Exception as e:
                        api_error = e
                        api_complete = True
                
                api_thread = threading.Thread(target=make_api_call_wrapper)
                api_thread.daemon = True
                api_thread.start()

                last_progress_update_time = start_time
                while not api_complete:
                    elapsed_time = time.time() - start_time
                    if time.time() - last_progress_update_time >= 5:
                        self.progress_signal.emit(
                            50 + int((elapsed_time / timeout_seconds) * 40), # Progress from 50 to 90 during API call
                            f"Waiting for {provider_name}... ({int(elapsed_time)}s elapsed)",
                        )
                        last_progress_update_time = time.time()
                    
                    if elapsed_time > timeout_seconds:
                        api_thread.join(0.1) # Attempt to clean up thread
                        raise TimeoutError(f"API request to {provider_name} timed out after {timeout_seconds}s.")
                    
                    time.sleep(0.5) # Polling interval

                if api_error:
                    raise api_error # Raise the error caught in the thread

                if response_data and response_data.get("success"):
                    self._safe_emit_status(f"Successfully received response from {provider_name}.")
                    self.progress_signal.emit(90, f"Response received from {provider_name}.")
                    return response_data
                else:
                    error_detail = response_data.get("error", "Unknown API error") if response_data else "No response data"
                    self._safe_emit_status(f"API call to {provider_name} failed: {error_detail}", "error")
                    if retry_count < max_retries - 1:
                        self._safe_emit_status(f"Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2 # Exponential backoff
                    else:
                         raise Exception(f"API call failed after {max_retries} retries: {error_detail}")
            
            except TimeoutError as te:
                self._safe_emit_status(f"Timeout error with {provider_name} (Attempt {retry_count + 1}): {str(te)}", "error")
                logging.error(f"TimeoutError during API call: {str(te)}")
                if retry_count < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise TimeoutError(f"API request timed out after {max_retries} attempts.")
            except Exception as e:
                self._safe_emit_status(f"Error with {provider_name} (Attempt {retry_count + 1}): {str(e)}", "error")
                logging.exception(f"Exception during API call to {provider_name}")
                if retry_count < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise e
            retry_count += 1
        
        raise Exception(f"API processing failed definitively after {max_retries} retries.")

    def run(self):
        """Run the integrated analysis operations."""
        try:
            if not self._initialize_llm_provider():
                # Initialization already emits its own error signals.
                # It returns false if it fails. We also emit a finished signal.
                self.finished_signal.emit(False, "LLM provider initialization failed.", "")
                return

            self.progress_signal.emit(15, "Reading combined summary file...")
            self._safe_emit_status(f"Reading combined summary file: {self.combined_summary_path}")
            with open(self.combined_summary_path, "r", encoding="utf-8") as f:
                combined_content = f.read()
            self._safe_emit_status(f"Combined summary length: {len(combined_content)} characters.")

            # Read original markdown files content
            original_docs_content = ""
            self.progress_signal.emit(20, "Reading original documents...")
            self._safe_emit_status(f"Reading {len(self.original_markdown_files)} original documents.")
            for i, md_file in enumerate(self.original_markdown_files):
                try:
                    with open(md_file, "r", encoding="utf-8") as f_md:
                        content = f_md.read()
                        original_docs_content += f"\n\n--- DOCUMENT: {os.path.basename(md_file)} ---\n\n{content}"
                    self._safe_emit_status(f"Read original document: {os.path.basename(md_file)} ({len(content)} chars)")
                except Exception as e:
                    self._safe_emit_status(f"Could not read original document {os.path.basename(md_file)}: {e}", "warning")    
            self._safe_emit_status(f"Total original documents content length: {len(original_docs_content)} characters.")

            self.progress_signal.emit(25, "Checking content size for chunking...")
            
            # Check if we need to chunk the content
            total_content = f"{combined_content}\n\n{original_docs_content}"
            
            # Estimate token count
            estimated_tokens = len(total_content) // 4
            self._safe_emit_status(f"Estimated total tokens: {estimated_tokens}")
            
            # Check if content fits in a single request (leaving room for prompts)
            if estimated_tokens < 50000:  # Conservative threshold
                # Process as single request
                self.progress_signal.emit(30, "Creating integrated analysis prompt...")
                prompt_text, system_prompt = self.create_integrated_prompt(combined_content, original_docs_content)
                self._safe_emit_status("Integrated analysis prompt created.")
                
                self.progress_signal.emit(35, "Requesting integrated analysis from LLM...")
                response = self.process_api_response(prompt=prompt_text, system_prompt=system_prompt)
                
                if response and response.get("success"):
                    integrated_analysis_content = response.get("content", "")
                else:
                    integrated_analysis_content = None
            else:
                # Process with chunking
                self.progress_signal.emit(30, "Content too large, using chunked processing...")
                self._safe_emit_status("Content exceeds single request limit, using chunked processing...")
                integrated_analysis_content = self.process_with_chunks(combined_content, original_docs_content)
            
            if integrated_analysis_content:
                if not integrated_analysis_content.strip():
                    self._safe_emit_status("LLM returned an empty integrated analysis.")
                    self.finished_signal.emit(False, "LLM returned an empty analysis.", "")
                    return

                self.progress_signal.emit(95, "Saving integrated analysis...")
                
                output_filename = f"{self.subject_name}_Integrated_Analysis_{time.strftime('%Y%m%d_%H%M%S')}.md"
                output_path = Path(self.output_dir) / "integrated_analysis" / output_filename
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(str(output_path), "w", encoding="utf-8") as f:
                    f.write(integrated_analysis_content)
                
                self._safe_emit_status(f"Integrated analysis saved to: {output_path}")
                self.progress_signal.emit(100, "Integrated analysis complete.")
                self.finished_signal.emit(True, "Integrated analysis generated successfully.", str(output_path))
            else:
                error_msg = response.get("error", "Integrated analysis failed. No content generated or API error.") if response else "Integrated analysis failed due to API communication issue."
                self._safe_emit_status(f"Failed to generate integrated analysis: {error_msg}")
                self.finished_signal.emit(False, error_msg, "")

        except Exception as e:
            error_msg = f"Error during integrated analysis: {str(e)}"
            logging.exception(error_msg)
            self._safe_emit_status(error_msg, "error")
            self.error_signal.emit(error_msg)
            self.finished_signal.emit(False, error_msg, "")

    def create_integrated_prompt(self, combined_content: str, original_docs_content: str) -> Tuple[str, str]:
        """Create the prompt for the integrated analysis."""
        # Use PromptManager to get the integrated analysis prompt template
        prompt_manager = PromptManager()
        template_data = prompt_manager.get_prompt_template("integrated_analysis")
        system_prompt_template = template_data.get("system_prompt", "")
        user_prompt_template = template_data.get("user_prompt", "")

        # Prepare placeholders
        placeholders = {
            "subject_name": self.subject_name,
            "subject_dob": self.subject_dob,
            "case_info": self.case_info,
            "combined_summaries": combined_content,
            "original_documents": original_docs_content # Added placeholder
        }

        # Populate system prompt
        system_prompt = system_prompt_template.format(**placeholders) if system_prompt_template else ""
        # Populate user prompt
        user_prompt = user_prompt_template.format(**placeholders)

        return user_prompt, system_prompt
    
    def process_with_chunks(self, combined_content: str, original_docs_content: str) -> Optional[str]:
        """Process the integrated analysis using chunking for large content.
        
        Args:
            combined_content: Combined summaries content
            original_docs_content: Original documents content
            
        Returns:
            The integrated analysis content or None if failed
        """
        try:
            # First, process summaries only
            self._safe_emit_status("Processing document summaries...")
            self.progress_signal.emit(40, "Analyzing summaries...")
            
            # Create chunks of the combined summaries
            # Get model context window to determine chunk size
            context_window = TokenCounter.get_model_context_window(self.llm_effective_model)
            # Use a conservative chunk size (leave room for prompts)
            max_tokens_per_chunk = int(context_window * 0.5)
            
            summary_chunks = ChunkingStrategy.markdown_headers(
                text=combined_content,
                max_tokens=max_tokens_per_chunk,
                overlap=2000 * 4  # Convert overlap tokens to characters (approx)
            )
            
            self._safe_emit_status(f"Summaries split into {len(summary_chunks)} chunks")
            
            # Process each summary chunk
            chunk_analyses = []
            for i, chunk in enumerate(summary_chunks):
                self.progress_signal.emit(
                    40 + int((i / len(summary_chunks)) * 30),  # 40-70% for summary processing
                    f"Processing summary chunk {i+1}/{len(summary_chunks)}..."
                )
                
                # Create prompt for this chunk
                chunk_prompt = f"""## Document Summaries (Part {i+1} of {len(summary_chunks)})

{chunk}

Please analyze these document summaries and extract:
1. Key clinical findings and diagnoses
2. Important dates and timeline events
3. Patterns of behavior or symptoms
4. Legal and forensic information
5. Treatment history and responses
6. Any contradictions or discrepancies

Focus on extracting factual information that will be important for the final integrated analysis."""

                system_prompt = f"""You are analyzing part {i+1} of {len(summary_chunks)} document summaries for {self.subject_name} (DOB: {self.subject_dob}). 
Extract and organize the most clinically relevant information. This is an intermediate analysis that will be combined with other chunks."""

                response = self.process_api_response(prompt=chunk_prompt, system_prompt=system_prompt)
                if response and response.get("success"):
                    chunk_analyses.append(response.get("content", ""))
                else:
                    self._safe_emit_status(f"Failed to process chunk {i+1}")
                    return None
            
            # Combine chunk analyses
            combined_analysis = "\n\n---\n\n".join(chunk_analyses)
            
            # Create final integrated analysis prompt
            self.progress_signal.emit(75, "Creating final integrated analysis...")
            
            final_prompt = f"""Based on the following analyzed summaries, create a comprehensive integrated analysis.

## Analyzed Document Summaries
{combined_analysis}

## Subject Information
- Name: {self.subject_name}
- Date of Birth: {self.subject_dob}

## Case Background
{self.case_info}

Please create the final integrated analysis following the structure outlined in your instructions, including:
1. Executive Summary
2. Comprehensive Timeline
3. Clinical History Integration
4. Behavioral Patterns and Themes
5. Legal and Forensic Summary
6. Substance Use History
7. Social and Family History
8. Discrepancies and Data Quality
9. Clinical Impressions

Ensure all sections are complete and professionally formatted."""

            final_system_prompt = """You are creating the final integrated analysis for a forensic psychiatrist. 
Synthesize all the information from the chunk analyses into a cohesive, comprehensive report. 
Maintain professional standards and ensure all sections are thoroughly addressed."""

            # Get final response
            self.progress_signal.emit(80, "Generating final integrated analysis...")
            final_response = self.process_api_response(prompt=final_prompt, system_prompt=final_system_prompt)
            
            if final_response and final_response.get("success"):
                return final_response.get("content", "")
            else:
                self._safe_emit_status("Failed to generate final integrated analysis")
                return None
                
        except Exception as e:
            self._safe_emit_status(f"Error in chunked processing: {str(e)}")
            logging.exception("Error in process_with_chunks")
            return None