"""
Startup configuration to control logging and warnings.
"""

import logging
import warnings
import os


def configure_startup_logging():
    """Configure logging levels to reduce startup noise."""
    # Set default logging level to WARNING for all loggers
    logging.getLogger().setLevel(logging.WARNING)
    
    # Set specific loggers to appropriate levels
    # Reduce noise from LLM factory
    logging.getLogger('llm.factory').setLevel(logging.WARNING)
    logging.getLogger('llm.providers').setLevel(logging.WARNING)
    logging.getLogger('llm.providers.anthropic').setLevel(logging.WARNING)
    logging.getLogger('llm.providers.gemini').setLevel(logging.WARNING)
    logging.getLogger('llm.providers.azure_openai').setLevel(logging.WARNING)
    
    # Keep app-level logging at INFO
    logging.getLogger('root').setLevel(logging.INFO)
    logging.getLogger('__main__').setLevel(logging.INFO)
    
    # Configure based on environment variable
    if os.environ.get('DEBUG_LLM', '').lower() == 'true':
        # Enable debug logging for LLM modules
        logging.getLogger('llm').setLevel(logging.DEBUG)
        logging.getLogger('llm.factory').setLevel(logging.DEBUG)
        logging.getLogger('llm.providers').setLevel(logging.DEBUG)


def suppress_startup_warnings():
    """Suppress deprecation warnings during startup."""
    # Filter deprecation warnings from compatibility module
    # No longer needed - llm_utils_compat has been removed
    warnings.filterwarnings('ignore', category=DeprecationWarning, module='__main__')
    
    # Filter Qt-related warnings
    warnings.filterwarnings('ignore', message='.*Qt.*')
    

def clean_startup():
    """Configure a clean startup experience."""
    configure_startup_logging()
    suppress_startup_warnings()