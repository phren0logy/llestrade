"""
Utility functions and classes for interacting with LLM providers.
Provides a structured approach to LLM connections and prompt management.
"""

import abc
import base64
import logging
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import openai  # Added for Azure OpenAI
import tiktoken  # Added for Azure OpenAI token counting
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Token counting cache to reduce redundant API calls
_TOKEN_COUNT_CACHE = {}
_MAX_CACHE_SIZE = 1000

# LRU cache for token counting - use a dictionary to track cache hits and misses
_LRU_CACHE_STATS = {"hits": 0, "misses": 0}

# Model context window sizes (in tokens)
# Using 65% of actual limits for safety margin
MODEL_CONTEXT_WINDOWS = {
    # Azure OpenAI
    "gpt-4.1": int(1_000_000 * 0.65),  # 650,000 tokens
    "gpt-4-turbo": int(128_000 * 0.65),  # 83,200 tokens
    "gpt-35-turbo": int(16_000 * 0.65),  # 10,400 tokens
    
    # Anthropic Claude
    "claude-sonnet-4-20250514": int(200_000 * 0.65),  # 130,000 tokens
    "claude-3-7-sonnet-latest": int(200_000 * 0.65),  # 130,000 tokens
    "claude-3-opus-20240229": int(200_000 * 0.65),  # 130,000 tokens
    "claude-3-haiku-20240307": int(200_000 * 0.65),  # 130,000 tokens
    
    # Google Gemini
    "gemini-2.5-pro-preview-05-06": int(2_000_000 * 0.65),  # 1,300,000 tokens
    "gemini-1.5-pro": int(2_000_000 * 0.65),  # 1,300,000 tokens
    "gemini-1.5-flash": int(1_000_000 * 0.65),  # 650,000 tokens
}

def get_model_context_window(model_name: str) -> int:
    """Get the safe context window size for a model.
    
    Args:
        model_name: The model identifier
        
    Returns:
        The safe context window size in tokens (65% of actual limit)
        Defaults to 30,000 tokens if model not found
    """
    # Check exact match first
    if model_name in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model_name]
    
    # Check for partial matches (e.g., if model name contains version info)
    for known_model, window_size in MODEL_CONTEXT_WINDOWS.items():
        if known_model in model_name or model_name in known_model:
            return window_size
    
    # Default conservative limit for unknown models
    logging.warning(f"Unknown model '{model_name}', using default context window of 30,000 tokens")
    return 30_000


def chunk_document_with_overlap(text, client=None, model_name=None, max_chunk_size=None, overlap=2000):
    """
    Chunk a document into overlapping pieces for processing by LLM.
    
    Args:
        text: The text to chunk
        client: LLM client for token counting (optional)
        model_name: Model name to determine chunk size (optional)
        max_chunk_size: Maximum tokens per chunk (overrides model-based sizing)
        overlap: Number of tokens to overlap between chunks
        
    Returns:
        List of text chunks
    """
    try:
        # Determine chunk size based on model if not explicitly provided
        if max_chunk_size is None:
            if model_name:
                max_chunk_size = get_model_context_window(model_name)
                # Reserve some space for prompts (use 90% of model window for content)
                max_chunk_size = int(max_chunk_size * 0.9)
            else:
                # Default to conservative size
                max_chunk_size = 60000
        
        # Try to count tokens accurately if client is provided
        if client:
            token_result = cached_count_tokens(client, text=text)
            if token_result["success"]:
                total_tokens = token_result["token_count"]
            else:
                # Fallback to character-based estimation
                total_tokens = len(text) // 4
        else:
            # No client provided, use character estimation
            total_tokens = len(text) // 4
            
        # If the document is small enough, return as single chunk
        if total_tokens <= max_chunk_size:
            return [text]
            
        # Calculate approximate characters per token
        chars_per_token = len(text) / total_tokens if total_tokens > 0 else 4
        
        # Convert token limits to character limits
        max_chars = int(max_chunk_size * chars_per_token)
        overlap_chars = int(overlap * chars_per_token)
        
        chunks = []
        start = 0
        
        while start < len(text):
            # Calculate end position
            end = min(start + max_chars, len(text))
            
            # Try to break at a sentence or paragraph boundary
            if end < len(text):
                # Look for sentence endings within the last 200 characters
                search_start = max(end - 200, start)
                sentence_breaks = []
                
                # Find sentence endings
                for i in range(search_start, end):
                    if text[i] in '.!?':
                        # Check if it's followed by whitespace and capital letter
                        if (i + 1 < len(text) and 
                            text[i + 1].isspace() and 
                            i + 2 < len(text) and 
                            text[i + 2].isupper()):
                            sentence_breaks.append(i + 1)
                
                # Use the last sentence break if available
                if sentence_breaks:
                    end = sentence_breaks[-1]
                
                # If no sentence breaks, try paragraph breaks
                elif '\n\n' in text[search_start:end]:
                    para_pos = text.rfind('\n\n', search_start, end)
                    if para_pos > start:
                        end = para_pos + 2
            
            # Extract the chunk
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move start position with overlap
            if end >= len(text):
                break
            start = max(end - overlap_chars, start + 1)
            
        return chunks if chunks else [text]
        
    except Exception as e:
        logging.error(f"Error chunking document: {e}")
        # Return the original text as a single chunk
        return [text]


