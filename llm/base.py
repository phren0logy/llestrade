"""
Abstract base class for LLM providers following Qt/PySide6 patterns.
"""

import abc
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal, Property
from dotenv import load_dotenv

from .tokens import TokenCounter

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class BaseLLMProvider(QObject):
    """
    Abstract base class for LLM providers.
    
    Follows Qt patterns with signals and properties.
    """
    
    # Qt signals
    initialized_changed = Signal(bool)
    response_ready = Signal(dict)
    error_occurred = Signal(str)
    progress_updated = Signal(int, str)  # percent, message
    
    def __init__(
        self,
        timeout: float = 600.0,
        max_retries: int = 2,
        default_system_prompt: Optional[str] = None,
        debug: bool = False,
        parent: Optional[QObject] = None
    ):
        """
        Initialize the base LLM provider.
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for API requests
            default_system_prompt: Default system prompt to use when none is provided
            debug: Debug mode flag
            parent: Parent QObject
        """
        super().__init__(parent)
        
        self.timeout = timeout
        self.max_retries = max_retries
        self.debug = debug
        self._initialized = False
        
        # Set default system prompt
        if default_system_prompt is None:
            default_system_prompt = self._load_default_system_prompt()
        self.default_system_prompt = default_system_prompt
        
        # Load environment variables
        self._load_env_vars()
    
    def _load_default_system_prompt(self) -> str:
        """Load default system prompt from PromptManager or use fallback."""
        try:
            from src.core.prompt_manager import PromptManager
            prompt_manager = PromptManager()
            prompt = prompt_manager.get_system_prompt()
            if self.debug:
                logging.info("Loaded system prompt from PromptManager")
            return prompt
        except Exception as e:
            if self.debug:
                logging.warning(f"Could not load PromptManager: {e}")
            return (
                "You are an advanced assistant designed to help a forensic psychiatrist. "
                "Your task is to analyze and objectively document case information in a formal clinical style, "
                "maintaining professional psychiatric documentation standards. Distinguish between information "
                "from the subject and objective findings. Report specific details such as dates, frequencies, "
                "dosages, and other relevant clinical data. Document without emotional language or judgment."
            )
    
    def _load_env_vars(self):
        """Load environment variables from .env file."""
        env_path = Path(".") / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            # Try template if .env doesn't exist
            template_path = Path(".") / "config.template.env"
            if template_path.exists():
                load_dotenv(template_path)
    
    # Qt Property for initialized state
    def get_initialized(self) -> bool:
        """Get whether the provider is initialized."""
        return self._initialized
    
    def set_initialized(self, value: bool):
        """Set the initialized state."""
        if self._initialized != value:
            self._initialized = value
            self.initialized_changed.emit(value)
    
    initialized = Property(bool, get_initialized, notify=initialized_changed)
    
    @abc.abstractmethod
    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 32000,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from the LLM.
        
        Args:
            prompt: The user prompt
            model: The model to use (provider-specific)
            max_tokens: Maximum tokens in response
            temperature: Temperature parameter (0.0-1.0)
            system_prompt: System prompt for context
            
        Returns:
            Dict with 'success', 'content', 'usage', etc.
        """
        pass
    
    @abc.abstractmethod
    def count_tokens(
        self,
        text: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Count tokens in text or messages.
        
        Args:
            text: Plain text to count
            messages: List of message dicts to count
            
        Returns:
            Dict with 'success', 'token_count', etc.
        """
        pass
    
    @abc.abstractproperty
    def provider_name(self) -> str:
        """Return the provider name."""
        pass
    
    @abc.abstractproperty
    def default_model(self) -> str:
        """Return the default model for this provider."""
        pass
    
    def emit_progress(self, percent: int, message: str):
        """Emit a progress update."""
        self.progress_updated.emit(percent, message)
    
    def emit_error(self, error: str):
        """Emit an error."""
        self.error_occurred.emit(error)
        logging.error(f"{self.provider_name} error: {error}")
    
    def emit_response(self, response: Dict[str, Any]):
        """Emit a response."""
        self.response_ready.emit(response)