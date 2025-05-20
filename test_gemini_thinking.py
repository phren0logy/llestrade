#!/usr/bin/env python
"""
Test script for Gemini extended thinking capabilities
"""

import logging
import os
import sys
import threading
import time
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Import LLM utilities
from llm_utils import GeminiClient, LLMClientFactory


def test_gemini_thinking():
    """Test Gemini's extended thinking implementation."""
    logger.info("Testing Gemini extended thinking capabilities...")
    
    # Create a dedicated Gemini client
    client = LLMClientFactory.create_client(provider="gemini")
    
    if not client or not client.is_initialized:
        logger.error("❌ Failed to initialize Gemini client")
        return False
    
    logger.info("✅ Gemini client initialized successfully")
    
    # Simple prompt for testing
    test_prompt = """
    Create a detailed analysis of the following scenario:
    
    A 45-year-old patient presents with chronic headaches, fatigue, and mild memory issues that have persisted for 6 months.
    Previous medical history includes hypertension (managed with medication) and a minor concussion 2 years ago.
    Recent blood work shows slightly elevated inflammatory markers, but other results are within normal ranges.
    
    What are the most likely diagnoses, what additional tests would you recommend, and what is your
    recommended treatment approach? Explain your reasoning in detail.
    """
    
    # Simple system prompt
    system_prompt = "You are a helpful medical assistant that provides detailed analysis of medical scenarios."
    
    # Track API call completion
    api_complete = False
    api_error = None
    api_response = None
    
    # Define API call function with timeout tracking
    def make_extended_thinking_call():
        nonlocal api_complete, api_error, api_response
        try:
            logger.info("Making Gemini extended thinking API call...")
            start = time.time()
            
            # Use extended thinking with explicit parameters
            api_response = client.generate_response_with_extended_thinking(
                prompt_text=test_prompt,
                system_prompt=system_prompt,
                model="gemini-2.5-pro-preview-05-06",
                temperature=0.5,
                thinking_budget_tokens=10000,
            )
            
            elapsed = time.time() - start
            logger.info(f"API call completed in {elapsed:.1f} seconds")
            api_complete = True
        except Exception as e:
            api_error = e
            api_complete = True
            logger.error(f"API call failed with error: {str(e)}")
    
    # Start API call in a thread
    api_thread = threading.Thread(target=make_extended_thinking_call)
    api_thread.daemon = True
    logger.info("Starting API call in background thread...")
    api_thread.start()
    
    # Wait with progress updates
    timeout = 600  # 10-minute timeout
    start_time = time.time()
    wait_interval = 1.0
    
    while not api_complete and (time.time() - start_time) < timeout:
        elapsed = time.time() - start_time
        if int(elapsed) % 15 == 0:  # Log every 15 seconds
            logger.info(f"Waiting for Gemini response... ({int(elapsed)}s elapsed)")
        time.sleep(wait_interval)
    
    # Check timeout
    if not api_complete:
        logger.error(f"❌ API call timed out after {timeout} seconds")
        return False
    
    # Check for errors
    if api_error:
        logger.error(f"❌ API call failed with error: {str(api_error)}")
        return False
    
    # Check for valid response
    if not api_response or not api_response.get("success", False):
        error = api_response.get("error", "Unknown error") if api_response else "No response"
        logger.error(f"❌ API call unsuccessful: {error}")
        return False
    
    # Validate response structure
    content = api_response.get("content", "")
    thinking = api_response.get("thinking", "")
    provider = api_response.get("provider", "unknown")
    model = api_response.get("model", "unknown")
    
    logger.info(f"✅ Response received from {provider} using model {model}")
    logger.info(f"✅ Content length: {len(content)} chars")
    logger.info(f"✅ Thinking length: {len(thinking)} chars")
    
    # Check if thinking is present and properly formatted
    if not thinking or len(thinking) < 200:
        logger.error(f"❌ Insufficient thinking content: {len(thinking)} chars")
        return False
    
    if "## Thinking" not in thinking:
        logger.warning("⚠️ Thinking section not properly formatted with '## Thinking' header")
    
    logger.info("✅ All checks passed! Extended thinking is working correctly")
    
    # Save the results to files for examination
    output_dir = Path("./test_output")
    output_dir.mkdir(exist_ok=True)
    
    # Save thinking to file
    thinking_file = output_dir / "gemini_thinking_test.md"
    with open(thinking_file, "w", encoding="utf-8") as f:
        f.write(f"# Gemini Extended Thinking Test\n\n")
        f.write(f"**Provider:** {provider}\n")
        f.write(f"**Model:** {model}\n")
        f.write(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(thinking)
    
    # Save content to file
    content_file = output_dir / "gemini_content_test.md"
    with open(content_file, "w", encoding="utf-8") as f:
        f.write(f"# Gemini Content Test\n\n")
        f.write(f"**Provider:** {provider}\n")
        f.write(f"**Model:** {model}\n")
        f.write(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(content)
    
    logger.info(f"✅ Test results saved to {output_dir}")
    logger.info(f"✅ Thinking file: {thinking_file}")
    logger.info(f"✅ Content file: {content_file}")
    
    return True

if __name__ == "__main__":
    # Run the test
    success = test_gemini_thinking()
    sys.exit(0 if success else 1) 
