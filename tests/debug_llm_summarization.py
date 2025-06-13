#!/usr/bin/env python
"""
Diagnostic script for debugging LLM summarization issues.

This script tests the LLM summarization functionality outside of the UI context
to isolate whether the issue is in the worker thread, API calls, or UI integration.

Usage:
    uv run python tests/debug_llm_summarization.py

Privacy Note:
    - API keys are read from .env file (gitignored)
    - No API keys will be logged or exposed
    - Only connection status and errors are reported
"""

import logging
import os
import sys
import tempfile
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('debug_summarization.log')
    ]
)
logger = logging.getLogger(__name__)

def test_environment():
    """Test the basic environment setup."""
    logger.info("🔍 Testing environment setup...")
    
    # Check .env file exists
    env_file = project_root / ".env"
    if env_file.exists():
        logger.info("✅ .env file found")
    else:
        logger.error("❌ .env file not found - API keys may not be available")
    
    # Test imports
    try:
        from app_config import get_configured_llm_client
        from ui.workers.llm_summary_thread import LLMSummaryThread
        logger.info("✅ Successfully imported required modules")
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        return False
    
    return True

def test_api_client():
    """Test LLM client initialization independently."""
    logger.info("🔍 Testing LLM client initialization...")
    
    try:
        from app_config import get_configured_llm_client
        
        # Test default client (should use anthropic)
        logger.info("📞 Calling get_configured_llm_client with default settings...")
        client_info = get_configured_llm_client()
        
        if client_info:
            logger.info(f"✅ Client info received: {type(client_info)}")
            logger.info(f"📋 Client info keys: {list(client_info.keys()) if isinstance(client_info, dict) else 'Not a dict'}")
            
            if client_info.get("client"):
                client = client_info["client"]
                logger.info(f"✅ Client extracted: {type(client)}")
                logger.info(f"🔍 Provider: {getattr(client, 'provider', 'Unknown')}")
                logger.info(f"🔍 Is initialized: {getattr(client, 'is_initialized', 'Unknown')}")
                
                if hasattr(client, 'is_initialized') and client.is_initialized:
                    logger.info("🎉 Client is properly initialized!")
                    return client
                else:
                    logger.error("❌ Client is not initialized")
            else:
                logger.error("❌ No 'client' key in client_info")
        else:
            logger.error("❌ get_configured_llm_client returned None")
            
    except Exception as e:
        logger.exception(f"💥 Exception during client initialization: {e}")
    
    return None

def test_simple_api_call(client):
    """Test a simple API call to verify connectivity."""
    logger.info("🔍 Testing simple API call...")
    
    try:
        # Simple test prompt
        test_prompt = "Please respond with exactly 'API test successful' and nothing else."
        system_prompt = "You are a helpful assistant. Follow instructions exactly."
        
        logger.info("📞 Making API call...")
        response = client.generate_response(
            prompt_text=test_prompt,
            system_prompt=system_prompt,
            temperature=0.1
        )
        
        logger.info(f"✅ API call completed")
        logger.info(f"📋 Response type: {type(response)}")
        
        if isinstance(response, dict):
            logger.info(f"📋 Response keys: {list(response.keys())}")
            
            if response.get("success"):
                logger.info("🎉 API call successful!")
                content = response.get("content", "")
                logger.info(f"📝 Response content length: {len(content)}")
                logger.info(f"📝 Response preview: {content[:100]}...")
                return True
            else:
                error = response.get("error", "Unknown error")
                logger.error(f"❌ API call failed: {error}")
        else:
            logger.error(f"❌ Unexpected response type: {type(response)}")
            
    except Exception as e:
        logger.exception(f"💥 Exception during API call: {e}")
    
    return False

