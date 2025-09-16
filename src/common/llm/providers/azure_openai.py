"""
Azure OpenAI provider implementation.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

import openai
from PySide6.QtCore import QObject

from ..base import BaseLLMProvider
from ..tokens import TokenCounter
from src.config.observability import trace_llm_call

logger = logging.getLogger(__name__)


class AzureOpenAIProvider(BaseLLMProvider):
    """Provider for Azure OpenAI API."""
    
    def __init__(
        self,
        timeout: float = 600.0,
        max_retries: int = 2,
        default_system_prompt: Optional[str] = None,
        api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        debug: bool = False,
        parent: Optional[QObject] = None
    ):
        """
        Initialize the Azure OpenAI provider.
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
            default_system_prompt: Default system prompt
            api_key: Optional API key (uses AZURE_OPENAI_API_KEY env var if not provided)
            azure_endpoint: Optional endpoint (uses AZURE_OPENAI_ENDPOINT env var if not provided)
            api_version: Optional API version (uses OPENAI_API_VERSION env var if not provided)
            debug: Debug mode flag
            parent: Parent QObject
        """
        super().__init__(timeout, max_retries, default_system_prompt, debug, parent)
        
        self.client = None
        self._init_client(api_key, azure_endpoint, api_version)
        
        # Auto-instrument OpenAI calls with Phoenix if enabled
        if os.getenv("PHOENIX_ENABLED", "false").lower() == "true":
            try:
                from openinference.instrumentation.openai import OpenAIInstrumentor
                OpenAIInstrumentor().instrument()
                logger.info("Phoenix OpenAI instrumentation enabled")
            except Exception as e:
                logger.warning(f"Could not enable Phoenix instrumentation: {e}")
    
    def _init_client(
        self,
        api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
    ):
        """Initialize the Azure OpenAI client."""
        try:
            # Get API key
            current_api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
            if not current_api_key:
                logger.error("AZURE_OPENAI_API_KEY environment variable not set")
                self.emit_error("Azure OpenAI API key not configured")
                return
            
            if current_api_key == "your_azure_openai_api_key":
                logger.error("AZURE_OPENAI_API_KEY is set to the template value")
                self.emit_error("Azure OpenAI API key not properly configured")
                return
            
            # Get endpoint
            current_azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
            if not current_azure_endpoint:
                logger.error("AZURE_OPENAI_ENDPOINT environment variable not set")
                self.emit_error("Azure OpenAI endpoint not configured")
                return
            
            if current_azure_endpoint == "your_azure_openai_endpoint":
                logger.error("AZURE_OPENAI_ENDPOINT is set to the template value")
                self.emit_error("Azure OpenAI endpoint not properly configured")
                return
            
            # Get API version
            current_api_version = api_version or os.getenv("OPENAI_API_VERSION")
            if not current_api_version:
                logger.error("OPENAI_API_VERSION environment variable not set")
                self.emit_error("Azure OpenAI API version not configured")
                return
            
            if current_api_version == "your_api_version":
                logger.error("OPENAI_API_VERSION is set to the template value")
                self.emit_error("Azure OpenAI API version not properly configured")
                return
            
            # Log configuration (safely)
            if len(current_api_key) > 8 and self.debug:
                logger.info(f"Using Azure OpenAI API key: {current_api_key[:4]}...{current_api_key[-4:]}")
            logger.info(f"Using Azure OpenAI Endpoint: {current_azure_endpoint}")
            logger.info(f"Using Azure OpenAI API Version: {current_api_version}")
            
            # Create client
            self.client = openai.AzureOpenAI(
                api_key=current_api_key,
                azure_endpoint=current_azure_endpoint,
                api_version=current_api_version,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
            
            self._test_connection()
            
        except ImportError:
            logger.error("openai package not installed - please install with: pip install openai")
            self.emit_error("OpenAI package not installed")
        except Exception as e:
            logger.error(f"Error initializing Azure OpenAI client: {str(e)}")
            self.emit_error(f"Failed to initialize Azure OpenAI: {str(e)}")
            self.client = None
    
    def _test_connection(self):
        """Test the connection to Azure OpenAI API."""
        if not self.client:
            return
        
        try:
            # Test with token counting
            test_result = self.count_tokens(text="Test connection")
            if not test_result["success"]:
                logger.error(f"Azure OpenAI connection test failed: {test_result.get('error')}")
                self.client = None
                self.set_initialized(False)
            else:
                logger.info("Azure OpenAI client initialized and tested successfully")
                self.set_initialized(True)
        except Exception as e:
            logger.error(f"Azure OpenAI connection test failed: {str(e)}")
            self.client = None
            self.set_initialized(False)
    
    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "azure_openai"
    
    @property
    def default_model(self) -> str:
        """Return the default model (deployment name)."""
        # Get from environment variable
        return os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1")
    
    @trace_llm_call()
    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a response from Azure OpenAI."""
        if not self.initialized:
            return {"success": False, "error": "Azure OpenAI client not initialized"}
        
        try:
            # Use default deployment if not specified
            if not model:
                model = self.default_model
            
            # Use default system prompt if not provided
            actual_system_prompt = system_prompt or self.default_system_prompt
            
            # Prepare messages
            messages = []
            if actual_system_prompt:
                messages.append({"role": "system", "content": actual_system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            # Log request details
            total_tokens = self.count_tokens(messages=messages).get("token_count", 0)
            
            logger.info(f"Azure OpenAI API Request - Deployment: {model}, Total tokens: {total_tokens}")
            if self.debug:
                logger.debug(f"Azure OpenAI API Request - System prompt length: {len(actual_system_prompt or '')}")
                logger.debug(f"Azure OpenAI API Request - User prompt length: {len(prompt)}")
                logger.debug(f"Azure OpenAI API Request - Temperature: {temperature}")
                logger.debug(f"Azure OpenAI API Request - Max tokens: {max_tokens}")
                logger.debug(f"Azure OpenAI API Request - Endpoint: {self.azure_endpoint}")
                logger.debug(f"Azure OpenAI API Request - API Version: {self.api_version}")
            
            # Emit progress
            self.emit_progress(10, "Sending request to Azure OpenAI...")
            
            # Time the API call
            start_time = time.time()
            
            # Enhanced retry logic for API calls
            completion = None
            last_error = None
            retry_delay = 1.0  # Start with 1 second delay
            
            for attempt in range(self.max_retries + 1):
                try:
                    # Log retry attempt
                    if attempt > 0:
                        logger.info(f"Retry attempt {attempt}/{self.max_retries} for Azure OpenAI request")
                        self.emit_progress(10 + (attempt * 10), f"Retrying request (attempt {attempt + 1})...")
                    
                    # Make the API call
                    completion = self.client.chat.completions.create(
                        model=model,  # Deployment name for Azure
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=self.timeout,
                    )
                    
                    # Success - break out of retry loop
                    break
                    
                except (openai.APITimeoutError, openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError) as e:
                    last_error = e
                    logger.warning(
                        f"Retryable error on attempt {attempt + 1}/{self.max_retries + 1}: {type(e).__name__}: {str(e)}"
                    )
                    
                    if attempt < self.max_retries:
                        # Wait before retrying with exponential backoff
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        # Final attempt failed, re-raise
                        raise
                        
                except Exception as e:
                    # Non-retryable error, re-raise immediately
                    raise
            
            if completion is None and last_error:
                raise last_error
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            if self.debug:
                logger.debug(f"Azure OpenAI API Response received in {elapsed_time:.2f} seconds")
            
            # Extract content
            content = completion.choices[0].message.content if completion.choices else ""
            
            # Get token usage
            usage = {}
            if completion.usage:
                usage = {
                    "input_tokens": completion.usage.prompt_tokens,
                    "output_tokens": completion.usage.completion_tokens,
                }
            else:
                # Estimate if not provided
                usage = {
                    "input_tokens": self.count_tokens(messages=messages).get("token_count", 0),
                    "output_tokens": self.count_tokens(text=content).get("token_count", 0),
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
            
        except openai.APIAuthenticationError as e:
            error_message = f"Authentication error: {str(e)}"
            logger.error(f"Azure OpenAI {error_message}", extra={
                "deployment": model,
                "endpoint": self.azure_endpoint,
                "api_version": self.api_version
            })
            self.emit_error(error_message)
            return {"success": False, "error": error_message, "provider": self.provider_name}
            
        except openai.RateLimitError as e:
            error_message = f"Rate limit exceeded: {str(e)}"
            logger.error(f"Azure OpenAI {error_message}")
            self.emit_error(error_message)
            return {"success": False, "error": error_message, "provider": self.provider_name}
            
        except openai.NotFoundError as e:
            error_message = f"Deployment not found (check deployment name '{model}'): {str(e)}"
            logger.error(f"Azure OpenAI {error_message}", extra={
                "deployment": model,
                "endpoint": self.azure_endpoint,
                "api_version": self.api_version,
                "hint": "For GPT-4.1, ensure deployment name matches exactly (e.g., 'gpt-4.1' not 'gpt-41')"
            })
            self.emit_error(error_message)
            return {"success": False, "error": error_message, "provider": self.provider_name}
            
        except openai.APIConnectionError as e:
            error_message = f"Connection error: {str(e)}"
            logger.error(f"Azure OpenAI {error_message}")
            self.emit_error(error_message)
            return {"success": False, "error": error_message, "provider": self.provider_name}
            
        except Exception as e:
            error_message = f"API error: {str(e)}"
            logger.error(f"Azure OpenAI {error_message}", extra={
                "deployment": model,
                "endpoint": self.azure_endpoint,
                "api_version": self.api_version,
                "error_type": type(e).__name__,
                "total_tokens": total_tokens if 'total_tokens' in locals() else "unknown"
            }, exc_info=True)
            self.emit_error(error_message)
            return {"success": False, "error": error_message, "provider": self.provider_name}
    
    def count_tokens(
        self,
        text: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Count tokens using tiktoken for Azure OpenAI models."""
        if text is None and messages is None:
            return {
                "success": False,
                "error": "Either messages or text must be provided",
            }
        
        try:
            # Try to use tiktoken
            try:
                import tiktoken
                
                encoding = tiktoken.get_encoding("cl100k_base")
                num_tokens = 0
                
                if text is not None:
                    num_tokens = len(encoding.encode(text))
                elif messages is not None:
                    # Based on OpenAI's cookbook
                    tokens_per_message = 3
                    tokens_per_name = 1
                    
                    for message in messages:
                        num_tokens += tokens_per_message
                        for key, value in message.items():
                            if isinstance(value, str):
                                num_tokens += len(encoding.encode(value))
                            if key == "name":
                                num_tokens += tokens_per_name
                    
                    num_tokens += 3  # Every reply is primed with assistant
                
                return {"success": True, "token_count": num_tokens}
                
            except ImportError:
                logger.warning("tiktoken not available, using estimation")
                # Fallback to TokenCounter
                return TokenCounter.count(
                    text=text,
                    messages=messages,
                    provider=self.provider_name
                )
                
        except Exception as e:
            logger.error(f"Error counting tokens: {str(e)}")
            # Fallback to estimation
            return TokenCounter.count(
                text=text,
                messages=messages,
                provider=self.provider_name
            )
    
    # Azure OpenAI doesn't support PDF or extended thinking modes
    def generate_with_pdf(self, *args, **kwargs) -> Dict[str, Any]:
        """PDF processing is not supported by Azure OpenAI."""
        logger.warning("generate_with_pdf is not implemented for Azure OpenAI")
        return {
            "success": False,
            "error": "PDF processing is not supported by Azure OpenAI",
            "provider": self.provider_name,
        }
    
    def generate_with_thinking(self, *args, **kwargs) -> Dict[str, Any]:
        """Extended thinking is not supported by Azure OpenAI."""
        logger.warning("generate_with_thinking is not implemented for Azure OpenAI")
        return {
            "success": False,
            "error": "Extended thinking is not supported by Azure OpenAI",
            "provider": self.provider_name,
        }