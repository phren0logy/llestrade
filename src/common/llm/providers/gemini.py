"""
Google Gemini provider implementation.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject

from ..base import BaseLLMProvider
from ..tokens import TokenCounter

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Provider for Google Gemini API."""
    
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
        Initialize the Gemini provider.
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
            default_system_prompt: Default system prompt
            api_key: Optional API key (uses GEMINI_API_KEY env var if not provided)
            debug: Debug mode flag
            parent: Parent QObject
        """
        super().__init__(timeout, max_retries, default_system_prompt, debug, parent)
        
        self.client = None
        self.genai = None
        self.default_model_instance = None
        self._init_client(api_key)
    
    def _init_client(self, api_key: Optional[str] = None):
        """Initialize the Gemini client."""
        try:
            # Import Google GenerativeAI
            try:
                import google.generativeai as genai
                self.genai = genai
                logger.info("Google GenerativeAI package imported successfully")
            except ImportError as ie:
                logger.error(
                    f"google-generativeai package import error: {str(ie)} - "
                    "please install with: pip install google-generativeai"
                )
                self.emit_error("Google GenerativeAI package not installed")
                return
            
            # Get API key
            if api_key:
                os.environ["GEMINI_API_KEY"] = api_key
            
            # Try GEMINI_API_KEY first, then GOOGLE_API_KEY
            gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not gemini_key:
                try:
                    from src.app.core.secure_settings import SecureSettings

                    settings = SecureSettings()
                    gemini_key = settings.get_api_key("gemini")
                    if gemini_key:
                        os.environ["GEMINI_API_KEY"] = gemini_key
                        logger.info("Loaded Gemini API key from SecureSettings")
                except Exception as exc:  # pragma: no cover - defensive fallback
                    logger.debug(
                        "SecureSettings unavailable while loading Gemini key: %s",
                        exc,
                    )

            if not gemini_key:
                logger.error("GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set")
                self.emit_error("Gemini API key not configured")
                return
            
            # Log API key for debugging (only first/last few characters)
            if len(gemini_key) > 8 and self.debug:
                logger.info(f"Using Gemini API key: {gemini_key[:4]}...{gemini_key[-4:]}")
            
            # Configure the Gemini API
            logger.info("Configuring Google GenAI...")
            try:
                self.genai.configure(api_key=gemini_key)
                self.client = True  # Flag that configuration was successful
                logger.info("Google GenAI configured successfully")
            except Exception as e:
                logger.error(f"Error configuring Google GenAI: {str(e)}")
                self.emit_error(f"Failed to configure Gemini: {str(e)}")
                self.client = None
                return
            
            # Test the API by creating a model
            try:
                logger.info("Testing Gemini by creating a GenerativeModel...")
                model = self.genai.GenerativeModel(model_name=self.default_model)
                self.default_model_instance = model
                logger.info(f"Gemini initialized successfully with model: {self.default_model}")
                self.set_initialized(True)
            except Exception as e:
                logger.error(f"Error testing Gemini API: {str(e)}")
                self.emit_error(f"Failed to test Gemini API: {str(e)}")
                self.client = None
                self.set_initialized(False)
                
        except Exception as e:
            logger.error(f"Error initializing Gemini client: {str(e)}")
            self.emit_error(f"Failed to initialize Gemini: {str(e)}")
            self.client = None
            self.set_initialized(False)
    
    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "gemini"
    
    @property
    def default_model(self) -> str:
        """Return the default model."""
        return "gemini-2.5-pro-preview-05-06"
    
    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 200000,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a response from Gemini."""
        if not self.initialized:
            return {"success": False, "error": "Gemini client not initialized"}
        
        try:
            # Use default model if not specified
            if not model:
                model = self.default_model
            
            # Log request details
            if self.debug:
                logger.debug(f"Gemini API Request - Model: {model}")
                logger.debug(f"Gemini API Request - Prompt length: {len(prompt)}")
                logger.debug(f"Gemini API Request - Temperature: {temperature}")
                logger.debug(f"Gemini API Request - Max tokens: {max_tokens}")
            
            # Emit progress
            self.emit_progress(10, "Sending request to Gemini...")
            
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
                
                # Get a GenerativeModel instance
                gemini_model = self.genai.GenerativeModel(model_name=model)
                
                # Add system instruction if provided and supported
                if hasattr(gemini_model, "with_system_instruction"):
                    if system_prompt:
                        gemini_model = gemini_model.with_system_instruction(system_prompt)
                    elif self.default_system_prompt:
                        gemini_model = gemini_model.with_system_instruction(self.default_system_prompt)
                else:
                    # If with_system_instruction is not available, prepend system prompt to user prompt
                    if system_prompt:
                        prompt = f"{system_prompt}\n\n{prompt}"
                    elif self.default_system_prompt:
                        prompt = f"{self.default_system_prompt}\n\n{prompt}"
                
                # Generate content
                response = gemini_model.generate_content(
                    prompt, generation_config=generation_config
                )
                
                # Calculate elapsed time
                elapsed_time = time.time() - start_time
                if self.debug:
                    logger.debug(f"Gemini API Response received in {elapsed_time:.2f} seconds")
                
                # Extract the response text
                if hasattr(response, "text"):
                    content = response.text
                else:
                    return {
                        "success": False,
                        "error": "Invalid response format from Gemini API",
                        "provider": self.provider_name,
                    }
                
                # Estimate token usage (Gemini doesn't provide exact counts)
                usage = {
                    "input_tokens": len(prompt) // 4,  # Rough estimate
                    "output_tokens": len(content) // 4,  # Rough estimate
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
                logger.error(f"Error from Gemini API: {str(e)}")
                self.emit_error(f"Gemini API error: {str(e)}")
                return {
                    "success": False,
                    "error": f"Gemini API error: {str(e)}",
                    "provider": self.provider_name,
                }
                
        except Exception as e:
            logger.error(f"Error in Gemini request: {str(e)}")
            self.emit_error(f"Gemini request error: {str(e)}")
            return {
                "success": False,
                "error": f"Error in Gemini request: {str(e)}",
                "provider": self.provider_name,
            }
    
    def count_tokens(
        self,
        text: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Count tokens using Gemini's API if available."""
        if not self.initialized:
            return {
                "success": False,
                "error": "Gemini client not initialized",
            }
        
        try:
            # Extract text content to count
            content_to_count = ""
            
            if text is not None:
                content_to_count = text
            elif messages is not None:
                # Extract text from messages
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
            
            # Try to use actual count_tokens API if available
            try:
                model = self.genai.GenerativeModel(model_name=self.default_model)
                count_result = model.count_tokens(content_to_count)
                
                if hasattr(count_result, "total_tokens"):
                    return {
                        "success": True,
                        "token_count": count_result.total_tokens,
                        "estimated": False,
                    }
            except Exception as e:
                if self.debug:
                    logger.debug(f"Token counting API error: {str(e)}, falling back to estimation")
            
            # Fallback to TokenCounter
            return TokenCounter.count(
                text=text,
                messages=messages,
                provider=self.provider_name
            )
            
        except Exception as e:
            logger.error(f"Error counting tokens: {str(e)}")
            return {"success": False, "error": f"Token counting error: {str(e)}"}
    
    def generate_with_thinking(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 200000,
        temperature: float = 0.2,
        system_prompt: Optional[str] = None,
        thinking_budget: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response with structured reasoning.
        
        Since Gemini doesn't have native thinking mode, we use structured prompting.
        """
        if not self.initialized:
            return {
                "success": False,
                "error": "Gemini client not initialized",
            }
        
        try:
            # Create structured prompt for reasoning
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
                "Here's the question or task to solve:\n\n" + prompt
            )
            
            # Set temperature for reasoning
            actual_temperature = max(0.2, min(0.5, temperature))
            
            # Use default model if not specified
            if not model:
                model = self.default_model
            
            # Configure generation
            generation_config = self.genai.GenerationConfig(
                temperature=actual_temperature,
                max_output_tokens=max_tokens,
                top_p=0.95,
                top_k=40,
            )
            
            # Create model with reasoning prompt
            reasoning_system_prompt = (
                "You are an assistant that provides detailed step-by-step reasoning. "
                "Always think through problems methodically before providing an answer. "
                "Show all your work and explain your reasoning process clearly."
            )
            
            self.emit_progress(10, "Processing with structured reasoning...")
            
            # Create model and generate
            gemini_model = self.genai.GenerativeModel(model_name=model)
            if hasattr(gemini_model, "with_system_instruction"):
                gemini_model = gemini_model.with_system_instruction(reasoning_system_prompt)
            
            response = gemini_model.generate_content(
                structured_prompt, generation_config=generation_config
            )
            
            if not response or not hasattr(response, "text"):
                return {
                    "success": False,
                    "error": "Invalid or empty response from Gemini",
                    "provider": self.provider_name,
                }
            
            # Extract full response
            full_response = response.text
            
            # Try to separate thinking from answer
            thinking_section = ""
            final_answer = ""
            
            if "## Thinking" in full_response and "## Answer" in full_response:
                # Split by section headers
                parts = full_response.split("## Thinking", 1)
                if len(parts) > 1:
                    thinking_content = "## Thinking" + parts[1].split("## Answer", 1)[0]
                    thinking_section = thinking_content.strip()
                    
                    answer_parts = full_response.split("## Answer", 1)
                    if len(answer_parts) > 1:
                        final_answer = answer_parts[1].strip()
            else:
                # If no clear separation, use full response
                thinking_section = full_response
                final_answer = full_response
            
            # Estimate token usage
            usage = {
                "input_tokens": len(structured_prompt) // 4,
                "output_tokens": len(full_response) // 4,
            }
            
            self.emit_progress(100, "Reasoning complete")
            
            result = {
                "success": True,
                "content": final_answer,
                "thinking": thinking_section,
                "usage": usage,
                "model": model,
                "provider": self.provider_name,
            }
            
            self.emit_response(result)
            return result
            
        except Exception as e:
            logger.error(f"Error with Gemini structured reasoning: {str(e)}")
            self.emit_error(f"Reasoning error: {str(e)}")
            return {
                "success": False,
                "error": f"Error with reasoning: {str(e)}",
                "provider": self.provider_name,
            }