def cached_count_tokens(client, text=None, messages=None):
    """
    Count tokens with caching to reduce redundant API calls.

    Args:
        client: LLM client instance with count_tokens method
        text: Text to count tokens for
        messages: Messages to count tokens for

    Returns:
        Token count result dictionary from the client
    """
    # Create a cache key based on content
    cache_key = None
    if text is not None:
        cache_key = f"text:{hash(text)}"
    elif messages is not None:
        # Convert messages to a stable string representation for hashing
        msg_str = str(messages)
        cache_key = f"messages:{hash(msg_str)}"

    # Return cached result if available
    if cache_key and cache_key in _TOKEN_COUNT_CACHE:
        _LRU_CACHE_STATS["hits"] += 1
        # Move this item to the end of the cache (most recently used)
        result = _TOKEN_COUNT_CACHE.pop(cache_key)
        _TOKEN_COUNT_CACHE[cache_key] = result
        return result

    # Cache miss
    _LRU_CACHE_STATS["misses"] += 1

    # Get fresh count if not in cache
    result = client.count_tokens(text=text, messages=messages)

    # Cache successful results
    if cache_key and result.get("success", False):
        # If cache is full, remove the oldest item (first in the dict)
        if len(_TOKEN_COUNT_CACHE) >= _MAX_CACHE_SIZE:
            # Remove the oldest item (first key)
            oldest_key = next(iter(_TOKEN_COUNT_CACHE))
            _TOKEN_COUNT_CACHE.pop(oldest_key)

        # Add new result to cache
        _TOKEN_COUNT_CACHE[cache_key] = result

    return result


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
            default_system_prompt: Default system prompt to use when none is provided.
                                 If None, will try to load from PromptManager.
            debug: Debug mode flag
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.thinking_budget_tokens = thinking_budget_tokens
        self.debug = debug

        # Try to import PromptManager for system prompt
        try:
            from prompt_manager import PromptManager

            prompt_manager = PromptManager()
            self.default_system_prompt = prompt_manager.get_system_prompt()
            if debug:
                logging.info("Loaded system prompt from PromptManager")
        except Exception as e:
            if debug:
                logging.warning(
                    f"Could not load PromptManager, using default system prompt: {e}"
                )
            # Fall back to provided or default prompt
            if default_system_prompt is not None:
                self.default_system_prompt = default_system_prompt
            else:
                self.default_system_prompt = (
                    "You are an advanced assistant designed to help a forensic psychiatrist. "
                    "Your task is to analyze and objectively document case information in a formal clinical style, "
                    "maintaining professional psychiatric documentation standards. Distinguish between information "
                    "from the subject and objective findings. Report specific details such as dates, frequencies, "
                    "dosages, and other relevant clinical data. Document without emotional language or judgment."
                )

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

    @abc.abstractproperty
    def provider(self) -> str:
        """Return the provider name for this client."""
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

    @property
    def provider(self) -> str:
        """Return the provider name for this client."""
        return "anthropic"

    def generate_response(
        self,
        prompt_text: str,
        model: str = "claude-3-7-sonnet-latest",
        max_tokens: int = 32000,
        temperature: float = 0.1,
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
        model: str = "claude-3-7-sonnet-latest",
        max_tokens: int = 32000,
        temperature: float = 0.1,
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
            thinking = ""  # Initialize thinking variable
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
            logging.error(f"Error with PDF processing: {str(e)}")
            return {
                "success": False,
                "error": f"Error with PDF: {str(e)}",
                "content": None,
            }

    def generate_response_with_extended_thinking(
        self,
        prompt_text: str,
        model: str = "claude-3-7-sonnet-latest",
        max_tokens: int = 32000,
        temperature: float = 1.0,  # required by Anthropic for thinking
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
                "temperature": 1.0,  # Required to be 1.0 for thinking
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

    def generate_response_with_pdf_and_thinking(
        self,
        prompt_text: str,
        pdf_file_path: str,
        model: str = "claude-3-7-sonnet-latest",
        max_tokens: int = 32000,
        temperature: float = 1.0,
        system_prompt: Optional[str] = None,
        thinking_budget_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate a response from Claude for a given prompt and PDF file with extended thinking enabled."""
        if not self.is_initialized:
            return {
                "success": False,
                "error": "Anthropic client not initialized - required for PDF extended thinking",
                "content": None,
                "thinking": None,
            }
        try:
            # Verify the PDF file exists
            if not os.path.exists(pdf_file_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_file_path}")

            # Read the PDF file
            with open(pdf_file_path, "rb") as f:
                pdf_data = f.read()

            # Use default thinking budget if not provided
            if thinking_budget_tokens is None:
                thinking_budget_tokens = self.thinking_budget_tokens
            # Ensure thinking budget is less than max_tokens
            if thinking_budget_tokens >= max_tokens:
                thinking_budget_tokens = max_tokens - 1000

            # Prepare message parameters with PDF and thinking enabled
            message_params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": thinking_budget_tokens,
                },
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
            if system_prompt is None:
                message_params["system"] = self.default_system_prompt
            else:
                message_params["system"] = system_prompt

            # Create the message
            response = self.client.messages.create(
                **message_params,
                timeout=self.timeout,
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

            if has_redacted_thinking:
                redacted_note = "\n\n[NOTE: Some thinking was flagged by safety systems and encrypted.]\n\n"
                if thinking:
                    thinking += redacted_note
                else:
                    thinking = redacted_note

            # Construct usage
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

            # Construct the result
            result = {
                "success": True,
                "content": content,
                "thinking": thinking,
                "usage": usage,
                "model": model,
                "provider": "anthropic",
            }
            return result

        except Exception as e:
            logging.error(f"Error with PDF extended thinking: {str(e)}")
            return {
                "success": False,
                "error": f"Error with PDF extended thinking: {str(e)}",
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
                    model="claude-3-7-sonnet-latest", messages=messages
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

        self.client = None
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

                self.genai = genai
                logging.info("Google GenerativeAI package imported successfully")
            except ImportError as ie:
                logging.error(
                    f"google-generativeai package import error: {str(ie)} - please install with: pip install google-generativeai"
                )
                return

            # Get API key
            if api_key:
                os.environ["GEMINI_API_KEY"] = api_key
                logging.info("Using provided API key for Gemini")

            # First try GEMINI_API_KEY, then fall back to GOOGLE_API_KEY
            gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not gemini_key:
                logging.error(
                    "GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set"
                )
                return

            # Log API key for debugging (only first/last few characters)
            if len(gemini_key) > 8:
                logging.info(
                    f"Using Gemini API key starting with: {gemini_key[:4]}...{gemini_key[-4:]}"
                )
            else:
                logging.warning("Gemini API key too short or invalid")

            # Configure the Gemini API
            logging.info("Configuring Google GenAI...")
            try:
                self.genai.configure(api_key=gemini_key)
                self.client = True  # Flag that configuration was successful
                logging.info("Google GenAI configured successfully")
            except Exception as client_error:
                logging.error(f"Error configuring Google GenAI: {str(client_error)}")
                self.client = None
                return

            # Store the default model name - use one of the available models from the list
            self.model_name = "gemini-2.5-pro-preview-05-06"

            # Test if the API is working by creating a model
            try:
                # Try creating a GenerativeModel object
                logging.info("Testing Gemini by creating a GenerativeModel...")
                model = self.genai.GenerativeModel(model_name=self.model_name)
                self.default_model = model
                logging.info(
                    f"Google Gemini initialized successfully with model: {self.model_name}"
                )

                # Also try listing models
                logging.info("Testing Gemini by listing available models...")
                models = list(self.genai.list_models())
                if models:
                    model_names = ", ".join([str(m.name) for m in models[:5]])
                    logging.info(f"Available Gemini models include: {model_names}")
            except Exception as e:
                logging.error(f"Error testing Gemini API: {str(e)}")
                self.client = None
                return

        except Exception as e:
            logging.error(f"Error initializing Gemini client: {str(e)}")
            self.client = None

    @property
    def is_initialized(self) -> bool:
        """Check if the client is properly initialized."""
        return self.client is not None

    @property
    def provider(self) -> str:
        """Return the provider name for this client."""
        return "gemini"

    def generate_response(
        self,
        prompt_text: str,
        model: str = "gemini-2.5-pro-preview-05-06",
        max_tokens: int = 200000,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Gemini for a given prompt.

        Args:
            prompt_text: The prompt to send to Gemini
            model: The Gemini model to use
            max_tokens: Maximum number of tokens in the response
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
            # Store the model name for other methods to use
            self.model_name = model

            # Log the request details
            logging.debug(f"Gemini API Request - Prompt length: {len(prompt_text)}")
            if system_prompt:
                logging.debug(
                    f"Gemini API Request - System prompt length: {len(system_prompt)}"
                )
            logging.debug(f"Gemini API Request - Temperature: {temperature}")
            logging.debug(f"Gemini API Request - Max tokens: {max_tokens}")

            # Time the API call
            start_time = time.time()

            try:
                # Create generation config
                generation_config = self.genai.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    top_p=0.95,
                    top_k=40,
                )

                # Get a GenerativeModel instance - use 'model_name' parameter
                gemini_model = self.genai.GenerativeModel(model_name=model)

                # Add system instruction if provided
                if system_prompt:
                    gemini_model = gemini_model.with_system_instruction(system_prompt)

                # Generate content
                response = gemini_model.generate_content(
                    prompt_text, generation_config=generation_config
                )

                # Calculate elapsed time
                elapsed_time = time.time() - start_time
                logging.debug(
                    f"Gemini API Response received in {elapsed_time:.2f} seconds"
                )

                # Extract the response text
                if hasattr(response, "text"):
                    content = response.text
                else:
                    return {
                        "success": False,
                        "error": "Invalid response format from Gemini API",
                        "provider": "gemini",
                    }

                # Gemini doesn't provide token usage information
                # Estimate based on chars
                char_count = len(prompt_text) + len(content)
                token_estimate = char_count // 4  # Rough estimate of chars to tokens

                usage = {
                    "input_tokens": len(prompt_text) // 4,  # Rough estimate
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
        model: str = "gemini-2.5-pro-preview-05-06",
        max_tokens: int = 200000,
        temperature: float = 0.2,
        system_prompt: Optional[str] = None,
        thinking_budget_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Gemini with structured reasoning and thinking.

        Since Gemini doesn't have a native "thinking" API like Claude, this implementation
        uses structured prompting to encourage detailed reasoning before answering.

        Args:
            prompt_text: The prompt to send to Gemini
            model: The Gemini model to use
            max_tokens: Maximum number of tokens in the response
            temperature: Temperature parameter (randomness)
            system_prompt: Optional system prompt to set context
            thinking_budget_tokens: Not used for Gemini but included for API compatibility

        Returns:
            Dictionary with response information including thinking and final answer
        """
        if not self.is_initialized:
            return {
                "success": False,
                "error": "Gemini client not initialized",
                "content": None,
                "thinking": None,
            }

        try:
            # Create a structured prompt that separates thinking from the final answer
            structured_prompt = ""
            if system_prompt:
                structured_prompt = f"System instructions: {system_prompt}\n\n"

            structured_prompt += (
                "I'd like you to solve this problem using detailed reasoning before providing your final answer.\n\n"
                "Please structure your response like this:\n"
                '1. First provide your detailed thinking and analysis under a section called "## Thinking"\n'
                '2. Then provide your final, organized answer under a section called "## Answer"\n\n'
                "Make sure to include BOTH sections clearly marked with these exact headings.\n"
                "Ensure your thinking is comprehensive and shows all steps of your analysis.\n\n"
                "Here's the question or task to solve:\n\n" + prompt_text
            )

            # Log the exact prompt format for debugging
            logging.debug(
                f"Structured prompt for Gemini (first 500 chars): {structured_prompt[:500]}..."
            )

            # Create a specific system prompt for reasoning if none provided
            reasoning_system_prompt = None
            if not system_prompt:
                reasoning_system_prompt = (
                    "You are an assistant that provides detailed step-by-step reasoning. "
                    "Always think through problems methodically before providing an answer. "
                    "Show all your work and explain your reasoning process clearly."
                )

            # Set temperature for optimal reasoning quality (0.5 is good balance for reasoning)
            actual_temperature = max(0.2, min(0.5, temperature))

            # Configure generation parameters
            generation_config = self.genai.GenerationConfig(
                temperature=actual_temperature,
                max_output_tokens=max_tokens,
                top_p=0.95,
                top_k=40,
            )

            # Explicitly log which model is being used
            logging.info(f"Using Gemini model: {model}")

            # Create a GenerativeModel and set the system instruction if supported
            try:
                gemini_model = self.genai.GenerativeModel(model_name=model)
                logging.info("Successfully created GenerativeModel instance")
            except Exception as model_error:
                logging.error(f"Error creating GenerativeModel: {str(model_error)}")
                raise

            # Try to set system instruction if supported
            try:
                if reasoning_system_prompt and hasattr(
                    gemini_model, "with_system_instruction"
                ):
                    logging.info("Applying system instruction to Gemini model")
                    gemini_model = gemini_model.with_system_instruction(
                        reasoning_system_prompt
                    )
            except Exception as system_error:
                # Log the error but continue without system instruction
                logging.warning(
                    f"Could not set system instruction: {str(system_error)} - continuing without it"
                )

            # Generate response with explicit timeout handling
            import time

            start_time = time.time()
            generation_timeout = 600  # Increased to 10 minutes

            try:
                logging.info("Sending request to Gemini API...")
                response = gemini_model.generate_content(
                    structured_prompt, generation_config=generation_config
                )
                elapsed = time.time() - start_time
                logging.info(f"Gemini API response received in {elapsed:.1f} seconds")
            except Exception as api_error:
                elapsed = time.time() - start_time
                logging.error(
                    f"Error from Gemini API after {elapsed:.1f} seconds: {str(api_error)}"
                )
                raise

            if not response or not hasattr(response, "text"):
                logging.error(
                    "Invalid or empty response from Gemini (missing text attribute)"
                )
                return {
                    "success": False,
                    "error": "Invalid or empty response from Gemini",
                    "content": None,
                    "thinking": None,
                    "provider": "gemini",
                }

            # Extract the full response text
            full_response = response.text
            logging.info(f"Received response of length {len(full_response)} chars")

            # Check if the response is empty (0 characters)
            if not full_response or len(full_response) == 0:
                logging.error("Empty response from Gemini API")
                return {
                    "success": False,
                    "error": "Empty response from Gemini API",
                    "content": None,
                    "thinking": None,
                    "provider": "gemini",
                }

            # Try to separate thinking from the final answer
            thinking_section = ""
            final_answer = ""

            # Look for the thinking and answer sections
            if "## Thinking" in full_response and "## Answer" in full_response:
                # Split by the section headers
                parts = full_response.split("## Thinking", 1)
                if len(parts) > 1:
                    thinking_content = "## Thinking" + parts[1].split("## Answer", 1)[0]
                    thinking_section = thinking_content.strip()

                    answer_parts = full_response.split("## Answer", 1)
                    if len(answer_parts) > 1:
                        final_answer = answer_parts[1].strip()
                logging.info("Successfully separated thinking and answer sections")
            else:
                # If no clear separation, use an approximation - first 80% as thinking, rest as answer
                logging.warning(
                    "No clear thinking/answer separation found, using approximation"
                )
                split_point = int(len(full_response) * 0.8)
                thinking_section = full_response[:split_point].strip()
                final_answer = full_response[split_point:].strip()

                # If we couldn't find a clear separation, use the full response as both
                if not thinking_section or not final_answer:
                    logging.warning(
                        "Fallback to using full response for both thinking and answer"
                    )
                    thinking_section = full_response
                    final_answer = full_response

            # Ensure at least minimal thinking section:
            if not thinking_section or len(thinking_section) < 100:
                logging.warning("Insufficient thinking section, using full response")
                thinking_section = f"## Thinking\n\n{full_response}"

            # Estimate token usage
            char_count = len(structured_prompt) + len(full_response)
            token_estimate = char_count // 4

            # Construct the result
            result = {
                "success": True,
                "content": final_answer,  # The final answer only
                "thinking": thinking_section,  # The thinking process
                "full_response": full_response,  # The entire response
                "usage": {
                    "input_tokens": len(structured_prompt) // 4,  # Very rough estimate
                    "output_tokens": len(full_response) // 4,  # Rough estimate
                },
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
                    if "content" in message:
                        content = message["content"]
                        if isinstance(content, str):
                            content_to_count += content + " "
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and "text" in item:
                                    content_to_count += item["text"] + " "
            else:
                return {
                    "success": False,
                    "error": "Either messages or text must be provided",
                }

            # Try to use the actual count_tokens API if available
            try:
                # Create a GenerativeModel to count tokens
                model = self.genai.GenerativeModel(model_name=self.model_name)
                count_result = model.count_tokens(content_to_count)

                if hasattr(count_result, "total_tokens"):
                    return {
                        "success": True,
                        "token_count": count_result.total_tokens,
                        "estimated": False,
                    }
            except Exception as token_error:
                logging.debug(
                    f"Token counting API error: {str(token_error)}, falling back to estimation"
                )

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
# Azure OpenAI Client
# -----------------------


class AzureOpenAIClient(BaseLLMClient):
    """Client for the Azure OpenAI API."""

    def __init__(
        self,
        timeout: float = 600.0,
        max_retries: int = 2,
        thinking_budget_tokens: int = 16000,  # Maintained for BaseLLMClient compatibility
        default_system_prompt: Optional[str] = None,
        api_key: Optional[str] = None,  # AZURE_OPENAI_API_KEY
        azure_endpoint: Optional[str] = None,  # AZURE_OPENAI_ENDPOINT
        api_version: Optional[str] = None,  # OPENAI_API_VERSION
        debug: bool = False,
    ):
        """
        Initialize the Azure OpenAI client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for API requests
            thinking_budget_tokens: Maintained for API compatibility, not directly used.
            default_system_prompt: Default system prompt to use when none is provided
            api_key: Optional Azure OpenAI API key
            azure_endpoint: Optional Azure OpenAI endpoint
            api_version: Optional Azure OpenAI API version
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
        self._init_client(api_key, azure_endpoint, api_version)

    def _init_client(
        self,
        api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
    ):
        """
        Initialize the Azure OpenAI client.

        Args:
            api_key: Optional Azure OpenAI API key
            azure_endpoint: Optional Azure OpenAI endpoint
            api_version: Optional Azure OpenAI API version
        """
        try:
            # API key
            current_api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
            if not current_api_key:
                logging.error("AZURE_OPENAI_API_KEY environment variable not set.")
                return
            if current_api_key == "your_azure_openai_api_key":
                logging.error("AZURE_OPENAI_API_KEY is set to the template value.")
                return

            # Endpoint
            current_azure_endpoint = azure_endpoint or os.getenv(
                "AZURE_OPENAI_ENDPOINT"
            )
            if not current_azure_endpoint:
                logging.error("AZURE_OPENAI_ENDPOINT environment variable not set.")
                return
            if current_azure_endpoint == "your_azure_openai_endpoint":
                logging.error("AZURE_OPENAI_ENDPOINT is set to the template value.")
                return

            # API Version
            current_api_version = api_version or os.getenv("OPENAI_API_VERSION")
            if not current_api_version:
                logging.error("OPENAI_API_VERSION environment variable not set.")
                return
            if current_api_version == "your_api_version":
                logging.error("OPENAI_API_VERSION is set to the template value.")
                return

            if len(current_api_key) > 8:
                logging.info(
                    f"Using Azure OpenAI API key starting with: {current_api_key[:4]}...{current_api_key[-4:]}"
                )
            logging.info(f"Using Azure OpenAI Endpoint: {current_azure_endpoint}")
            logging.info(f"Using Azure OpenAI API Version: {current_api_version}")

            self.client = openai.AzureOpenAI(
                api_key=current_api_key,
                azure_endpoint=current_azure_endpoint,
                api_version=current_api_version,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
            self._test_connection()

        except ImportError:
            logging.error(
                "openai package not installed - please install with: pip install openai"
            )
        except Exception as e:
            logging.error(f"Error initializing Azure OpenAI client: {str(e)}")
            self.client = None

    def _test_connection(self):
        """Test the connection to Azure OpenAI API."""
        if not self.client:
            return
        try:
            # A lightweight way to test could be to list models,
            # but for Azure, deployments are key.
            # Counting tokens for a test string is a safe way to check API key and endpoint.
            test_result = self.count_tokens(text="Test connection")
            if not test_result["success"]:
                logging.error(
                    f"Azure OpenAI connection test failed: {test_result.get('error')}"
                )
                self.client = None
            else:
                logging.info("Azure OpenAI client initialized and tested successfully.")
        except Exception as e:
            logging.error(
                f"Azure OpenAI connection test failed during count_tokens: {str(e)}"
            )
            self.client = None

    @property
    def is_initialized(self) -> bool:
        """Check if the client is properly initialized."""
        return self.client is not None

    @property
    def provider(self) -> str:
        """Return the provider name for this client."""
        return "azure_openai"

    def generate_response(
        self,
        prompt_text: str,
        model: str,  # This will be the Azure deployment name
        max_tokens: int = 4000,  # Typical default for many OpenAI models
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Azure OpenAI.

        Args:
            prompt_text: The user's prompt text
            model: The Azure OpenAI deployment name
            max_tokens: Maximum number of tokens to generate
            temperature: Temperature parameter for generation (0.0 to 2.0 for OpenAI)
            system_prompt: Optional system prompt for context

        Returns:
            A dictionary with the response content or error message
        """
        if not self.is_initialized:
            return {
                "success": False,
                "error": "Azure OpenAI client not initialized",
                "provider": "azure_openai",
            }

        actual_system_prompt = system_prompt or self.default_system_prompt

        messages = []
        if actual_system_prompt:
            messages.append({"role": "system", "content": actual_system_prompt})
        messages.append({"role": "user", "content": prompt_text})

        logging.debug(f"Azure OpenAI API Request - Deployment: {model}")
        logging.debug(
            f"Azure OpenAI API Request - System prompt length: {len(actual_system_prompt or '')}"
        )
        logging.debug(
            f"Azure OpenAI API Request - User prompt length: {len(prompt_text)}"
        )
        logging.debug(f"Azure OpenAI API Request - Temperature: {temperature}")
        logging.debug(f"Azure OpenAI API Request - Max tokens: {max_tokens}")

        start_time = time.time()
        try:
            completion = self.client.chat.completions.create(
                model=model,  # Deployment name for Azure
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            elapsed_time = time.time() - start_time
            logging.debug(
                f"Azure OpenAI API Response received in {elapsed_time:.2f} seconds"
            )

            content = (
                completion.choices[0].message.content if completion.choices else ""
            )

            usage = {}
            if completion.usage:
                usage = {
                    "input_tokens": completion.usage.prompt_tokens,
                    "output_tokens": completion.usage.completion_tokens,
                }
                logging.debug(
                    f"Azure OpenAI API Token usage - Input: {usage['input_tokens']}, Output: {usage['output_tokens']}"
                )
            else:  # Estimate if not provided
                input_tokens_est = self.count_tokens(messages=messages).get(
                    "token_count", 0
                )
                output_tokens_est = self.count_tokens(text=content).get(
                    "token_count", 0
                )
                usage = {
                    "input_tokens": input_tokens_est,
                    "output_tokens": output_tokens_est,
                }
                logging.debug(
                    f"Azure OpenAI API Estimated Token usage - Input: {usage['input_tokens']}, Output: {usage['output_tokens']}"
                )

            return {
                "success": True,
                "content": content,
                "usage": usage,
                "provider": "azure_openai",
            }
        except openai.APIAuthenticationError as e:
            error_message = f"Azure OpenAI Authentication Error: {str(e)}. Check your API key and endpoint."
            logging.error(error_message)
            return {
                "success": False,
                "error": error_message,
                "provider": "azure_openai",
            }
        except openai.RateLimitError as e:
            error_message = (
                f"Azure OpenAI Rate Limit Exceeded: {str(e)}. Try again later."
            )
            logging.error(error_message)
            return {
                "success": False,
                "error": error_message,
                "provider": "azure_openai",
            }
        except openai.NotFoundError as e:  # Often for incorrect deployment name
            error_message = f"Azure OpenAI Not Found Error (check deployment name '{model}'): {str(e)}"
            logging.error(error_message)
            return {
                "success": False,
                "error": error_message,
                "provider": "azure_openai",
            }
        except openai.APIConnectionError as e:
            error_message = f"Azure OpenAI API Connection Error: {str(e)}. Check network connectivity and endpoint."
            logging.error(error_message)
            return {
                "success": False,
                "error": error_message,
                "provider": "azure_openai",
            }
        except Exception as e:
            error_message = f"Azure OpenAI API Error: {str(e)}"
            logging.error(error_message)
            return {
                "success": False,
                "error": error_message,
                "provider": "azure_openai",
            }

    def count_tokens(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
        text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Count tokens using tiktoken for Azure OpenAI models.

        Args:
            messages: List of messages to count tokens for
            text: Plain text to count tokens for (used if messages is None)
            model_encoding: The tiktoken encoding to use.

        Returns:
            Dictionary with token count information
        """
        if (
            not self.is_initialized and not text and not messages
        ):  # Allow counting even if client fails but tiktoken is there
            # Check if tiktoken is available for counting even if client init failed
            return {
                "success": False,
                "error": "Azure OpenAI client not initialized.",
            }

        if text is None and messages is None:
            return {
                "success": False,
                "error": "Either messages or text must be provided",
            }

        try:
            # Import tiktoken if not already available
            try:
                import tiktoken as tk
            except ImportError:
                tk = None
                
            if tk is None:
                raise ImportError("tiktoken not available")
                
            encoding = tk.get_encoding("cl100k_base")
            num_tokens = 0

            if text is not None:
                num_tokens = len(encoding.encode(text))
            elif messages is not None:
                # Based on OpenAI's cookbook for counting tokens with tiktoken for chat models
                # Ref: https://github.com/openai/openai-cookbook/blob/main/examples/how_to_count_tokens_with_tiktoken.ipynb
                # This logic might need adjustment based on the specific Azure OpenAI model version.
                # For now, using a common approach.
                # Assumes gpt-3.5-turbo and gpt-4 like models.
                tokens_per_message = 3
                tokens_per_name = 1  # if there's a 'name' field in a message

                for message in messages:
                    num_tokens += tokens_per_message
                    for key, value in message.items():
                        if isinstance(value, str):
                            num_tokens += len(encoding.encode(value))
                        if key == "name":
                            num_tokens += tokens_per_name
                num_tokens += (
                    3  # every reply is primed with <|start|>assistant<|message|>
                )

            return {"success": True, "token_count": num_tokens}

        except ImportError:
            logging.error(
                "tiktoken package not installed - please install with: pip install tiktoken"
            )
            # Fallback to char estimation if tiktoken is missing
            content_to_estimate = text or ""
            if messages:
                content_to_estimate = " ".join(
                    m.get("content", "")
                    for m in messages
                    if isinstance(m.get("content"), str)
                )
            estimated_tokens = len(content_to_estimate) // 4
            return {
                "success": True,
                "token_count": estimated_tokens,
                "estimated": True,
                "warning": "tiktoken not found, using character-based estimation.",
            }
        except Exception as e:
            logging.error(f"Error counting tokens with tiktoken: {str(e)}")
            return {"success": False, "error": f"Token counting error: {str(e)}"}

    def generate_response_with_pdf(self, *args, **kwargs) -> Dict[str, Any]:
        """PDF processing is not implemented for Azure OpenAI client."""
        logging.warning(
            "generate_response_with_pdf is not implemented for AzureOpenAIClient."
        )
        return {
            "success": False,
            "error": "PDF processing is not implemented for Azure OpenAI client.",
            "provider": "azure_openai",
        }

    def generate_response_with_extended_thinking(
        self, *args, **kwargs
    ) -> Dict[str, Any]:
        """Extended thinking is not implemented for Azure OpenAI client."""
        logging.warning(
            "generate_response_with_extended_thinking is not implemented for AzureOpenAIClient."
        )
        return {
            "success": False,
            "error": "Extended thinking is not implemented for Azure OpenAI client.",
            "provider": "azure_openai",
        }

    def generate_response_with_pdf_and_thinking(
        self, *args, **kwargs
    ) -> Dict[str, Any]:
        """PDF and extended thinking is not implemented for Azure OpenAI client."""
        logging.warning(
            "generate_response_with_pdf_and_thinking is not implemented for AzureOpenAIClient."
        )
        return {
            "success": False,
            "error": "PDF and extended thinking is not implemented for Azure OpenAI client.",
            "provider": "azure_openai",
        }


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
        api_key: Optional[str] = None,  # Can be for Anthropic, Gemini, or Azure OpenAI
        azure_endpoint: Optional[str] = None,  # Specific to Azure OpenAI
        api_version: Optional[str] = None,  # Specific to Azure OpenAI
        debug: bool = False,
    ) -> BaseLLMClient:
        """
        Create an LLM client for the specified provider.

        Args:
            provider: The LLM provider to use ("anthropic", "gemini", "azure_openai", or "auto")
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for API requests
            thinking_budget_tokens: Budget for "thinking" tokens
            default_system_prompt: Default system prompt
            api_key: Optional API key (used by the selected provider)
            azure_endpoint: Azure OpenAI specific endpoint.
            api_version: Azure OpenAI specific API version.
            debug: Debug mode flag

        Returns:
            An initialized LLM client
        """
        # Auto-detect provider based on available API keys
        if provider == "auto":
            # Try Anthropic first
            logging.info("Auto-detection: Trying to initialize Anthropic client...")
            anthropic_client = AnthropicClient(
                timeout=timeout,
                max_retries=max_retries,
                thinking_budget_tokens=thinking_budget_tokens,
                default_system_prompt=default_system_prompt,
                api_key=api_key,  # Assumes api_key could be for Anthropic
                debug=debug,
            )
            if anthropic_client.is_initialized:
                logging.info("Automatically selected Anthropic provider.")
                return anthropic_client

            # Fall back to Gemini
            logging.info(
                "Anthropic client initialization failed or not selected. Auto-detection: Trying Gemini..."
            )
            gemini_client = GeminiClient(
                timeout=timeout,
                max_retries=max_retries,
                thinking_budget_tokens=thinking_budget_tokens,
                default_system_prompt=default_system_prompt,
                api_key=api_key,  # Assumes api_key could be for Gemini
                debug=debug,
            )
            if gemini_client.is_initialized:
                logging.info("Automatically selected Gemini provider.")
                return gemini_client

            # Fall back to Azure OpenAI
            logging.info(
                "Gemini client initialization failed or not selected. Auto-detection: Trying Azure OpenAI..."
            )
            azure_openai_client = AzureOpenAIClient(
                timeout=timeout,
                max_retries=max_retries,
                thinking_budget_tokens=thinking_budget_tokens,
                default_system_prompt=default_system_prompt,
                api_key=api_key,  # Assumes api_key could be for Azure OpenAI
                azure_endpoint=azure_endpoint,
                api_version=api_version,
                debug=debug,
            )
            if azure_openai_client.is_initialized:
                logging.info("Automatically selected Azure OpenAI provider.")
                return azure_openai_client

            logging.warning(
                "Auto-detection failed for all providers. Returning uninitialized Anthropic client as fallback."
            )
            return anthropic_client  # Fallback to uninitialized Anthropic

        # Create client for specific provider
        if provider == "anthropic":
            logging.info("Explicitly initializing Anthropic client...")
            return AnthropicClient(
                timeout=timeout,
                max_retries=max_retries,
                thinking_budget_tokens=thinking_budget_tokens,
                default_system_prompt=default_system_prompt,
                api_key=api_key,
                debug=debug,
            )
        elif provider == "gemini":
            logging.info("Explicitly initializing Gemini client...")
            return GeminiClient(
                timeout=timeout,
                max_retries=max_retries,
                thinking_budget_tokens=thinking_budget_tokens,
                default_system_prompt=default_system_prompt,
                api_key=api_key,
                debug=debug,
            )
        elif provider == "azure_openai":
            logging.info("Explicitly initializing Azure OpenAI client...")
            return AzureOpenAIClient(
                timeout=timeout,
                max_retries=max_retries,
                thinking_budget_tokens=thinking_budget_tokens,
                default_system_prompt=default_system_prompt,
                api_key=api_key,
                azure_endpoint=azure_endpoint,
                api_version=api_version,
                debug=debug,
            )
        else:
            logging.error(
                f"Unknown provider: {provider}. Supported: anthropic, gemini, azure_openai, auto."
            )
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
        google_api_key: Optional[str] = None,  # For Gemini
        azure_api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        azure_api_version: Optional[str] = None,
        debug: bool = False,
    ):
        """Initialize the legacy LLM client wrapper."""
        logging.info(
            "Initializing legacy LLMClient - consider using LLMClientFactory for new code"
        )

        # Try to get system prompt from PromptManager
        system_prompt_to_use = default_system_prompt
        if default_system_prompt is None:
            try:
                from prompt_manager import PromptManager

                prompt_manager = PromptManager()
                system_prompt_to_use = prompt_manager.get_system_prompt()
                if debug:
                    logging.info(
                        "Loaded system prompt from PromptManager for legacy client"
                    )
            except Exception as e:
                if debug:
                    logging.warning(
                        f"Could not load PromptManager for legacy client: {e}"
                    )

        # Create clients for each provider
        self.anthropic_client = LLMClientFactory.create_client(
            provider="anthropic",
            timeout=timeout,
            max_retries=max_retries,
            thinking_budget_tokens=thinking_budget_tokens,
            default_system_prompt=system_prompt_to_use,
            api_key=anthropic_api_key,
            debug=debug,
        )

        self.gemini_client = LLMClientFactory.create_client(
            provider="gemini",
            timeout=timeout,
            max_retries=max_retries,
            thinking_budget_tokens=thinking_budget_tokens,
            default_system_prompt=system_prompt_to_use,
            api_key=google_api_key,
            debug=debug,
        )

        self.azure_openai_client = LLMClientFactory.create_client(
            provider="azure_openai",
            timeout=timeout,
            max_retries=max_retries,
            thinking_budget_tokens=thinking_budget_tokens,
            default_system_prompt=system_prompt_to_use,
            api_key=azure_api_key,
            azure_endpoint=azure_endpoint,
            api_version=azure_api_version,
            debug=debug,
        )

        # Set other instance variables for legacy support
        self.timeout = timeout
        self.max_retries = max_retries
        self.thinking_budget_tokens = thinking_budget_tokens
        # Use the system prompt from the first initialized client or the provided one
        if self.anthropic_initialized:
            self.default_system_prompt = self.anthropic_client.default_system_prompt
        elif self.gemini_initialized:
            self.default_system_prompt = self.gemini_client.default_system_prompt
        elif self.azure_openai_initialized:
            self.default_system_prompt = self.azure_openai_client.default_system_prompt
        else:
            self.default_system_prompt = (
                system_prompt_to_use or "Default system prompt placeholder."
            )
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

    @property
    def azure_openai_initialized(self):
        """Check if Azure OpenAI client is initialized."""
        return (
            isinstance(self.azure_openai_client, AzureOpenAIClient)
            and self.azure_openai_client.is_initialized
        )

    def generate_response(
        self,
        prompt_text: str,
        model: str = "gemini-2.5-pro-preview-05-06",  # Default model, may need context
        max_tokens: int = 200000,  # General default, provider might override
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response, preferring Anthropic, then Gemini, then Azure OpenAI if available.
        The 'model' parameter should be appropriate for the client being used.
        """
        # Note: The `model` parameter needs to be suitable for the chosen client.
        # This legacy method doesn't easily know which client will be chosen if multiple are initialized.
        # Caller should ideally use the specific client or factory for better control.

        if self.anthropic_initialized:
            # Assuming 'model' is an Anthropic model if this branch is taken.
            # If 'model' is for Gemini/Azure, this call might fail or use a default Anthropic model.
            # For true multi-provider support with specific models, use the factory.
            anthropic_model = (
                model if "claude" in model.lower() else "claude-3-haiku-20240307"
            )  # A sensible default
            return self.anthropic_client.generate_response(
                prompt_text=prompt_text,
                model=anthropic_model,  # Use a model name suitable for Anthropic
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
            )
        elif self.gemini_initialized:
            gemini_model = (
                model if "gemini" in model.lower() else "gemini-1.5-flash"
            )  # A sensible default
            return self.gemini_client.generate_response(
                prompt_text=prompt_text,
                model=gemini_model,  # Use a model name suitable for Gemini
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
            )
        elif self.azure_openai_initialized:
            # For Azure, 'model' is the deployment name. This is highly context-specific.
            # The default 'model' arg "gemini-2.5-pro-preview-05-06" is not an Azure deployment.
            # This highlights a weakness in the legacy client's generic generate_response.
            # A better approach for the caller would be to provide a known Azure deployment name.
            # If 'model' is not an Azure deployment name, this call will likely fail.
            # We'll pass 'model' as is, assuming the caller knows it's for Azure.
            return self.azure_openai_client.generate_response(
                prompt_text=prompt_text,
                model=model,  # This MUST be an Azure deployment name
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
            )
        else:
            return {
                "success": False,
                "error": "No LLM clients initialized in legacy client",
                "content": None,
            }

    def generate_response_with_pdf(
        self,
        prompt_text: str,
        pdf_file_path: str,
        model: str = "gemini-2.5-pro-preview-05-06",
        max_tokens: int = 200000,
        temperature: float = 0.1,
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
        model: str = "gemini-2.5-pro-preview-05-06",
        max_tokens: int = 200000,
        temperature: float = 0.1,
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
        model: str = "gemini-2.5-pro-preview-05-06",
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
        """Count tokens, preferring Anthropic, then Gemini, then Azure OpenAI."""
        if self.anthropic_initialized:
            return self.anthropic_client.count_tokens(messages=messages, text=text)
        elif self.gemini_initialized:
            return self.gemini_client.count_tokens(messages=messages, text=text)
        elif self.azure_openai_initialized:
            return self.azure_openai_client.count_tokens(messages=messages, text=text)
        else:
            return {
                "success": False,
                "error": "No LLM clients initialized in legacy client",
            }

    def generate_response_with_gemini_thinking(
        self,
        prompt_text: str,
        model: str = "gemini-2.5-pro-preview-05-06",
        max_output_tokens: int = 200000,  # Increased from 32000 to leverage 2M token context window
        temperature: float = 0.2,
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
