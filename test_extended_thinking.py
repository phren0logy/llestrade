#!/usr/bin/env python
"""
Test script for Gemini extended thinking capabilities
"""

import logging
import sys

from llm_utils import GeminiClient, LLMClientFactory

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

def test_gemini_thinking():
    """Test that the Gemini client can use extended thinking."""
    logging.info("Testing Gemini extended thinking...")
    
    # Create a Gemini client
    client = LLMClientFactory.create_client(provider="gemini")
    
    if client.is_initialized:
        logging.info("✅ Gemini client initialized successfully")
        
        # Test extended thinking
        try:
            # Complex prompt that should trigger multi-step thinking
            complex_prompt = """
            Solve this step by step:
            
            If a train travels at 60 miles per hour, how far will it travel in 2.5 hours?
            Then, if another train travels the same distance but takes 3 hours, what is its speed?
            Finally, if both trains start at the same time from stations that are 300 miles apart
            and travel toward each other, how long will it take for them to meet?
            """
            
            response = client.generate_response_with_extended_thinking(
                prompt_text=complex_prompt,
                model="gemini-2.5-pro-preview-05-06",
                temperature=0.7,
                thinking_budget_tokens=2000,
            )
            
            if response["success"]:
                logging.info(f"✅ Gemini extended thinking response received")
                logging.info(f"Content: {response['content'][:200]}...")
                if "thinking" in response and response["thinking"]:
                    logging.info(f"Thinking: {response['thinking'][:200]}...")
                else:
                    logging.info("No thinking content returned")
                return True
            else:
                logging.error(f"❌ Gemini extended thinking failed: {response.get('error', 'Unknown error')}")
                return False
        except Exception as e:
            logging.error(f"❌ Error generating response: {str(e)}")
            return False
    else:
        logging.error("❌ Failed to initialize Gemini client")
        return False

def main():
    """Run tests and exit with appropriate status code."""
    success = test_gemini_thinking()
    if success:
        logging.info("🎉 All tests passed!")
        return 0
    else:
        logging.error("❌ Tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 
