"""
Utility functions and classes for interacting with LLM providers.
Provides a structured approach to LLM connections and prompt management.
"""

import abc
import base64
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# -----------------------
# Base LLM Client Class
# -----------------------


class BaseLLMClient(abc.ABC):
    """Abstract base class for LLM clients."""

    def __init__(
        self,
        timeout: float = 600.0,
        max_retries: int = 2,
        thinking_budget_tokens: int = 16000,
        default_system_prompt: Optional[str] = None,
        debug: bool = False,
    ):
        """
        Initialize the base LLM client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for API requests
            thinking_budget_tokens: Budget for "thinking" tokens in extended thinking mode
            default_system_prompt: Default system prompt to use when none is provided
            debug: Debug mode flag
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.thinking_budget_tokens = thinking_budget_tokens
        self.debug = debug

        # Set default system prompt if not provided
        if default_system_prompt is None:
            self.default_system_prompt = "You are an advanced assistant designed to help a forensic psychiatrist. Your task is to analyze and objectively document case information in a formal clinical style, maintaining professional psychiatric documentation standards. Distinguish between information from the subject and objective findings. Report specific details such as dates, frequencies, dosages, and other relevant clinical data. Document without emotional language or judgment."
        else:
            self.default_system_prompt = default_system_prompt

        # Load environment variables
        self._load_env_vars()

    def _load_env_vars(self):
        """Load environment variables from .env file."""
        env_path = Path(".") / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            # Try to use template if .env doesn't exist
            template_path = Path(".") / "config.template.env"
            if template_path.exists():
                load_dotenv(template_path)

    @abc.abstractmethod
    def generate_response(
        self,
        prompt_text: str,
        model: str,
        max_tokens: int = 32000,
        temperature: float = 0.0,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a response from the LLM."""
        pass

    @abc.abstractmethod
    def count_tokens(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
        text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Count tokens in a message or text."""
        pass

    @abc.abstractproperty
    def is_initialized(self) -> bool:
        """Check if the client is properly initialized."""
        pass


# -----------------------
# Anthropic Client
# -----------------------


class AnthropicClient(BaseLLMClient):
    """Client for the Anthropic Claude API."""

    def __init__(
        self,
        timeout: float = 600.0,
        max_retries: int = 2,
        thinking_budget_tokens: int = 16000,
        default_system_prompt: Optional[str] = None,
        api_key: Optional[str] = None,
        debug: bool = False,
    ):
        """
        Initialize the Anthropic client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for API requests
            thinking_budget_tokens: Budget for "thinking" tokens in extended thinking mode
            default_system_prompt: Default system prompt to use when none is provided
            api_key: Optional API key (will use ANTHROPIC_API_KEY from env if not provided)
            debug: Debug mode flag
        """
        super().__init__(
            timeout=timeout,
            max_retries=max_retries,
            thinking_budget_tokens=thinking_budget_tokens,
            default_system_prompt=default_system_prompt,
            debug=debug,
        )

        self.client = None
        self._init_client(api_key)

    def _init_client(self, api_key: Optional[str] = None):
        """
        Initialize the Anthropic client.

        Args:
            api_key: Optional API key
        """
        try:
            import anthropic

            # Get API key
            if api_key:
                os.environ["ANTHROPIC_API_KEY"] = api_key

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logging.error("ANTHROPIC_API_KEY environment variable not set")
                return

            # Check if the API key is the template value
            if api_key == "your_api_key_here":
                logging.error("ANTHROPIC_API_KEY is set to the template value")
                return

            # Log first few chars of API key for verification
            if len(api_key) > 8:
                logging.info(
                    f"Using Anthropic API key starting with: {api_key[:4]}...{api_key[-4:]}"
                )

            self.client = anthropic.Anthropic(
                api_key=api_key,
                timeout=self.timeout,
                max_retries=self.max_retries,
                default_headers={"anthropic-version": "2023-06-01"},
            )

            # Test with a simple token count
            self._test_connection()

        except ImportError:
            logging.error(
                "anthropic package not installed - please install with: pip install anthropic"
            )
        except Exception as e:
            logging.error(f"Error initializing Anthropic client: {str(e)}")
            self.client = None

    def _test_connection(self):
        """Test the connection to Anthropic API."""
        try:
            if not self.client:
                return

            test_result = self.count_tokens(text="Test connection")
            if not test_result["success"]:
                logging.error(
                    f"Anthropic connection test failed: {test_result.get('error')}"
                )
                self.client = None
            else:
                logging.info("Anthropic client initialized and tested successfully")
        except Exception as e:
            logging.error(f"Anthropic connection test failed: {str(e)}")
            self.client = None

    @property
    def is_initialized(self) -> bool:
        """Check if the client is properly initialized."""
        return self.client is not None

    def generate_response(
        self,
        prompt_text: str,
        model: str = "claude-3-7-sonnet-20250219",
        max_tokens: int = 32000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Claude using the provided prompt and system prompt.

        Args:
            prompt_text: The user's prompt text
            system_prompt: Optional system prompt for context
            temperature: Temperature parameter for generation (0.0 to 1.0)
            max_tokens: Maximum number of tokens to generate

        Returns:
            A dictionary with the response content or error message
        """
        if not self.is_initialized:
            return {"success": False, "error": "Anthropic client not initialized"}

        try:
            # Set default system prompt if not provided
            if not system_prompt:
                system_prompt = "You are Claude, a helpful AI assistant."

            # Set options for the Claude API
            options = {
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system_prompt,
            }

            # Log the request details
            logging.debug(
                f"Anthropic API Request - System prompt length: {len(system_prompt)}"
            )
            logging.debug(
                f"Anthropic API Request - User prompt length: {len(prompt_text)}"
            )
            logging.debug(f"Anthropic API Request - Temperature: {temperature}")
            logging.debug(f"Anthropic API Request - Max tokens: {max_tokens}")

            # Time the API call
            start_time = time.time()

            try:
                # Make the API call to Claude
                message = self.client.messages.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt_text}],
                    **options,
                )

                # Extract the response
                content = message.content[0].text

                # Calculate elapsed time
                elapsed_time = time.time() - start_time
                logging.debug(
                    f"Anthropic API Response received in {elapsed_time:.2f} seconds"
                )

                # Get token usage if available
                usage = {}
                if hasattr(message, "usage"):
                    usage = {
                        "input_tokens": message.usage.input_tokens,
                        "output_tokens": message.usage.output_tokens,
                    }
                    logging.debug(
                        f"Anthropic API Token usage - Input: {usage['input_tokens']}, Output: {usage['output_tokens']}"
                    )

                return {
                    "success": True,
                    "content": content,
                    "usage": usage,
                    "provider": "anthropic",
                }

            except Exception as e:
                # Handle specific API errors with helpful messages
                error_message = str(e)

                if "rate limit" in error_message.lower() or "429" in error_message:
                    error_message = f"Rate limit exceeded: {error_message}. Try again in a few minutes."
                elif "bad gateway" in error_message.lower() or "502" in error_message:
                    error_message = f"Anthropic API service unavailable (502): {error_message}. Try again later."
                elif "timeout" in error_message.lower():
                    error_message = f"Request timeout: {error_message}. The API took too long to respond."
                elif (
                    "authentication" in error_message.lower()
                    or "api key" in error_message.lower()
                ):
                    error_message = (
                        f"Authentication error: {error_message}. Check your API key."
                    )

                logging.error(f"Anthropic API Error: {error_message}")
                return {
                    "success": False,
                    "error": error_message,
                    "provider": "anthropic",
                }

        except Exception as e:
            # Handle any other unexpected errors
            error_message = f"Unexpected error in Anthropic client: {str(e)}"
            logging.error(error_message)
            return {"success": False, "error": error_message, "provider": "anthropic"}

    def generate_response_with_pdf(
        self,
        prompt_text: str,
        pdf_file_path: str,
        model: str = "claude-3-7-sonnet-20250219",
        max_tokens: int = 32000,
        temperature: float = 0.0,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Claude for a given prompt and PDF file.

        Args:
            prompt_text: The prompt to send to Claude
            pdf_file_path: Path to the PDF file to analyze
            model: The Claude model to use
            max_tokens: Maximum number of tokens in the response
            temperature: Temperature parameter (randomness)
            system_prompt: Optional system prompt to set context

        Returns:
            Dictionary with response information
        """
        if not self.is_initialized:
            return {
                "success": False,
                "error": "Anthropic client not initialized",
                "content": None,
            }

        try:
            # Verify the PDF file exists
            if not os.path.exists(pdf_file_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_file_path}")

            # Read the PDF file
            with open(pdf_file_path, "rb") as f:
                pdf_data = f.read()

            # Prepare the messages with the PDF attachment
            message_params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text},
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": base64.b64encode(pdf_data).decode("utf-8"),
                                },
                            },
                        ],
                    }
                ],
            }

            # Use the default system prompt if none is provided
            if system_prompt is None:
                message_params["system"] = self.default_system_prompt
            else:
                message_params["system"] = system_prompt

            # Create the message
            response = self.client.messages.create(
                **message_params,
                timeout=self.timeout,  # Explicitly set timeout on API request
            )

            # Extract the response content
            content = ""
            for block in response.content:
                if (
                    block.type == "text"
                    and hasattr(block, "text")
                    and block.text is not None
                ):
                    content += block.text

            # Construct the result
            result = {
                "success": True,
                "content": content,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                "model": model,
                "provider": "anthropic",
            }

            return result

        except Exception as e:
            logging.error(f"Error with PDF processing: {str(e)}")
            return {
                "success": False,
                "error": f"Error with PDF: {str(e)}",
                "content": None,
            }

    def generate_response_with_extended_thinking(
        self,
        prompt_text: str,
        model: str = "claude-3-7-sonnet-20250219",
        max_tokens: int = 32000,
        temperature: float = 1.0,  # Fixed at 1.0 as required by Anthropic for thinking
        system_prompt: Optional[str] = None,
        thinking_budget_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Claude using extended thinking mode.

        Args:
            prompt_text: The prompt to send to Claude
            model: The Claude model to use
            max_tokens: Maximum number of tokens in the response
            temperature: Temperature parameter (randomness)
            system_prompt: Optional system prompt to set context
            thinking_budget_tokens: Override for thinking token budget

        Returns:
            Dictionary with response information including thinking and final response
        """
        if not self.is_initialized:
            return {
                "success": False,
                "error": "Anthropic client not initialized",
                "content": None,
                "thinking": None,
            }

        try:
            # Use instance default if not specified
            if thinking_budget_tokens is None:
                thinking_budget_tokens = self.thinking_budget_tokens

            # Ensure thinking budget is always less than max_tokens
            if thinking_budget_tokens >= max_tokens:
                thinking_budget_tokens = max_tokens - 1000

            # Prepare message parameters with thinking enabled
            message_params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 1.0,  # Always 1.0 for thinking, regardless of parameter
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": thinking_budget_tokens,
                },
                "messages": [{"role": "user", "content": prompt_text}],
            }

            # Use the default system prompt if none is provided
            if system_prompt is None:
                message_params["system"] = self.default_system_prompt
            else:
                message_params["system"] = system_prompt

            # Create the message
            response = self.client.messages.create(
                **message_params,
                timeout=self.timeout,  # Explicitly set timeout on API request
            )

            # Extract content and thinking from response
            content = ""
            thinking = ""
            has_redacted_thinking = False

            for block in response.content:
                if (
                    block.type == "text"
                    and hasattr(block, "text")
                    and block.text is not None
                ):
                    content += block.text
                elif (
                    block.type == "thinking"
                    and hasattr(block, "thinking")
                    and block.thinking is not None
                ):
                    thinking += block.thinking
                elif block.type == "redacted_thinking" and hasattr(block, "data"):
                    has_redacted_thinking = True

            # Add note about redacted thinking if present
            if has_redacted_thinking:
                redacted_note = "\n\n[NOTE: Some thinking was flagged by safety systems and encrypted.]\n\n"
                if thinking:
                    thinking += redacted_note
                else:
                    thinking = redacted_note

            # Construct the result
            result = {
                "success": True,
                "content": content,
                "thinking": thinking,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                "model": model,
                "provider": "anthropic",
            }

            return result

        except Exception as e:
            logging.error(f"Error with extended thinking: {str(e)}")
            return {
                "success": False,
                "error": f"Error with thinking: {str(e)}",
                "content": None,
                "thinking": None,
            }

    def count_tokens(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
        text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Count tokens in a message or text.

        Args:
            messages: List of messages to count tokens for
            text: Plain text to count tokens for (used if messages is None)

        Returns:
            Dictionary with token count information
        """
        if not self.is_initialized:
            return {
                "success": False,
                "error": "Anthropic client not initialized",
            }

        try:
            import anthropic

            # If only text is provided, create a simple message with it
            if messages is None and text is not None:
                messages = [{"role": "user", "content": text}]
            elif messages is None and text is None:
                return {
                    "success": False,
                    "error": "Either messages or text must be provided",
                }

            # Count tokens using the messages.count_tokens method
            try:
                response = self.client.messages.count_tokens(
                    model="claude-3-7-sonnet-20250219", messages=messages
                )

                # Handle different response structures
                if hasattr(response, "input_tokens"):
                    return {"success": True, "token_count": response.input_tokens}
                elif hasattr(response, "usage") and hasattr(
                    response.usage, "input_tokens"
                ):
                    return {"success": True, "token_count": response.usage.input_tokens}
                elif isinstance(response, dict):
                    if "input_tokens" in response:
                        return {
                            "success": True,
                            "token_count": response["input_tokens"],
                        }
                    elif "usage" in response and "input_tokens" in response["usage"]:
                        return {
                            "success": True,
                            "token_count": response["usage"]["input_tokens"],
                        }

                # Could not determine token count
                return {
                    "success": False,
                    "error": "Unknown response structure for token counting",
                }

            except Exception as e:
                # Fallback to simple character-based estimation
                if text:
                    estimated_tokens = len(text) // 4  # Rough estimate
                    return {
                        "success": True,
                        "token_count": estimated_tokens,
                        "estimated": True,
                    }
                else:
                    try:
                        combined_text = " ".join(
                            [
                                m.get("content", "")
                                for m in messages
                                if isinstance(m.get("content", ""), str)
                            ]
                        )
                        estimated_tokens = len(combined_text) // 4
                        return {
                            "success": True,
                            "token_count": estimated_tokens,
                            "estimated": True,
                        }
                    except:
                        return {
                            "success": False,
                            "error": f"Token counting failed: {str(e)}",
                        }

        except Exception as e:
            logging.error(f"Token counting error: {str(e)}")
            return {"success": False, "error": f"Token counting error: {str(e)}"}


# -----------------------
# Google Gemini Client
# -----------------------


class GeminiClient(BaseLLMClient):
    """Client for the Google Gemini API."""

    def __init__(
        self,
        timeout: float = 600.0,
        max_retries: int = 2,
        thinking_budget_tokens: int = 16000,
        default_system_prompt: Optional[str] = None,
        api_key: Optional[str] = None,
        debug: bool = False,
    ):
        """
        Initialize the Gemini client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for API requests
            thinking_budget_tokens: Budget for "thinking" tokens in extended thinking mode
            default_system_prompt: Default system prompt to use when none is provided
            api_key: Optional API key (will use GEMINI_API_KEY from env if not provided)
            debug: Debug mode flag
        """
        super().__init__(
            timeout=timeout,
            max_retries=max_retries,
            thinking_budget_tokens=thinking_budget_tokens,
            default_system_prompt=default_system_prompt,
            debug=debug,
        )

        self.gemini_model = None
        self._init_client(api_key)

    def _init_client(self, api_key: Optional[str] = None):
        """
        Initialize the Gemini client.

        Args:
            api_key: Optional API key
        """
        try:
            # Check for Google Generative AI package
            try:
                import google.generativeai as genai
            except ImportError:
                logging.error(
                    "google-generativeai package not installed - please install with: pip install google-generativeai"
                )
                return

            # Get API key
            if api_key:
                os.environ["GEMINI_API_KEY"] = api_key

            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logging.error(
                    "GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set"
                )
                return

            # Configure the Gemini API
            genai.configure(api_key=api_key)
            self.gemini_model = genai.GenerativeModel(
                "models/gemini-2.5-pro-preview-03-25"
            )

            # Log successful initialization
            logging.info(
                "Google Gemini client initialized with model: models/gemini-2.5-pro-preview-03-25"
            )

        except Exception as e:
            logging.error(f"Error initializing Gemini client: {str(e)}")
            self.gemini_model = None

    @property
    def is_initialized(self) -> bool:
        """Check if the client is properly initialized."""
        return self.gemini_model is not None

    def generate_response(
        self,
        prompt_text: str,
        model: str = "models/gemini-2.5-pro-preview-03-25",
        max_tokens: int = 200000,  # Increased from 32000 to leverage 2M token context window
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Gemini for a given prompt.

        Args:
            prompt_text: The prompt to send to Gemini
            model: The Gemini model to use
            max_tokens: Maximum number of tokens in the response (increased to 200k for large responses)
            temperature: Temperature parameter (randomness)
            system_prompt: Optional system prompt to set context

        Returns:
            Dictionary with response information
        """
        if not self.is_initialized:
            return {
                "success": False,
                "error": "Gemini client not initialized",
                "content": None,
            }

        try:
            # Combine the system prompt with user prompt for Gemini
            # Gemini doesn't have a separate system prompt concept
            combined_prompt = prompt_text
            if system_prompt:
                combined_prompt = f"{system_prompt}\n\n{prompt_text}"

            # Log the request details
            logging.debug(
                f"Gemini API Request - Combined prompt length: {len(combined_prompt)}"
            )
            logging.debug(f"Gemini API Request - Temperature: {temperature}")
            logging.debug(f"Gemini API Request - Max tokens: {max_tokens}")

            # Time the API call
            start_time = time.time()

            try:
                # Configure generation parameters
                generation_config = {
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                    "top_p": 0.95,
                    "top_k": 40,
                }

                # Get a response
                response = self.gemini_model.generate_content(
                    combined_prompt,
                    generation_config=generation_config,
                )

                # Calculate elapsed time
                elapsed_time = time.time() - start_time
                logging.debug(
                    f"Gemini API Response received in {elapsed_time:.2f} seconds"
                )

                # Check for blocked response
                if (
                    hasattr(response, "candidates")
                    and len(response.candidates) > 0
                    and hasattr(response.candidates[0], "finish_reason")
                    and response.candidates[0].finish_reason == "SAFETY"
                ):
                    return {
                        "success": False,
                        "error": "Content was blocked by safety filters",
                        "provider": "gemini",
                    }

                # Extract the response text
                if hasattr(response, "text"):
                    content = response.text
                elif (
                    hasattr(response, "candidates")
                    and len(response.candidates) > 0
                    and hasattr(response.candidates[0], "content")
                    and hasattr(response.candidates[0].content, "parts")
                    and len(response.candidates[0].content.parts) > 0
                ):
                    content = response.candidates[0].content.parts[0].text
                else:
                    return {
                        "success": False,
                        "error": "Invalid response format from Gemini API",
                        "provider": "gemini",
                    }

                # Gemini doesn't provide token usage information
                # Estimate based on chars
                char_count = len(combined_prompt) + len(content)
                token_estimate = char_count // 4  # Rough estimate of chars to tokens

                usage = {
                    "input_tokens": len(combined_prompt) // 4,  # Rough estimate
                    "output_tokens": len(content) // 4,  # Rough estimate
                }

                logging.debug(
                    f"Gemini API Estimated token usage - Input: ~{usage['input_tokens']}, Output: ~{usage['output_tokens']}"
                )

                return {
                    "success": True,
                    "content": content,
                    "usage": usage,
                    "provider": "gemini",
                }

            except Exception as e:
                logging.error(f"Error from Gemini API: {str(e)}")
                return {
                    "success": False,
                    "error": f"Gemini API error: {str(e)}",
                    "provider": "gemini",
                }

        except Exception as e:
            logging.error(f"Error in Gemini request: {str(e)}")
            return {
                "success": False,
                "error": f"Error in Gemini request: {str(e)}",
                "provider": "gemini",
            }

    def generate_response_with_extended_thinking(
        self,
        prompt_text: str,
        model: str = "models/gemini-2.5-pro-preview-03-25",
        max_tokens: int = 200000,  # Increased from 32000 to leverage 2M token context window
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        thinking_budget_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Gemini leveraging its long context capabilities and step-by-step thinking.

        This function uses the meta_prompt structure from llm_summary_thread.py.

        Args:
            prompt_text: The prompt to send to Gemini, should follow meta_prompt structure
            model: The Gemini model to use (default is 2.5 Pro Preview)
            max_tokens: Maximum number of tokens in the response (default 200k to leverage 2M token context window)
            temperature: Temperature parameter (randomness)
            system_prompt: Optional system prompt to set context
            thinking_budget_tokens: Not used for Gemini but included for API compatibility

        Returns:
            Dictionary with response information including thinking and final response
        """
        if not self.is_initialized:
            return {
                "success": False,
                "error": "Gemini client not initialized",
                "content": None,
                "thinking": None,
            }

        try:
            # Set temperature for optimal reasoning quality
            actual_temperature = max(0.2, min(0.7, temperature))

            # Generate the response using the standard generate_response method
            # Pass system_prompt separately rather than combining it with prompt_text
            response = self.generate_response(
                prompt_text=prompt_text,
                model=model,
                max_tokens=max_tokens,
                temperature=actual_temperature,
                system_prompt=system_prompt,  # Properly pass system_prompt as a separate parameter
            )

            if not response["success"]:
                return {
                    "success": False,
                    "error": response.get("error", "Unknown error"),
                    "content": None,
                    "thinking": None,
                    "provider": "gemini",
                }

            # Don't try to extract thinking - use the entire response as both content and thinking
            content = response["content"]
            
            # Construct the result
            result = {
                "success": True,
                "content": content,
                "thinking": content,  # Same content for both
                "usage": response.get("usage", {}),
                "model": model,
                "provider": "gemini",
            }

            return result

        except Exception as e:
            logging.error(f"Error with Gemini extended thinking: {str(e)}")
            return {
                "success": False,
                "error": f"Error with Gemini thinking: {str(e)}",
                "content": None,
                "thinking": None,
                "provider": "gemini",
            }

    def count_tokens(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
        text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Count tokens in a message or text.

        Note: Gemini doesn't provide a token counting API, so this uses an estimation.

        Args:
            messages: List of messages to count tokens for
            text: Plain text to count tokens for (used if messages is None)

        Returns:
            Dictionary with token count information
        """
        if not self.is_initialized:
            return {
                "success": False,
                "error": "Gemini client not initialized",
            }

        try:
            # Extract text content to estimate
            content_to_count = ""

            if text is not None:
                content_to_count = text
            elif messages is not None:
                # Try to extract text from messages
                for message in messages:
                    if isinstance(message.get("content"), str):
                        content_to_count += message.get("content", "") + " "
                    elif isinstance(message.get("content"), list):
                        for content_block in message.get("content", []):
                            if (
                                isinstance(content_block, dict)
                                and "text" in content_block
                            ):
                                content_to_count += content_block["text"] + " "
            else:
                return {
                    "success": False,
                    "error": "Either messages or text must be provided",
                }

            # Calculate estimated token count (very rough approximation)
            token_estimate = len(content_to_count) // 4

            return {
                "success": True,
                "token_count": token_estimate,
                "estimated": True,
            }

        except Exception as e:
            logging.error(f"Error estimating tokens: {str(e)}")
            return {"success": False, "error": f"Token estimation error: {str(e)}"}


# -----------------------
# LLM Client Factory
# -----------------------


class LLMClientFactory:
    """Factory to create appropriate LLM clients."""

    @staticmethod
    def create_client(
        provider: str = "auto",
        timeout: float = 600.0,
        max_retries: int = 2,
        thinking_budget_tokens: int = 16000,
        default_system_prompt: Optional[str] = None,
        api_key: Optional[str] = None,
        debug: bool = False,
    ) -> BaseLLMClient:
        """
        Create an LLM client for the specified provider.

        Args:
            provider: The LLM provider to use ("anthropic", "gemini", or "auto")
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for API requests
            thinking_budget_tokens: Budget for "thinking" tokens in extended thinking mode
            default_system_prompt: Default system prompt to use when none is provided
            api_key: Optional API key
            debug: Debug mode flag

        Returns:
            An initialized LLM client
        """
        # Auto-detect provider based on available API keys
        if provider == "auto":
            # Try Anthropic first
            client = AnthropicClient(
                timeout=timeout,
                max_retries=max_retries,
                thinking_budget_tokens=thinking_budget_tokens,
                default_system_prompt=default_system_prompt,
                api_key=api_key,
                debug=debug,
            )

            if client.is_initialized:
                logging.info("Automatically selected Anthropic provider")
                return client

            # Fall back to Gemini
            logging.info("Falling back to Gemini provider")
            return GeminiClient(
                timeout=timeout,
                max_retries=max_retries,
                thinking_budget_tokens=thinking_budget_tokens,
                default_system_prompt=default_system_prompt,
                api_key=api_key,
                debug=debug,
            )

        # Create client for specific provider
        if provider == "anthropic":
            return AnthropicClient(
                timeout=timeout,
                max_retries=max_retries,
                thinking_budget_tokens=thinking_budget_tokens,
                default_system_prompt=default_system_prompt,
                api_key=api_key,
                debug=debug,
            )
        elif provider == "gemini":
            return GeminiClient(
                timeout=timeout,
                max_retries=max_retries,
                thinking_budget_tokens=thinking_budget_tokens,
                default_system_prompt=default_system_prompt,
                api_key=api_key,
                debug=debug,
            )
        else:
            logging.error(f"Unknown provider: {provider}")
            raise ValueError(f"Unknown provider: {provider}")


# -----------------------
# Legacy Support for Backward Compatibility
# -----------------------


class LLMClient:
    """
    Legacy wrapper for LLM APIs to maintain backward compatibility.
    For new code, use LLMClientFactory to create provider-specific clients.
    """

    def __init__(
        self,
        timeout: float = 600.0,
        max_retries: int = 2,
        thinking_budget_tokens: int = 16000,
        default_system_prompt: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        google_api_key: Optional[str] = None,
        debug: bool = False,
    ):
        """Initialize the legacy LLM client wrapper."""
        logging.info(
            "Initializing legacy LLMClient - consider using LLMClientFactory for new code"
        )

        # Create clients for each provider
        self.anthropic_client = LLMClientFactory.create_client(
            provider="anthropic",
            timeout=timeout,
            max_retries=max_retries,
            thinking_budget_tokens=thinking_budget_tokens,
            default_system_prompt=default_system_prompt,
            api_key=anthropic_api_key,
            debug=debug,
        )

        self.gemini_client = LLMClientFactory.create_client(
            provider="gemini",
            timeout=timeout,
            max_retries=max_retries,
            thinking_budget_tokens=thinking_budget_tokens,
            default_system_prompt=default_system_prompt,
            api_key=google_api_key,
            debug=debug,
        )

        # Set other instance variables for legacy support
        self.timeout = timeout
        self.max_retries = max_retries
        self.thinking_budget_tokens = thinking_budget_tokens
        self.default_system_prompt = self.anthropic_client.default_system_prompt
        self.debug = debug

    def _load_env_vars(self):
        """Load environment variables from .env file."""
        # Legacy method kept for backward compatibility
        env_path = Path(".") / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            # Try to use template if .env doesn't exist
            template_path = Path(".") / "config.template.env"
            if template_path.exists():
                load_dotenv(template_path)

    def _get_client(self):
        """Legacy method to maintain backward compatibility."""
        if isinstance(self.anthropic_client, AnthropicClient) and hasattr(
            self.anthropic_client, "client"
        ):
            return self.anthropic_client.client
        return None

    def _init_gemini_client(self, google_api_key: Optional[str] = None) -> bool:
        """Legacy method to maintain backward compatibility."""
        if google_api_key:
            self.gemini_client = LLMClientFactory.create_client(
                provider="gemini",
                api_key=google_api_key,
            )
        return self.gemini_initialized

    @property
    def anthropic_initialized(self):
        """Check if Anthropic client is initialized."""
        return (
            isinstance(self.anthropic_client, AnthropicClient)
            and self.anthropic_client.is_initialized
        )

    @property
    def gemini_initialized(self):
        """Check if Gemini client is initialized."""
        return (
            isinstance(self.gemini_client, GeminiClient)
            and self.gemini_client.is_initialized
        )

    def generate_response(
        self,
        prompt_text: str,
        model: str = "claude-3-7-sonnet-20250219",
        max_tokens: int = 32000,
        temperature: float = 0.0,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a response, preferring Anthropic if available."""
        if self.anthropic_initialized:
            return self.anthropic_client.generate_response(
                prompt_text=prompt_text,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
            )
        elif self.gemini_initialized:
            return self.gemini_client.generate_response(
                prompt_text=prompt_text,
                model="models/gemini-2.5-pro-preview-03-25",  # Override model for Gemini
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
            )
        else:
            return {
                "success": False,
                "error": "No LLM clients initialized",
                "content": None,
            }

    def generate_response_with_pdf(
        self,
        prompt_text: str,
        pdf_file_path: str,
        model: str = "claude-3-7-sonnet-20250219",
        max_tokens: int = 32000,
        temperature: float = 0.0,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a response with PDF, requires Anthropic."""
        if self.anthropic_initialized:
            return self.anthropic_client.generate_response_with_pdf(
                prompt_text=prompt_text,
                pdf_file_path=pdf_file_path,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
            )
        else:
            return {
                "success": False,
                "error": "Anthropic client not initialized - required for PDF processing",
                "content": None,
            }

    def generate_response_with_extended_thinking(
        self,
        prompt_text: str,
        model: str = "claude-3-7-sonnet-20250219",
        max_tokens: int = 32000,
        temperature: float = 1.0,
        system_prompt: Optional[str] = None,
        thinking_budget_tokens: int = 16000,
    ) -> Dict[str, Any]:
        """Generate a response with extended thinking, requires Anthropic."""
        if self.anthropic_initialized:
            return self.anthropic_client.generate_response_with_extended_thinking(
                prompt_text=prompt_text,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
                thinking_budget_tokens=thinking_budget_tokens,
            )
        else:
            return {
                "success": False,
                "error": "Anthropic client not initialized - required for extended thinking",
                "content": None,
                "thinking": None,
            }

    def generate_response_with_gemini(
        self,
        prompt_text: str,
        model: str = "models/gemini-2.5-pro-preview-03-25",
        max_output_tokens: int = 32000,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a response with Gemini."""
        if self.gemini_initialized:
            return self.gemini_client.generate_response(
                prompt_text=prompt_text,
                model=model,
                max_tokens=max_output_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
            )
        else:
            return {
                "success": False,
                "error": "Gemini client not initialized",
                "content": None,
            }

    def count_tokens(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
        text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Count tokens, preferring Anthropic if available."""
        if self.anthropic_initialized:
            return self.anthropic_client.count_tokens(messages=messages, text=text)
        elif self.gemini_initialized:
            return self.gemini_client.count_tokens(messages=messages, text=text)
        else:
            return {
                "success": False,
                "error": "No LLM clients initialized",
            }

    def generate_response_with_gemini_thinking(
        self,
        prompt_text: str,
        model: str = "models/gemini-2.5-pro-preview-03-25",
        max_output_tokens: int = 200000,  # Increased from 32000 to leverage 2M token context window
        temperature: float = 0.3,
        system_prompt: Optional[str] = None,
        thinking_budget_tokens: int = 16000,
    ) -> Dict[str, Any]:
        """Generate a response using Gemini with step-by-step thinking capability.

        This leverages Gemini's 2M token context window and instructs it to think step-by-step.

        Args:
            prompt_text: The prompt to send
            model: The Gemini model to use
            max_output_tokens: Maximum tokens in response (increased to 200k for large responses)
            temperature: Temperature parameter (0.3 default for better reasoning)
            system_prompt: Optional system prompt
            thinking_budget_tokens: Not directly used by Gemini but kept for API compatibility

        Returns:
            Dictionary with response information including thinking and final answer
        """
        if self.gemini_initialized:
            return self.gemini_client.generate_response_with_extended_thinking(
                prompt_text=prompt_text,
                model=model,
                max_tokens=max_output_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
                thinking_budget_tokens=thinking_budget_tokens,
            )
        else:
            return {
                "success": False,
                "error": "Gemini client not initialized - required for Gemini thinking",
                "content": None,
                "thinking": None,
            }


# -----------------------
# Utility Functions
# -----------------------


def combine_transcript_with_fragments(transcript_text: str, fragment: str) -> str:
    """
    Combine transcript text with a template fragment.

    Args:
        transcript_text: The transcript text to combine with the fragment
        fragment: Template fragment as a string

    Returns:
        Combined prompt as a string
    """
    # Add the fragment first, then the transcript with proper wrapping
    combined = f"{fragment}\n\n<transcript>\n{transcript_text}\n</transcript>"
    return combined
