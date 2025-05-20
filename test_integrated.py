#!/usr/bin/env python
"""
Test script for integrated analysis thread
"""

import logging
import sys

from llm_utils import GeminiClient, LLMClientFactory

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

def test_gemini_client():
    """Test that the Gemini client can be initialized and used with the new model."""
    logging.info("Testing Gemini client...")
    
    # Create a Gemini client
    client = LLMClientFactory.create_client(provider="gemini")
    
    if client.is_initialized:
        logging.info("✅ Gemini client initialized successfully")
        
        # Test a simple response
        try:
            response = client.generate_response(
                prompt_text="What is the capital of France?",
                model="gemini-2.5-pro-preview-05-06",
                temperature=0.1,
            )
            
            if response["success"]:
                logging.info(f"✅ Gemini response received: {response['content'][:100]}...")
                return True
            else:
                logging.error(f"❌ Gemini response failed: {response.get('error', 'Unknown error')}")
                return False
        except Exception as e:
            logging.error(f"❌ Error generating response: {str(e)}")
            return False
    else:
        logging.error("❌ Failed to initialize Gemini client")
        return False

def main():
    """Run tests and exit with appropriate status code."""
    success = test_gemini_client()
    if success:
        logging.info("🎉 All tests passed!")
        return 0
    else:
        logging.error("❌ Tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 
