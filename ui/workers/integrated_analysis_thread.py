"""
Worker thread for generating an integrated analysis with Claude's thinking model.
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from PySide6.QtCore import QThread, Signal, QObject

from llm_utils import (
    LLMClientFactory,
    LLMClient,
    AnthropicClient,
    GeminiClient,
    cached_count_tokens,
)
from prompt_manager import PromptManager


class IntegratedAnalysisThread(QThread):
    """Worker thread for generating an integrated analysis with Claude's thinking model."""

    progress_signal = Signal(int, str)
    finished_signal = Signal(bool, str, str)  # success, message, file_path
    error_signal = Signal(str)

    def __init__(self, combined_file, output_dir, subject_name, subject_dob, case_info):
        """Initialize the thread with the combined summary file."""
        super().__init__()
        self.combined_file = combined_file
        self.output_dir = output_dir
        self.subject_name = subject_name
        self.subject_dob = subject_dob
        self.case_info = case_info
        
        # Check for API keys in environment variables
        self._check_api_keys()
        
        # Attempt to initialize LLM clients with detailed error logging
        try:
            # Try auto detection first
            self.llm_client = LLMClientFactory.create_client(provider="auto")
            logging.info("LLM client initialized using auto provider selection")
            
            # Log which provider was selected
            if isinstance(self.llm_client, AnthropicClient) and self.llm_client.is_initialized:
                logging.info("Using Anthropic Claude as the LLM provider")
            elif isinstance(self.llm_client, GeminiClient) and self.llm_client.is_initialized:
                logging.info("Using Google Gemini as the LLM provider")
            else:
                # If auto detection failed, explicitly try Gemini
                logging.warning("Auto provider selection failed, trying Gemini explicitly")
                self.llm_client = LLMClientFactory.create_client(provider="gemini")
                
                if isinstance(self.llm_client, GeminiClient) and self.llm_client.is_initialized:
                    logging.info("Successfully initialized Gemini as fallback")
                else:
                    logging.error("Failed to initialize any LLM provider")
        except Exception as e:
            logging.error(f"Error initializing LLM client: {str(e)}")
            # Create a placeholder client to avoid NoneType errors
            self.llm_client = LLMClientFactory.create_client(provider="auto")

    def _check_api_keys(self):
        """Check and log API key availability."""
        try:
            import os

            # Check for Gemini key
            gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if gemini_key:
                masked_key = f"{gemini_key[:4]}...{gemini_key[-4:]}" if len(gemini_key) > 8 else "[too short]"
                logging.info(f"Found Gemini API key: {masked_key}")
            else:
                logging.error("No Gemini API key found in environment variables")
                
            # Check for Anthropic key
            anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
            if anthropic_key:
                masked_key = f"{anthropic_key[:4]}...{anthropic_key[-4:]}" if len(anthropic_key) > 8 else "[too short]"
                logging.info(f"Found Anthropic API key: {masked_key}")
            else:
                logging.error("No Anthropic API key found in environment variables")
                
        except Exception as e:
            logging.error(f"Error checking API keys: {str(e)}")

    def process_api_response(self, prompt, system_prompt, use_gemini=False):
        """Process API response with detailed error handling and retries."""
        max_retries = 3
        retry_count = 0
        retry_delay = 2  # seconds
        timeout_seconds = 600  # 10 minutes timeout for long analysis

        # Force using Gemini if explicitly requested or if we detect our client is a GeminiClient
        if not use_gemini and isinstance(self.llm_client, GeminiClient) and self.llm_client.is_initialized:
            use_gemini = True
            self.progress_signal.emit(40, "Detected Gemini client, switching to Gemini mode")

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
                from PySide6.QtCore import QEventLoop, QTimer

                # Prepare the request parameters - same parameters for both clients
                # Let each client handle the system_prompt appropriately
                request_params = {
                    "prompt_text": prompt,
                    "system_prompt": system_prompt,
                    "temperature": 0.1,
                }
                
                # Add model parameter for Claude
                if not use_gemini:
                    request_params["model"] = "claude-3-7-sonnet-20250219"

                # Create an event to track API response completion
                response = None
                api_error = None
                api_complete = False

                # Start the API call in the current thread, but use a timer to update progress
                # This won't block the UI thread but will keep our current thread busy
                def make_api_call():
                    nonlocal response, api_error, api_complete
                    try:
                        # Check client type and use appropriate method
                        if use_gemini:
                            # First check if we have a GeminiClient available
                            gemini_available = False
                            
                            # Check if we have a direct GeminiClient
                            if isinstance(self.llm_client, GeminiClient) and self.llm_client.is_initialized:
                                gemini_available = True
                                self.progress_signal.emit(
                                    45, "Using direct Gemini client for large token context"
                                )
                                response = self.llm_client.generate_response(**request_params)
                            
                            # Check if we have a LLMClient with Gemini methods
                            elif hasattr(self.llm_client, "gemini_initialized") and self.llm_client.gemini_initialized:
                                gemini_available = True
                                self.progress_signal.emit(
                                    45, "Using LLMClient's Gemini interface for large token context"
                                )
                                # Make a copy of request_params for Gemini since parameter names might differ
                                gemini_params = request_params.copy()
                                
                                # Check if generate_response_with_gemini expects max_output_tokens instead of max_tokens
                                if hasattr(self.llm_client, "generate_response_with_gemini"):
                                    # Add the model parameter explicitly for Gemini
                                    gemini_params["model"] = "gemini-2.5-pro-preview-05-06"
                                    
                                    # Convert max_tokens to max_output_tokens if needed
                                    if "max_tokens" in gemini_params and not hasattr(self.llm_client.generate_response_with_gemini, "max_tokens"):
                                        gemini_params["max_output_tokens"] = gemini_params.pop("max_tokens")
                                        
                                    response = self.llm_client.generate_response_with_gemini(**gemini_params)
                            
                            # Fall back to Claude if Gemini is not available
                            if not gemini_available:
                                self.progress_signal.emit(
                                    45, "Gemini client not available, falling back to Claude"
                                )
                                # Try to use Claude with standard parameters, it might reject if too large
                                try:
                                    # Add model parameter for Claude
                                    claude_params = request_params.copy()
                                    claude_params["model"] = "claude-3-7-sonnet-20250219"
                                    response = self.llm_client.generate_response(**claude_params)
                                except Exception as claude_error:
                                    # If Claude fails (likely due to token limit), log this and pass the error up
                                    self.progress_signal.emit(
                                        45, f"Claude also failed: {str(claude_error)}"
                                    )
                                    raise Exception(f"Gemini not available and Claude failed: {str(claude_error)}")
                        else:
                            # Use Anthropic client
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

    def force_init_gemini_client(self):
        """Force initialization of Gemini client specifically, regardless of what was auto-detected."""
        try:
            self.progress_signal.emit(5, "Explicitly initializing Gemini client...")
            
            # Directly create a fresh Gemini client
            # Get the API key from environment variables
            import os

            from llm_utils import GeminiClient
            gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            
            if not gemini_key:
                self.progress_signal.emit(8, "No Gemini API key found in environment variables")
                return False
                
            # Create a new client directly
            self.llm_client = LLMClientFactory.create_client(provider="gemini")
            
            # Verify it's actually a GeminiClient and initialized
            if isinstance(self.llm_client, GeminiClient) and self.llm_client.is_initialized:
                self.progress_signal.emit(10, "Successfully initialized dedicated Gemini client")
                return True
            else:
                self.progress_signal.emit(10, "Failed to initialize Gemini client properly")
                return False
        except Exception as e:
            self.progress_signal.emit(10, f"Error initializing Gemini client: {str(e)}")
            return False

    def run(self):
        """Run the integrated analysis."""
        try:
            # Define the output file path
            integrated_file = os.path.join(self.output_dir, "integrated_analysis.md")
            thinking_tokens_file = os.path.join(
                self.output_dir, "integrated_analysis_thinking_tokens.md"
            )

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
            
            # First, try to force initialize Gemini client
            gemini_initialized = self.force_init_gemini_client()
            
            # If Gemini initialization failed, check the current client
            if not gemini_initialized:
                self.progress_signal.emit(5, "Checking current LLM client...")
                if not hasattr(self.llm_client, 'is_initialized') or not self.llm_client.is_initialized:
                    self.progress_signal.emit(5, "Main LLM client not initialized, creating auto client...")
                    try:
                        # Try creating an auto client as fallback
                        self.llm_client = LLMClientFactory.create_client(provider="auto")
                        if self.llm_client.is_initialized:
                            self.progress_signal.emit(8, f"Successfully created fallback client: {self.llm_client.__class__.__name__}")
                        else:
                            self.progress_signal.emit(8, "Warning: Failed to initialize any LLM client")
                    except Exception as e:
                        self.progress_signal.emit(8, f"Error creating fallback client: {str(e)}")

            # Read the combined summary content
            with open(self.combined_file, "r", encoding="utf-8") as f:
                combined_content = f.read()

            # Update progress
            self.progress_signal.emit(20, "Creating prompt for analysis...")

            # Create the prompt for analysis
            prompt = self.create_integrated_prompt(combined_content)

            # Count tokens to determine which LLM to use
            self.progress_signal.emit(
                30, "Calculating token usage to select appropriate model..."
            )
            token_count_result = cached_count_tokens(self.llm_client, text=prompt)

            # Determine token count and decide whether to use Gemini
            use_gemini = False
            if token_count_result["success"]:
                token_count = token_count_result["token_count"]
                self.progress_signal.emit(35, f"Token count: {token_count}")

                # Only use Gemini for very large token counts (>180k)
                if token_count > 180000:  # Increased threshold to only use Gemini for very large contexts
                    use_gemini = True
                    self.progress_signal.emit(38, "Using Gemini for large token count (>180k)")
                else:
                    # Check if we have a GeminiClient already - prefer it if available
                    from llm_utils import GeminiClient
                    if isinstance(self.llm_client, GeminiClient) and self.llm_client.is_initialized:
                        use_gemini = True
                        self.progress_signal.emit(38, "Using Gemini client that's already initialized")
                    else:
                        self.progress_signal.emit(38, "Using Claude for token count <= 180k")
            else:
                # If token counting fails, check what client we have
                from llm_utils import AnthropicClient, GeminiClient
                if isinstance(self.llm_client, GeminiClient) and self.llm_client.is_initialized:
                    use_gemini = True
                    self.progress_signal.emit(35, "Token counting failed, using Gemini by client type")
                elif isinstance(self.llm_client, AnthropicClient) and self.llm_client.is_initialized:
                    use_gemini = False
                    self.progress_signal.emit(35, "Token counting failed, using Claude by client type")
                else:
                    # Default to Claude if token count fails, only try Gemini if Claude unavailable
                    use_gemini = False  
                    self.progress_signal.emit(35, "Token counting failed, using Claude as default")
                    
                    # Try to initialize Claude first
                    try:
                        self.progress_signal.emit(36, "Attempting to initialize Claude client...")
                        claude_client = self.reinitialize_llm_client(provider="anthropic")
                        if claude_client:
                            use_gemini = False
                            self.progress_signal.emit(37, "Successfully initialized Claude client")
                        else:
                            # Only try Gemini if Claude fails
                            self.progress_signal.emit(37, "Claude initialization failed, trying Gemini as fallback...")
                            gemini_initialized = self.force_init_gemini_client()
                            use_gemini = gemini_initialized
                    except Exception as e:
                        self.progress_signal.emit(36, f"Error initializing clients: {str(e)}")
                        # Default to trying Claude anyway
                        use_gemini = False
            
            # Log the final decision
            self.progress_signal.emit(
                40, f"Final decision: Using {'Gemini' if use_gemini else 'Claude'} for analysis..."
            )

            # Update progress
            self.progress_signal.emit(
                40, "Sending for analysis..."
            )

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

            # Check if we should use Gemini's extended thinking for large token counts
            if use_gemini:
                self.progress_signal.emit(42, "Using Gemini for extended token context...")
                
                # Verify we have a properly initialized Gemini client
                from llm_utils import GeminiClient
                if not isinstance(self.llm_client, GeminiClient) or not self.llm_client.is_initialized:
                    self.progress_signal.emit(43, "Gemini client not properly initialized, forcing reinitialization...")
                    gemini_initialized = self.force_init_gemini_client()
                    
                    if not gemini_initialized:
                        self.progress_signal.emit(44, "Gemini reinitialization failed, falling back to Claude...")
                        # Force Claude to be used
                        use_gemini = False
                
                # Proceed with Gemini if still selected after verification
                if use_gemini:
                    self.progress_signal.emit(43, "Using Gemini's extended thinking capabilities...")
                    
                    # Only use direct extended thinking API
                    try:
                        # Set a timer to prevent hanging indefinitely
                        import threading
                        import time
                        
                        api_complete = False
                        api_error = None
                        api_response = None
                        
                        # Define the API call function - only use extended thinking
                        def make_api_call():
                            nonlocal api_complete, api_error, api_response
                            try:
                                api_response = self.llm_client.generate_response_with_extended_thinking(
                                    prompt_text=prompt,
                                    system_prompt=system_prompt,
                                    model="gemini-2.5-pro-preview-05-06",
                                    temperature=0.5,
                                    thinking_budget_tokens=token_count // 2 if token_count_result["success"] else 20000,
                                )
                                api_complete = True
                            except Exception as e:
                                api_error = e
                                api_complete = True
                        
                        # Create and start the thread
                        api_thread = threading.Thread(target=make_api_call)
                        api_thread.daemon = True
                        api_thread.start()
                        
                        # Wait with progress updates
                        timeout = 600  # 10-minute timeout
                        start_time = time.time()
                        wait_interval = 1.0
                        
                        while not api_complete and (time.time() - start_time) < timeout:
                            elapsed = time.time() - start_time
                            if elapsed % 10 < 0.5:  # Update roughly every 10 seconds
                                self.progress_signal.emit(
                                    44, f"Waiting for Gemini extended thinking response... ({int(elapsed)}s elapsed)"
                                )
                            time.sleep(wait_interval)
                        
                        # Check if we timed out
                        if not api_complete:
                            self.progress_signal.emit(
                                44, f"Gemini API call timed out after {timeout} seconds"
                            )
                            raise Exception(f"Gemini API call timed out after {timeout} seconds")
                        
                        # Check if there was an error
                        if api_error:
                            raise api_error
                        
                        # Check if the response is empty or invalid
                        if not api_response or not api_response.get("success", False):
                            error_msg = api_response.get("error", "Unknown error") if api_response else "No response"
                            self.progress_signal.emit(45, f"Gemini API error: {error_msg}")
                            raise Exception(f"Gemini API error: {error_msg}")
                            
                        # Check if the content is empty
                        if not api_response.get("content") or len(api_response.get("content", "")) == 0:
                            self.progress_signal.emit(45, "Received empty response from Gemini")
                            raise Exception("Gemini returned empty response content")
                            
                        # Check if thinking tokens were returned
                        if not api_response.get("thinking") or len(api_response.get("thinking", "")) == 0:
                            self.progress_signal.emit(46, "Warning: No thinking tokens received from Gemini")
                            
                        # Use the response
                        response = api_response
                        self.progress_signal.emit(48, "Gemini extended thinking successful")
                        
                    except Exception as e:
                        self.progress_signal.emit(44, f"Error with Gemini extended thinking: {str(e)}")
                        self.progress_signal.emit(47, "Falling back to Claude as last resort...")
                        use_gemini = False
                        
            # Use Claude's extended thinking if not using Gemini
            if not use_gemini and hasattr(self.llm_client, "generate_response_with_extended_thinking"):
                self.progress_signal.emit(42, "Using Claude's extended thinking capabilities...")

                # Set a reasonable thinking budget
                thinking_budget_tokens = (
                    min(16000, token_count // 2)
                    if token_count_result["success"]
                    else 16000
                )

                # Generate with extended thinking
                response = self.llm_client.generate_response_with_extended_thinking(
                    prompt_text=prompt,
                    system_prompt=system_prompt,
                    model="claude-3-7-sonnet-20250219",
                    temperature=0.1,
                    thinking_budget_tokens=thinking_budget_tokens,
                )
            elif not use_gemini:
                # Use our process_api_response method for regular API calls
                self.progress_signal.emit(42, "Using standard API request...")
                response = self.process_api_response(prompt, system_prompt, use_gemini)

            # Update progress
            self.progress_signal.emit(90, "Processing response...")

            if not response["success"]:
                raise Exception(
                    f"LLM processing failed: {response.get('error', 'Unknown error')}"
                )
                
            # Save thinking tokens to a separate file if available
            if (
                response["success"]
                and "thinking" in response
                and response["thinking"]
            ):
                self.progress_signal.emit(
                    82, "Saving thinking tokens to separate file..."
                )

                # Create thinking tokens content with header information
                thinking_content = f"""# Thinking Tokens for Integrated Analysis of {self.subject_name}

## Subject Information
- **Subject Name**: {self.subject_name}
- **Date of Birth**: {self.subject_dob}
- **Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}
- **Model**: {response.get("model", "Unknown")}
- **Provider**: {response.get("provider", "Unknown")}

## Thinking Process
{response["thinking"]}
"""
                # Write thinking tokens to file
                with open(thinking_tokens_file, "w", encoding="utf-8") as f:
                    f.write(thinking_content)

                self.progress_signal.emit(
                    85, f"Thinking tokens saved to {thinking_tokens_file}"
                )
            else:
                self.progress_signal.emit(
                    82, "No thinking tokens available in the response"
                )

            # Write the integrated analysis to a file
            with open(integrated_file, "w", encoding="utf-8") as f:
                f.write(f"# Integrated Analysis for {self.subject_name}\n\n")
                f.write(f"**Date of Birth:** {self.subject_dob}\n\n")
                f.write(f"**Model Used:** {response.get('model', 'Unknown')}\n")
                f.write(f"**Provider:** {response.get('provider', 'Unknown')}\n\n")
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
## Combined Document Summaries
<combined_summaries>
{combined_content}
</combined_summaries>

# Integrated Document Analysis Task

## Subject Information
- **Subject Name**: {self.subject_name}
- **Date of Birth**: {self.subject_dob}

## Case Background
{self.case_info}

## Instructions
I'm providing you with multiple document summaries that contain information about the subject (or subjects). The summaries are from markdown versions of original PDF documents. Please analyze all of these summaries and create a comprehensive integrated report per subject that includes:

1. **Executive Summary**: A clear, concise overview of the subject based on all documents (700-1000 words).

2. **Comprehensive Timeline**: Create a single, unified timeline that combines all events from the individual document timelines. The timeline should:
   - Be in chronological order (oldest to newest)
   - Be formatted as a markdown table with columns for Date, Event, Significance, and Source Document Name(s)
   - Create or preserve all markdown links to the original PDF page number in the format [Page x](./pdfs/<filename.pdf>#page=<page_number>)
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

5. **Create or preserve all markdown links to the original PDF page number in the format [file  name.pdf: Page x](./pdfs/<filename.pdf>#page=<page_number>)

Please use your thinking capabilities to connect information across documents, identify patterns, and create a coherent narrative from these separate summaries. When information appears contradictory, note the discrepancy rather than trying to resolve it definitively.

Before finalizing results, do a review for accuracy, with attention to both exact quotes and markdown links to original PDFs.
"""

    def reinitialize_llm_client(self, provider="auto"):
        """
        Reinitialize the LLM client with an explicit provider if needed.
        
        Args:
            provider: The provider to use ("auto", "anthropic", or "gemini")
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logging.info(f"Reinitializing LLM client with provider={provider}")
            self.llm_client = LLMClientFactory.create_client(provider=provider)
            
            if self.llm_client.is_initialized:
                logging.info(f"Successfully reinitialized LLM client with provider={provider}")
                
                # Log which provider was selected
                if isinstance(self.llm_client, AnthropicClient):
                    logging.info("Using Anthropic Claude as the LLM provider")
                elif isinstance(self.llm_client, GeminiClient):
                    logging.info("Using Google Gemini as the LLM provider")
                
                return True
            else:
                logging.error(f"Failed to initialize LLM client with provider={provider}")
                return False
        except Exception as e:
            logging.error(f"Error reinitializing LLM client: {str(e)}")
            return False
