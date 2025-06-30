"""
LLM provider system for Forensic Psych Report Drafter.

This package provides a clean, modular interface for working with various LLM providers
(Anthropic, Google Gemini, Azure OpenAI) following Qt/PySide6 patterns.
"""

from .base import BaseLLMProvider
from .chunking import ChunkingStrategy
from .tokens import TokenCounter, MODEL_CONTEXT_WINDOWS
from .factory import create_provider, get_available_providers

__all__ = [
    'BaseLLMProvider',
    'ChunkingStrategy',
    'TokenCounter',
    'MODEL_CONTEXT_WINDOWS',
    'create_provider',
    'get_available_providers',
]

# Version info
__version__ = '1.0.0'