def create_test_markdown_file():
    """Create a test markdown file for summarization."""
    logger.info("📝 Creating test markdown file...")
    
    test_content = """# Test Medical Record

## Patient Information
- Name: Test Patient
- DOB: 1990-01-01
- Date of Service: 2024-01-01

## Assessment
This is a test document for debugging the summarization function.
The patient appears to be in good health with no significant concerns.

## Treatment Plan
1. Continue regular checkups
2. Maintain current medication regimen
3. Follow up in 6 months

## Notes
This is a synthetic test document created for debugging purposes.
"""
    
    # Create temp file
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8')
    temp_file.write(test_content)
    temp_file.close()
    
    logger.info(f"✅ Test file created: {temp_file.name}")
    logger.info(f"📊 File size: {os.path.getsize(temp_file.name)} bytes")
    
    return temp_file.name

def test_summarization_workflow():
    """Test the complete summarization workflow."""
    logger.info("🔍 Testing complete summarization workflow...")
    
    try:
        from PySide6.QtCore import QCoreApplication

        from ui.workers.llm_summary_thread import LLMSummaryThread
        
        # Create Qt application (required for QThread)
        app = QCoreApplication.instance()
        if app is None:
            app = QCoreApplication(sys.argv)
        
        # Create test file
        test_file = create_test_markdown_file()
        
        # Create temporary output directory
        output_dir = tempfile.mkdtemp()
        logger.info(f"📂 Output directory: {output_dir}")
        
        # Create summarization thread
        logger.info("🧵 Creating LLMSummaryThread...")
        thread = LLMSummaryThread(
            parent=None,
            markdown_files=[test_file],
            output_dir=output_dir,
            subject_name="Test Patient",
            subject_dob="1990-01-01",
            case_info="Test case for debugging",
            status_panel=None,  # No UI component
            llm_provider_id="anthropic",
            llm_model_name="claude-3-7-sonnet-latest"
        )
        
        # Test synchronous execution (bypass Qt threading)
        logger.info("🔄 Running summarization synchronously...")
        thread.run()
        
        # Check results  
        # The filename should be based on the test file basename
        test_basename = os.path.splitext(os.path.basename(test_file))[0]
        expected_summary_file = os.path.join(output_dir, f"{test_basename}_summary.md")
        logger.info(f"🔍 Expected summary file: {expected_summary_file}")
        if os.path.exists(expected_summary_file):
            logger.info("🎉 Summary file created successfully!")
            with open(expected_summary_file, 'r', encoding='utf-8') as f:
                content = f.read()
                logger.info(f"📝 Summary length: {len(content)} characters")
                logger.info(f"📝 Summary preview: {content[:200]}...")
            return True
        else:
            logger.error("❌ Summary file was not created")
            logger.info(f"📂 Output directory contents: {os.listdir(output_dir)}")
        
        # Cleanup
        os.unlink(test_file)
        if os.path.exists(expected_summary_file):
            os.unlink(expected_summary_file)
        os.rmdir(output_dir)
        
    except Exception as e:
        logger.exception(f"💥 Exception during workflow test: {e}")
    
    return False

def main():
    """Run all diagnostic tests."""
    logger.info("🚀 Starting LLM Summarization Diagnostic Tests")
    logger.info("=" * 60)
    
    # Test 1: Environment
    if not test_environment():
        logger.error("❌ Environment test failed - cannot proceed")
        return False
    
    logger.info("=" * 60)
    
    # Test 2: API Client
    client = test_api_client()
    if not client:
        logger.error("❌ API client test failed - cannot proceed")
        return False
    
    logger.info("=" * 60)
    
    # Test 3: Simple API Call
    if not test_simple_api_call(client):
        logger.error("❌ API call test failed")
        return False
    
    logger.info("=" * 60)
    
    # Test 4: Complete Workflow
    if not test_summarization_workflow():
        logger.error("❌ Summarization workflow test failed")
        return False
    
    logger.info("=" * 60)
    logger.info("🎉 All diagnostic tests completed successfully!")
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        logger.error("❌ Diagnostic tests failed - check logs above for details")
        sys.exit(1)
    else:
        logger.info("✅ All tests passed - summarization should work correctly")
        sys.exit(0) 
