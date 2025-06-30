"""
Compatibility shim for transitioning from llm_utils to the new llm package.

This module provides backward compatibility during the migration period.
It can be removed once all code has been updated to use the new llm package directly.
"""

import warnings
from typing import Any, Dict, List, Optional

# Import from new structure
from llm import (
    BaseLLMProvider,
    ChunkingStrategy,
    TokenCounter,
    MODEL_CONTEXT_WINDOWS,
    create_provider,
    get_available_providers,
)
from llm.providers import AnthropicProvider, GeminiProvider, AzureOpenAIProvider

# Re-export with old names for compatibility
BaseLLMClient = BaseLLMProvider
AnthropicClient = AnthropicProvider
GeminiClient = GeminiProvider
AzureOpenAIClient = AzureOpenAIProvider

# Compatibility functions
def get_model_context_window(model_name: str) -> int:
    """Compatibility wrapper."""
    warnings.warn(
        "get_model_context_window is deprecated. Use TokenCounter.get_model_context_window instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return TokenCounter.get_model_context_window(model_name)


def chunk_document_with_overlap(
    text: str,
    client=None,
    model_name: Optional[str] = None,
    max_chunk_size: Optional[int] = None,
    overlap: int = 2000
) -> List[str]:
    """Compatibility wrapper for chunk_document_with_overlap."""
    warnings.warn(
        "chunk_document_with_overlap is deprecated. Use ChunkingStrategy.markdown_headers or .simple_overlap instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Determine max tokens
    if max_chunk_size is None:
        if model_name:
            max_chunk_size = TokenCounter.get_model_context_window(model_name)
            # Reserve some space for prompts (use 90% of model window for content)
            max_chunk_size = int(max_chunk_size * 0.9)
        else:
            max_chunk_size = 60000
    
    # Use simple overlap strategy for compatibility
    return ChunkingStrategy.simple_overlap(text, max_chunk_size, overlap)


def cached_count_tokens(client, text=None, messages=None) -> Dict[str, Any]:
    """Compatibility wrapper for cached_count_tokens."""
    warnings.warn(
        "cached_count_tokens is deprecated. Use TokenCounter.count instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Determine provider from client
    provider = "anthropic"  # Default
    if hasattr(client, "provider_name"):
        provider = client.provider_name
    elif hasattr(client, "provider"):
        provider = client.provider
    
    return TokenCounter.count(text=text, messages=messages, provider=provider)


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


class LLMClientFactory:
    """Compatibility wrapper for LLMClientFactory."""
    
    @staticmethod
    def create_client(**kwargs) -> Optional[BaseLLMProvider]:
        """Create client using new factory."""
        warnings.warn(
            "LLMClientFactory is deprecated. Use create_provider instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        # Map old kwargs to new
        if "provider" in kwargs:
            kwargs["provider"] = kwargs["provider"]
        if "thinking_budget_tokens" in kwargs:
            # Remove as it's not used in base init
            del kwargs["thinking_budget_tokens"]
            
        return create_provider(**kwargs)


# Legacy LLMClient wrapper
class LLMClient:
    """
    Legacy wrapper for backward compatibility.
    
    This class is deprecated and will be removed in a future version.
    Use create_provider() directly instead.
    """
    
    def __init__(self, **kwargs):
        """Initialize legacy client."""
        warnings.warn(
            "LLMClient is deprecated. Use create_provider() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        # Create providers
        self.anthropic_client = create_provider("anthropic", **kwargs)
        self.gemini_client = create_provider("gemini", **kwargs)
        self.azure_openai_client = create_provider("azure_openai", **kwargs)
        
        # Set attributes for compatibility
        self.timeout = kwargs.get("timeout", 600.0)
        self.max_retries = kwargs.get("max_retries", 2)
        self.debug = kwargs.get("debug", False)
        
        # Set default system prompt from first initialized client
        if self.anthropic_client and self.anthropic_client.initialized:
            self.default_system_prompt = self.anthropic_client.default_system_prompt
        elif self.gemini_client and self.gemini_client.initialized:
            self.default_system_prompt = self.gemini_client.default_system_prompt
        elif self.azure_openai_client and self.azure_openai_client.initialized:
            self.default_system_prompt = self.azure_openai_client.default_system_prompt
        else:
            self.default_system_prompt = "You are a helpful AI assistant."
    
    @property
    def anthropic_initialized(self):
        """Check if Anthropic is initialized."""
        return self.anthropic_client and self.anthropic_client.initialized
    
    @property
    def gemini_initialized(self):
        """Check if Gemini is initialized."""
        return self.gemini_client and self.gemini_client.initialized
    
    @property
    def azure_openai_initialized(self):
        """Check if Azure OpenAI is initialized."""
        return self.azure_openai_client and self.azure_openai_client.initialized
    
    def generate_response(self, **kwargs):
        """Generate response using first available provider."""
        if self.anthropic_initialized:
            return self.anthropic_client.generate(**kwargs)
        elif self.gemini_initialized:
            return self.gemini_client.generate(**kwargs)
        elif self.azure_openai_initialized:
            return self.azure_openai_client.generate(**kwargs)
        else:
            return {"success": False, "error": "No LLM providers initialized"}
    
    def count_tokens(self, **kwargs):
        """Count tokens using first available provider."""
        if self.anthropic_initialized:
            return self.anthropic_client.count_tokens(**kwargs)
        elif self.gemini_initialized:
            return self.gemini_client.count_tokens(**kwargs)
        elif self.azure_openai_initialized:
            return self.azure_openai_client.count_tokens(**kwargs)
        else:
            return {"success": False, "error": "No LLM providers initialized"}
    
    # Add other compatibility methods as needed...