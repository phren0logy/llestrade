#!/usr/bin/env python
"""
Test both Gemini and Anthropic clients working in the same script
"""

import logging
import os
import sys

from llm_utils import AnthropicClient, GeminiClient, LLMClientFactory

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

def test_both_clients():
    """Test initializing and using both Gemini and Anthropic clients."""
    
    # Initialize both clients directly
    logging.info("Initializing Anthropic client...")
    anthropic_client = LLMClientFactory.create_client(provider="anthropic")
    
    logging.info("Initializing Gemini client...")
    gemini_client = LLMClientFactory.create_client(provider="gemini")
    
    # Test if both clients initialized
    anthropic_working = isinstance(anthropic_client, AnthropicClient) and anthropic_client.is_initialized
    gemini_working = isinstance(gemini_client, GeminiClient) and gemini_client.is_initialized
    
    logging.info(f"Anthropic client initialized: {anthropic_working}")
    logging.info(f"Gemini client initialized: {gemini_working}")
    
    # Test request with both if possible
    success = True
    
    # Test Anthropic if available
    if anthropic_working:
        try:
            logging.info("Testing Anthropic response...")
            response = anthropic_client.generate_response(
                prompt_text="What is the capital of France?",
                model="claude-3-7-sonnet-20250219",
                temperature=0.1
            )
            
            if response["success"]:
                logging.info(f"Anthropic response: {response['content'][:50]}...")
            else:
                logging.error(f"Anthropic response failed: {response.get('error', 'Unknown error')}")
                success = False
        except Exception as e:
            logging.error(f"Error generating Anthropic response: {str(e)}")
            success = False
    
    # Test Gemini if available  
    if gemini_working:
        try:
            logging.info("Testing Gemini response...")
            response = gemini_client.generate_response(
                prompt_text="What is the capital of France?",
                model="gemini-2.5-pro-preview-05-06",
                temperature=0.1
            )
            
            if response["success"]:
                logging.info(f"Gemini response: {response['content'][:50]}...")
            else:
                logging.error(f"Gemini response failed: {response.get('error', 'Unknown error')}")
                success = False
        except Exception as e:
            logging.error(f"Error generating Gemini response: {str(e)}")
            success = False
    
    return success and (anthropic_working or gemini_working)

def main():
    """Run all tests."""
    success = test_both_clients()
    
    if success:
        logging.info("🎉 Tests passed!")
        return 0
    else:
        logging.error("❌ Tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 
