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

from app_config import get_configured_llm_client
from llm_utils import (
    AnthropicClient,
    GeminiClient,
    LLMClient,
    LLMClientFactory,
    cached_count_tokens,
)
from prompt_manager import PromptManager


class IntegratedAnalysisThread(QThread):
    """Worker thread for generating an integrated analysis with Claude's thinking model."""

    progress_signal = Signal(int, str)
    finished_signal = Signal(bool, str, str)  # success, message, file_path
    error_signal = Signal(str)

    def __init__(self, 
                 parent, 
                 combined_summary_path, 
                 original_markdown_files, 
                 output_dir, 
                 subject_name, 
                 subject_dob, 
                 case_info,
                 status_panel, 
                 progress_dialog, # This is QProgressDialog instance
                 llm_provider_id, 
                 llm_model_name):
        """Initialize the thread."""
        super().__init__(parent)
        self.combined_summary_path = combined_summary_path
        self.original_markdown_files = original_markdown_files
        self.output_dir = output_dir
        self.subject_name = subject_name
        self.subject_dob = subject_dob
        self.case_info = case_info
        self.status_panel = status_panel
        self.progress_dialog = progress_dialog # Store the QProgressDialog
        self.llm_provider_id = llm_provider_id
        self.llm_model_name = llm_model_name
        
        self.llm_client: Optional[LLMClient] = None
        self.llm_client_provider_label: Optional[str] = None
        self.llm_client_effective_model: Optional[str] = None

    def _initialize_llm_client(self) -> bool:
        """Initialize LLM client using specified provider and model."""
        try:
            self.progress_signal.emit(5, f"Initializing LLM: {self.llm_provider_id} ({self.llm_model_name})...")
            self.status_panel.append_details(
                f"Attempting to initialize LLM client for integrated analysis: Provider ID: {self.llm_provider_id}, Model: {self.llm_model_name}"
            )
            
            client_info = get_configured_llm_client(
                provider_id_override=self.llm_provider_id,
                model_override=self.llm_model_name
            )

            if client_info and client_info.get("client"):
                self.llm_client = client_info["client"]
                if self.llm_client.is_initialized:
                    self.llm_client_provider_label = client_info.get("provider_label", self.llm_provider_id)
                    self.llm_client_effective_model = client_info.get("effective_model_name", self.llm_model_name)
                    self.status_panel.append_details(
                        f"Successfully initialized LLM client: {self.llm_client_provider_label} ({self.llm_client_effective_model}) for integrated analysis."
                    )
                    self.progress_signal.emit(10, f"LLM client {self.llm_client_provider_label} initialized.")
                    return True
                else:
                    error_msg = f"LLM client for {client_info.get('provider_label', self.llm_provider_id)} could not be initialized (is_initialized flag is false)."
                    self.status_panel.append_error(error_msg)
                    logging.error(error_msg)
                    self.error_signal.emit(error_msg)
                    return False
            else:
                error_msg = f"Failed to get configured LLM client for Provider: {self.llm_provider_id}, Model: {self.llm_model_name}. Review app_config logs and settings."
                self.status_panel.append_error(error_msg)
                logging.error(error_msg)
                self.error_signal.emit(error_msg)
                return False
        except Exception as e:
            error_msg = f"Exception initializing LLM client ({self.llm_provider_id}/{self.llm_model_name}) for integrated analysis: {str(e)}"
            self.status_panel.append_error(error_msg)
            logging.exception(error_msg)
            self.error_signal.emit(error_msg)
            return False

    def process_api_response(self, prompt: str, system_prompt: str) -> Optional[Dict[str, Any]]:
        """Process API response with detailed error handling and retries using the configured LLM client."""
        max_retries = 3
        retry_count = 0
        retry_delay = 5  # seconds, increased from 2
        timeout_seconds = 900  # 15 minutes timeout for potentially very long analysis

        if not self.llm_client or not self.llm_client.is_initialized:
            err_msg = "LLM client not initialized. Cannot process API response."
            self.status_panel.append_error(err_msg)
            raise Exception(err_msg)

        while retry_count < max_retries:
            try:
                provider_name = self.llm_client_provider_label or self.llm_client.provider
                self.progress_signal.emit(
                    50,
                    f"Sending request to {provider_name} (Attempt {retry_count + 1}/{max_retries})...",
                )
                self.status_panel.append_details(f"Sending request to {provider_name} for integrated analysis. Attempt {retry_count + 1}.")
                
                # Log prompt lengths for debugging
                # self.status_panel.append_details(f"System prompt length: {len(system_prompt)} chars, User prompt length: {len(prompt)} chars")

                start_time = time.time()
                api_complete = False
                response_data = None
                api_error = None

                def make_api_call_wrapper():
                    nonlocal response_data, api_error, api_complete
                    try:
                        request_params = {
                            "prompt_text": prompt,
                            "system_prompt": system_prompt,
                            "temperature": 0.1, # Default, can be adjusted if needed
                            "model": self.llm_client_effective_model # Use the specific model for the client
                        }
                        # Some clients might not expect a model param if it's part of their endpoint (e.g. Azure)
                        # The create_client in llm_utils should handle this, but good to be mindful.
                        # For now, we assume model is generally required or ignored if not applicable by the client.

                        self.status_panel.append_details(f"Using model: {self.llm_client_effective_model} with {provider_name}") 
                        response_data = self.llm_client.generate_response(**request_params)
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
                    self.status_panel.append_details(f"Successfully received response from {provider_name}.")
                    self.progress_signal.emit(90, f"Response received from {provider_name}.")
                    return response_data
                else:
                    error_detail = response_data.get("error", "Unknown API error") if response_data else "No response data"
                    self.status_panel.append_error(f"API call to {provider_name} failed: {error_detail}")
                    if retry_count < max_retries - 1:
                        self.status_panel.append_details(f"Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2 # Exponential backoff
                    else:
                         raise Exception(f"API call failed after {max_retries} retries: {error_detail}")
            
            except TimeoutError as te:
                self.status_panel.append_error(f"Timeout error with {provider_name} (Attempt {retry_count + 1}): {str(te)}")
                logging.error(f"TimeoutError during API call: {str(te)}")
                if retry_count < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise TimeoutError(f"API request timed out after {max_retries} attempts.")
            except Exception as e:
                self.status_panel.append_error(f"Error with {provider_name} (Attempt {retry_count + 1}): {str(e)}")
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
            if not self._initialize_llm_client():
                # Initialization already emits its own error signals.
                # It returns false if it fails. We also emit a finished signal.
                self.finished_signal.emit(False, "LLM client initialization failed.", "")
                return

            self.progress_signal.emit(15, "Reading combined summary file...")
            self.status_panel.append_details(f"Reading combined summary file: {self.combined_summary_path}")
            with open(self.combined_summary_path, "r", encoding="utf-8") as f:
                combined_content = f.read()
            self.status_panel.append_details(f"Combined summary length: {len(combined_content)} characters.")

            # Read original markdown files content
            original_docs_content = ""
            self.progress_signal.emit(20, "Reading original documents...")
            self.status_panel.append_details(f"Reading {len(self.original_markdown_files)} original documents.")
            for i, md_file in enumerate(self.original_markdown_files):
                try:
                    with open(md_file, "r", encoding="utf-8") as f_md:
                        content = f_md.read()
                        original_docs_content += f"\n\n--- DOCUMENT: {os.path.basename(md_file)} ---\n\n{content}"
                    self.status_panel.append_details(f"Read original document: {os.path.basename(md_file)} ({len(content)} chars)")
                except Exception as e:
                    self.status_panel.append_warning(f"Could not read original document {os.path.basename(md_file)}: {e}")    
            self.status_panel.append_details(f"Total original documents content length: {len(original_docs_content)} characters.")

            self.progress_signal.emit(25, "Creating integrated analysis prompt...")
            prompt_text, system_prompt = self.create_integrated_prompt(combined_content, original_docs_content)
            self.status_panel.append_details("Integrated analysis prompt created.")
            # self.status_panel.append_details(f"System Prompt: {system_prompt[:200]}...")
            # self.status_panel.append_details(f"User Prompt: {prompt_text[:200]}...")

            self.progress_signal.emit(30, "Requesting integrated analysis from LLM...")
            response = self.process_api_response(prompt=prompt_text, system_prompt=system_prompt)

            if response and response.get("success"):
                integrated_analysis_content = response.get("content", "")
                if not integrated_analysis_content.strip():
                    self.status_panel.append_error("LLM returned an empty integrated analysis.")
                    self.finished_signal.emit(False, "LLM returned an empty analysis.", "")
                    return

                self.progress_signal.emit(95, "Saving integrated analysis...")
                
                output_filename = f"{self.subject_name}_Integrated_Analysis_{time.strftime('%Y%m%d_%H%M%S')}.md"
                output_path = Path(self.output_dir) / "integrated_analysis" / output_filename
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(str(output_path), "w", encoding="utf-8") as f:
                    f.write(integrated_analysis_content)
                
                self.status_panel.append_details(f"Integrated analysis saved to: {output_path}")
                self.progress_signal.emit(100, "Integrated analysis complete.")
                self.finished_signal.emit(True, "Integrated analysis generated successfully.", str(output_path))
            else:
                error_msg = response.get("error", "Integrated analysis failed. No content generated or API error.") if response else "Integrated analysis failed due to API communication issue."
                self.status_panel.append_error(f"Failed to generate integrated analysis: {error_msg}")
                self.finished_signal.emit(False, error_msg, "")

        except Exception as e:
            error_msg = f"Error during integrated analysis: {str(e)}"
            logging.exception(error_msg)
            self.status_panel.append_error(error_msg)
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
