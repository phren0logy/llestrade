#!/usr/bin/env python
"""
Test script for API key detection and client initialization
"""

import logging
import os
import sys

from llm_utils import GeminiClient, LLMClientFactory

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

def test_api_keys():
    """Test API key detection for both providers."""
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    
    if gemini_key:
        masked_key = f"{gemini_key[:4]}...{gemini_key[-4:]}" if len(gemini_key) > 8 else "[too short]"
        logging.info(f"Found Gemini API key: {masked_key}")
    else:
        logging.error("No Gemini API key found")
        
    if anthropic_key:
        masked_key = f"{anthropic_key[:4]}...{anthropic_key[-4:]}" if len(anthropic_key) > 8 else "[too short]"
        logging.info(f"Found Anthropic API key: {masked_key}")
    else:
        logging.error("No Anthropic API key found")
    
    assert gemini_key is not None and anthropic_key is not None, "Both Gemini and Anthropic API keys must be available"

def test_direct_gemini_client():
    """Test direct creation of Gemini client."""
    logging.info("Creating Gemini client directly...")
    
    try:
        # Directly create Gemini client
        client = LLMClientFactory.create_client(provider="gemini")
        
        assert isinstance(client, GeminiClient), f"Expected GeminiClient, got {client.__class__.__name__}"
        logging.info("Created GeminiClient instance")
        
        assert client.is_initialized, "Gemini client should be initialized"
        logging.info("Gemini client initialized successfully")
        
        # Test simple request
        response = client.generate_response(
            prompt_text="What is the capital of France?",
            model="gemini-2.5-pro-preview-05-06",
            temperature=0.1
        )
        
        assert response["success"], f"Gemini response failed: {response.get('error', 'Unknown error')}"
        logging.info(f"Gemini response: {response['content'][:50]}...")
        
    except Exception as e:
        logging.error(f"Error creating Gemini client: {str(e)}")
        raise

def main():
    """Run all tests."""
    logging.info("Testing API key availability...")
    test_api_keys()
    
    logging.info("Testing direct Gemini client creation...")
    test_direct_gemini_client()
    
    logging.info("🎉 All tests passed!")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 
