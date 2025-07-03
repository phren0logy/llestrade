"""
Token counting utilities for LLM providers.
"""

import logging
from functools import lru_cache
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

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

# Token counting cache
_TOKEN_COUNT_CACHE = {}
_MAX_CACHE_SIZE = 1000
_CACHE_STATS = {"hits": 0, "misses": 0}


class TokenCounter:
    """Unified token counting for all providers."""
    
    @staticmethod
    def get_model_context_window(model_name: str) -> int:
        """
        Get the safe context window size for a model.
        
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
        logger.warning(f"Unknown model '{model_name}', using default context window of 30,000 tokens")
        return 30_000
    
    @staticmethod
    def count(
        text: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        provider: str = "anthropic",
        model: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Count tokens for text or messages.
        
        Args:
            text: Plain text to count
            messages: List of message dicts to count
            provider: The LLM provider (for provider-specific counting)
            model: The specific model (for model-specific encoding)
            use_cache: Whether to use caching
            
        Returns:
            Dict with 'success', 'token_count', and optional 'estimated' flag
        """
        # Create cache key if caching is enabled
        cache_key = None
        if use_cache:
            if text is not None:
                cache_key = f"{provider}:text:{hash(text)}"
            elif messages is not None:
                msg_str = str(messages)
                cache_key = f"{provider}:messages:{hash(msg_str)}"
        
        # Check cache
        if cache_key and cache_key in _TOKEN_COUNT_CACHE:
            _CACHE_STATS["hits"] += 1
            # Move to end (LRU)
            result = _TOKEN_COUNT_CACHE.pop(cache_key)
            _TOKEN_COUNT_CACHE[cache_key] = result
            return result
        
        # Cache miss
        if use_cache:
            _CACHE_STATS["misses"] += 1
        
        # Provider-specific counting
        result = None
        
        if provider == "anthropic":
            result = TokenCounter._count_anthropic(text, messages)
        elif provider == "azure_openai":
            result = TokenCounter._count_openai(text, messages, model)
        elif provider == "gemini":
            result = TokenCounter._count_gemini(text, messages)
        else:
            # Default to character-based estimation
            result = TokenCounter._count_estimate(text, messages)
        
        # Cache successful results
        if use_cache and cache_key and result.get("success", False):
            # Manage cache size
            if len(_TOKEN_COUNT_CACHE) >= _MAX_CACHE_SIZE:
                # Remove oldest item
                oldest_key = next(iter(_TOKEN_COUNT_CACHE))
                _TOKEN_COUNT_CACHE.pop(oldest_key)
            
            _TOKEN_COUNT_CACHE[cache_key] = result
        
        return result
    
    @staticmethod
    def _count_anthropic(text: Optional[str], messages: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Count tokens for Anthropic models."""
        try:
            # For now, use estimation
            # In the future, we could use Anthropic's token counting API
            return TokenCounter._count_estimate(text, messages)
        except Exception as e:
            logger.error(f"Error counting Anthropic tokens: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _count_openai(
        text: Optional[str], 
        messages: Optional[List[Dict[str, Any]]],
        model: Optional[str]
    ) -> Dict[str, Any]:
        """Count tokens for OpenAI/Azure OpenAI models using tiktoken."""
        try:
            import tiktoken
            
            # Get encoding for the model
            encoding_name = "cl100k_base"  # Default for GPT-4 models
            encoding = tiktoken.get_encoding(encoding_name)
            
            num_tokens = 0
            
            if text is not None:
                num_tokens = len(encoding.encode(text))
            elif messages is not None:
                # Based on OpenAI's token counting cookbook
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
            return TokenCounter._count_estimate(text, messages)
        except Exception as e:
            logger.error(f"Error counting OpenAI tokens: {e}")
            return TokenCounter._count_estimate(text, messages)
    
    @staticmethod
    def _count_gemini(text: Optional[str], messages: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Count tokens for Gemini models."""
        # Gemini doesn't have a public token counting API
        # Use estimation
        return TokenCounter._count_estimate(text, messages)
    
    @staticmethod
    def _count_estimate(text: Optional[str], messages: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Estimate token count using character-based approximation."""
        try:
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
            
            # Rough estimate: 4 characters per token
            estimated_tokens = len(content_to_count) // 4
            
            return {
                "success": True,
                "token_count": estimated_tokens,
                "estimated": True
            }
            
        except Exception as e:
            logger.error(f"Error estimating tokens: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_cache_stats() -> Dict[str, int]:
        """Get token counting cache statistics."""
        return {
            "hits": _CACHE_STATS["hits"],
            "misses": _CACHE_STATS["misses"],
            "size": len(_TOKEN_COUNT_CACHE),
            "max_size": _MAX_CACHE_SIZE
        }
    
    @staticmethod
    def clear_cache():
        """Clear the token counting cache."""
        global _TOKEN_COUNT_CACHE
        _TOKEN_COUNT_CACHE = {}
        _CACHE_STATS["hits"] = 0
        _CACHE_STATS["misses"] = 0
        logger.info("Token counting cache cleared")


# Convenience function for backward compatibility
def count_tokens_cached(provider: Any, text: str) -> Dict[str, Any]:
    """
    Count tokens for text using the provider's model.
    
    This is a convenience wrapper for backward compatibility with the old API.
    
    Args:
        provider: The LLM provider instance
        text: The text to count tokens for
        
    Returns:
        Dict with 'success', 'token_count', and optional 'estimated' flag
    """
    # Extract provider type from the class name
    provider_type = "anthropic"  # Default
    if hasattr(provider, '__class__'):
        class_name = provider.__class__.__name__.lower()
        if 'gemini' in class_name:
            provider_type = "gemini"
        elif 'azure' in class_name or 'openai' in class_name:
            provider_type = "azure_openai"
    
    # Get model name if available
    model = None
    if hasattr(provider, 'model'):
        model = provider.model
    elif hasattr(provider, 'default_model'):
        model = provider.default_model
    
    return TokenCounter.count(
        text=text,
        provider=provider_type,
        model=model,
        use_cache=True
    )