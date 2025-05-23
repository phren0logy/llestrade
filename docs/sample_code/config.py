# File Location: lib/config.py
# Section: 3.1 Simplified Multi-Provider Configuration
# Description: Auto-discovery of available models with minimal configuration

import os
from typing import Dict, List, Optional

import litellm

# Note: Model identifiers are updated to reflect current model families:
# - Azure OpenAI: GPT-4.1 family (released April 2025)
# - Anthropic: Claude Sonnet 4 (released 2025)
# - Gemini: 2.5 Pro family (released March 2025)
# These identifiers will automatically resolve to the most recent
# available versions within each model family, ensuring the system
# uses current capabilities without requiring frequent configuration updates.

# Simple provider configuration
PROVIDER_CONFIG = {
    "azure": {
        "required_env": ["AZURE_API_KEY", "AZURE_API_BASE"],
        "models": []  # Will be auto-discovered
    },
    "anthropic": {
        "required_env": ["ANTHROPIC_API_KEY"],
        "models": []
    },
    "gemini": {
        "required_env": ["GOOGLE_API_KEY"],
        "models": []
    }
}

# Langfuse configuration
LANGFUSE_CONFIG = {
    "public_key": os.getenv("LANGFUSE_PUBLIC_KEY"),
    "secret_key": os.getenv("LANGFUSE_SECRET_KEY"),
    "host": os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
}

def check_provider_available(provider: str) -> bool:
    """Check if provider is configured"""
    required_env = PROVIDER_CONFIG[provider]["required_env"]
    return all(os.getenv(var) for var in required_env)

def discover_available_models() -> Dict[str, List[str]]:
    """Use LiteLLM to discover available models from each provider"""
    available_models = {}

    # Azure OpenAI
    if check_provider_available("azure"):
        try:
            # LiteLLM can fetch Azure deployment names
            azure_models = litellm.get_model_list(provider="azure")
            available_models["azure"] = [f"azure/{model}" for model in azure_models]
        except Exception:
            # Fallback to common Azure models
            available_models["azure"] = [
                "azure/gpt-4.1",                    # Most recent GPT model family
                "azure/gpt-4.1-mini",               # Most recent GPT mini model
                "azure/gpt-35-turbo"                # Legacy fallback
            ]

    # Anthropic
    if check_provider_available("anthropic"):
        try:
            anthropic_models = litellm.get_model_list(provider="anthropic")
            available_models["anthropic"] = [f"anthropic/{model}" for model in anthropic_models]
        except Exception:
            available_models["anthropic"] = [
                "anthropic/claude-sonnet-4-latest",  # Most recent Sonnet model
                "anthropic/claude-haiku-3.5-latest"  # Most recent Haiku model
            ]

    # Gemini
    if check_provider_available("gemini"):
        try:
            gemini_models = litellm.get_model_list(provider="gemini")
            available_models["gemini"] = [f"gemini/{model}" for model in gemini_models]
        except Exception:
            available_models["gemini"] = [
                "gemini/gemini-2.5-pro",            # Most recent Gemini Pro model
                "gemini/gemini-2.5-flash"           # Most recent Gemini Flash model
            ]

    return available_models

def get_all_available_models() -> List[str]:
    """Get flat list of all available models"""
    models_by_provider = discover_available_models()
    all_models = []
    for provider_models in models_by_provider.values():
        all_models.extend(provider_models)
    return all_models

def get_recommended_model() -> Optional[str]:
    """Get recommended primary model based on availability"""
    all_models = get_all_available_models()

    # Preference order for forensic applications
    preferences = [
        "azure/gpt-4.1",                     # Most recent Azure GPT model
        "anthropic/claude-sonnet-4-latest",   # Most recent Anthropic Sonnet model
        "gemini/gemini-2.5-pro",             # Most recent Gemini Pro model
        "azure/gpt-4.1-mini"                 # Most recent Azure GPT mini model
    ]

    for preferred in preferences:
        if preferred in all_models:
            return preferred

    return all_models[0] if all_models else None 
