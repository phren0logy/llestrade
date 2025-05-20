"""
Test script for Gemini API integration.
"""

import logging
import os
import sys
from pathlib import Path

# Configure logging to console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Ensure we can import from the parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import our LLM utils
from llm_utils import GeminiClient, LLMClientFactory

# Test direct Google Generative AI import
try:
    import google.generativeai as genai
    logging.info("Successfully imported google.generativeai package directly")
except ImportError as e:
    logging.error(f"Error importing google.generativeai: {str(e)}")


def test_gemini_client():
    """Test the Gemini client initialization and basic response generation."""
    logging.info("Testing Gemini client initialization...")
    
    # Create a Gemini client directly
    gemini_client = LLMClientFactory.create_client(provider="gemini")
    
    if not gemini_client.is_initialized:
        logging.error("❌ Failed to initialize Gemini client")
        return False
    
    logging.info("✅ Gemini client initialized successfully")
    
    # Test a simple response
    logging.info("Testing Gemini response generation...")
    response = gemini_client.generate_response(
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

def test_auto_client_fallback():
    """Test the auto client selection with fallback to Gemini."""
    logging.info("Testing auto client selection capabilities...")
    
    # Get the original API key value
    original_anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    
    # First test with Anthropic key present
    try:
        if original_anthropic_key:
            logging.info("Testing auto client with Anthropic API key available...")
            auto_client = LLMClientFactory.create_client(provider="auto")
            
            # Check if Anthropic was selected
            from llm_utils import AnthropicClient
            if isinstance(auto_client, AnthropicClient) and auto_client.is_initialized:
                logging.info("✅ Auto client correctly selected Anthropic (primary option)")
                return True
    finally:
        pass
    
    # Now test fallback to Gemini by removing Anthropic key
    try:
        if original_anthropic_key:
            os.environ.pop("ANTHROPIC_API_KEY", None)
            logging.info("Testing fallback to Gemini (removed Anthropic key)...")
        
        auto_client = LLMClientFactory.create_client(provider="auto")
        
        if isinstance(auto_client, GeminiClient) and auto_client.is_initialized:
            logging.info("✅ Auto client selection correctly fell back to Gemini")
            
            # Test a response
            response = auto_client.generate_response(
                prompt_text="Tell me a short joke.",
                model="gemini-2.5-pro-preview-05-06",
                temperature=0.7,
            )
            
            if response["success"]:
                logging.info(f"✅ Auto client (Gemini) response: {response['content'][:100]}...")
                return True
            else:
                logging.error(f"❌ Auto client (Gemini) response failed: {response.get('error', 'Unknown error')}")
                return False
        else:
            logging.error("❌ Auto client selection did not fall back to Gemini correctly")
            return False
    finally:
        # Restore original API key
        if original_anthropic_key:
            os.environ["ANTHROPIC_API_KEY"] = original_anthropic_key

def main():
    """Run all tests."""
    logging.info("=== GEMINI API INTEGRATION TESTS ===")
    
    # Test direct Gemini client
    gemini_result = test_gemini_client()
    
    # Test auto client fallback
    auto_result = test_auto_client_fallback()
    
    # Report results
    if gemini_result and auto_result:
        logging.info("🎉 All tests passed!")
        return 0
    else:
        logging.error("❌ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 
