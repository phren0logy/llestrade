"""
Anthropic Claude provider implementation.
"""

import base64
import logging
import os
import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject

from ..base import BaseLLMProvider
from ..tokens import TokenCounter

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseLLMProvider):
    """Provider for Anthropic Claude API."""
    
    def __init__(
        self,
        timeout: float = 600.0,
        max_retries: int = 2,
        default_system_prompt: Optional[str] = None,
        api_key: Optional[str] = None,
        debug: bool = False,
        parent: Optional[QObject] = None
    ):
        """
        Initialize the Anthropic provider.
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
            default_system_prompt: Default system prompt
            api_key: Optional API key (uses ANTHROPIC_API_KEY env var if not provided)
            debug: Debug mode flag
            parent: Parent QObject
        """
        super().__init__(timeout, max_retries, default_system_prompt, debug, parent)
        
        self.client = None
        self._init_client(api_key)
    
    def _init_client(self, api_key: Optional[str] = None):
        """Initialize the Anthropic client."""
        try:
            import anthropic
            
            # Get API key
            if api_key:
                os.environ["ANTHROPIC_API_KEY"] = api_key
            
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("ANTHROPIC_API_KEY environment variable not set")
                self.emit_error("ANTHROPIC_API_KEY not configured")
                return
            
            # Check if it's the template value
            if api_key == "your_api_key_here":
                logger.error("ANTHROPIC_API_KEY is set to the template value")
                self.emit_error("ANTHROPIC_API_KEY not properly configured")
                return
            
            # Log first few chars for verification
            if len(api_key) > 8 and self.debug:
                logger.info(f"Using Anthropic API key: {api_key[:4]}...{api_key[-4:]}")
            
            self.client = anthropic.Anthropic(
                api_key=api_key,
                timeout=self.timeout,
                max_retries=self.max_retries,
                default_headers={"anthropic-version": "2023-06-01"},
            )
            
            # Test connection
            self._test_connection()
            
        except ImportError:
            logger.error("anthropic package not installed - please install with: pip install anthropic")
            self.emit_error("Anthropic package not installed")
        except Exception as e:
            logger.error(f"Error initializing Anthropic client: {str(e)}")
            self.emit_error(f"Failed to initialize Anthropic: {str(e)}")
            self.client = None
    
    def _test_connection(self):
        """Test the connection to Anthropic API."""
        try:
            if not self.client:
                return
            
            test_result = self.count_tokens(text="Test connection")
            if not test_result["success"]:
                logger.error(f"Anthropic connection test failed: {test_result.get('error')}")
                self.client = None
                self.set_initialized(False)
            else:
                logger.info("Anthropic client initialized and tested successfully")
                self.set_initialized(True)
        except Exception as e:
            logger.error(f"Anthropic connection test failed: {str(e)}")
            self.client = None
            self.set_initialized(False)
    
    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "anthropic"
    
    @property
    def default_model(self) -> str:
        """Return the default model."""
        return "claude-sonnet-4-20250514"
    
    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 32000,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a response from Claude."""
        if not self.initialized:
            return {"success": False, "error": "Anthropic client not initialized"}
        
        try:
            # Use default model if not specified
            if not model:
                model = self.default_model
            
            # Use default system prompt if not provided
            if not system_prompt:
                system_prompt = self.default_system_prompt
            
            # Set options
            options = {
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system_prompt,
            }
            
            # Log request details
            if self.debug:
                logger.debug(f"Anthropic API Request - Model: {model}")
                logger.debug(f"Anthropic API Request - Prompt length: {len(prompt)}")
                logger.debug(f"Anthropic API Request - Temperature: {temperature}")
            
            # Emit progress
            self.emit_progress(10, "Sending request to Anthropic...")
            
            # Time the API call
            start_time = time.time()
            
            # Make the API call
            message = self.client.messages.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                **options,
            )
            
            # Extract response
            content = message.content[0].text
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            if self.debug:
                logger.debug(f"Anthropic API Response received in {elapsed_time:.2f} seconds")
            
            # Get token usage
            usage = {}
            if hasattr(message, "usage"):
                usage = {
                    "input_tokens": message.usage.input_tokens,
                    "output_tokens": message.usage.output_tokens,
                }
            
            self.emit_progress(100, "Response received")
            
            result = {
                "success": True,
                "content": content,
                "usage": usage,
                "provider": self.provider_name,
                "model": model,
            }
            
            self.emit_response(result)
            return result
            
        except Exception as e:
            # Handle specific API errors
            error_message = str(e)
            
            if "rate limit" in error_message.lower():
                error_message = f"Rate limit exceeded: {error_message}"
            elif "authentication" in error_message.lower():
                error_message = f"Authentication error: {error_message}"
            
            logger.error(f"Anthropic API Error: {error_message}")
            self.emit_error(error_message)
            
            return {
                "success": False,
                "error": error_message,
                "provider": self.provider_name,
            }
    
    def count_tokens(
        self,
        text: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Count tokens using Anthropic's API."""
        if not self.initialized:
            return {
                "success": False,
                "error": "Anthropic client not initialized",
            }
        
        try:
            # Convert to messages format if text provided
            if messages is None and text is not None:
                messages = [{"role": "user", "content": text}]
            elif messages is None and text is None:
                return {
                    "success": False,
                    "error": "Either messages or text must be provided",
                }
            
            # Use Anthropic's token counting
            response = self.client.messages.count_tokens(
                model=self.default_model,
                messages=messages
            )
            
            # Extract token count
            if hasattr(response, "input_tokens"):
                return {"success": True, "token_count": response.input_tokens}
            else:
                # Fallback to TokenCounter
                return TokenCounter.count(
                    text=text,
                    messages=messages,
                    provider=self.provider_name
                )
                
        except Exception as e:
            logger.error(f"Token counting error: {str(e)}")
            # Fallback to estimation
            return TokenCounter.count(
                text=text,
                messages=messages,
                provider=self.provider_name
            )
    
    def generate_with_pdf(
        self,
        prompt: str,
        pdf_file_path: str,
        model: Optional[str] = None,
        max_tokens: int = 32000,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a response for a PDF file."""
        if not self.initialized:
            return {
                "success": False,
                "error": "Anthropic client not initialized",
            }
        
        try:
            # Verify PDF exists
            if not os.path.exists(pdf_file_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_file_path}")
            
            # Read PDF file
            with open(pdf_file_path, "rb") as f:
                pdf_data = f.read()
            
            # Use default model if not specified
            if not model:
                model = self.default_model
            
            # Use default system prompt if not provided
            if not system_prompt:
                system_prompt = self.default_system_prompt
            
            # Prepare message with PDF
            message_params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
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
            
            self.emit_progress(10, "Sending PDF to Anthropic...")
            
            # Create message
            response = self.client.messages.create(**message_params)
            
            # Extract content
            content = ""
            for block in response.content:
                if block.type == "text" and hasattr(block, "text"):
                    content += block.text
            
            # Get usage
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
            
            self.emit_progress(100, "PDF processed")
            
            result = {
                "success": True,
                "content": content,
                "usage": usage,
                "model": model,
                "provider": self.provider_name,
            }
            
            self.emit_response(result)
            return result
            
        except Exception as e:
            logger.error(f"Error with PDF processing: {str(e)}")
            self.emit_error(f"PDF processing error: {str(e)}")
            return {
                "success": False,
                "error": f"Error with PDF: {str(e)}",
                "provider": self.provider_name,
            }
    
    def generate_with_thinking(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 32000,
        temperature: float = 1.0,
        system_prompt: Optional[str] = None,
        thinking_budget: int = 16000,
    ) -> Dict[str, Any]:
        """Generate a response with extended thinking mode."""
        if not self.initialized:
            return {
                "success": False,
                "error": "Anthropic client not initialized",
            }
        
        try:
            # Use default model if not specified
            if not model:
                model = self.default_model
            
            # Use default system prompt if not provided
            if not system_prompt:
                system_prompt = self.default_system_prompt
            
            # Ensure thinking budget is less than max_tokens
            if thinking_budget >= max_tokens:
                thinking_budget = max_tokens - 1000
            
            # Prepare message with thinking enabled
            message_params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 1.0,  # Required for thinking
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": thinking_budget,
                },
                "system": system_prompt,
                "messages": [{"role": "user", "content": prompt}],
            }
            
            self.emit_progress(10, "Processing with extended thinking...")
            
            # Create message
            response = self.client.messages.create(**message_params)
            
            # Extract content and thinking
            content = ""
            thinking = ""
            
            for block in response.content:
                if block.type == "text" and hasattr(block, "text"):
                    content += block.text
                elif block.type == "thinking" and hasattr(block, "thinking"):
                    thinking += block.thinking
            
            # Get usage
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
            
            self.emit_progress(100, "Thinking complete")
            
            result = {
                "success": True,
                "content": content,
                "thinking": thinking,
                "usage": usage,
                "model": model,
                "provider": self.provider_name,
            }
            
            self.emit_response(result)
            return result
            
        except Exception as e:
            logger.error(f"Error with extended thinking: {str(e)}")
            self.emit_error(f"Extended thinking error: {str(e)}")
            return {
                "success": False,
                "error": f"Error with thinking: {str(e)}",
                "provider": self.provider_name,
            }