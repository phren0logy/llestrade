#!/usr/bin/env python
"""
Test script for IntegratedAnalysisThread to verify it uses Gemini's extended thinking API properly.
"""

import logging
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.common.llm import create_provider
from src.common.llm.providers.gemini import GeminiProvider
from src.legacy.ui.workers.integrated_analysis_thread import IntegratedAnalysisThread

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class TestIntegratedAnalysisThread:
    """Test class for IntegratedAnalysisThread."""
    
    @pytest.fixture
    def mock_gemini_client(self):
        """Create a mock GeminiClient with extended thinking capability."""
        # Create a simple MagicMock without spec to avoid InvalidSpecError
        mock_client = MagicMock()
        mock_client.is_initialized = True
        
        # Setup the extended thinking response
        def mock_generate_response_with_extended_thinking(*args, **kwargs):
            """Mock implementation of generate_response_with_extended_thinking."""
            time.sleep(0.5)  # Simulate API call delay
            return {
                "success": True,
                "content": "This is the final answer content",
                "thinking": "## Thinking\nThis is the thinking process in detail",
                "model": "gemini-2.5-pro-preview-05-06",
                "provider": "gemini",
                "usage": {"input_tokens": 100, "output_tokens": 200}
            }
        
        # Setup the regular response (should not be called)
        def mock_generate_response(*args, **kwargs):
            """Mock implementation of generate_response."""
            # We'll make this fail to verify it's not being used
            return {
                "success": False,
                "error": "This method should not be called - use extended thinking instead",
                "content": None,
                "provider": "gemini",
            }
        
        mock_client.generate_response_with_extended_thinking = MagicMock(
            side_effect=mock_generate_response_with_extended_thinking
        )
        mock_client.generate_response = MagicMock(
            side_effect=mock_generate_response
        )
        return mock_client
    
    @pytest.fixture
    def test_files(self):
        """Create test files needed for the analysis thread."""
        # Create a temporary directory for test files
        test_dir = tempfile.mkdtemp()
        
        # Create a sample combined file
        combined_file = os.path.join(test_dir, "combined_summaries.md")
        with open(combined_file, "w", encoding="utf-8") as f:
            f.write("# Combined Summaries\n\nThis is test content for the combined summaries file.")
        
        # Create output directory
        output_dir = os.path.join(test_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        
        # Return file paths
        return {
            "test_dir": test_dir,
            "combined_file": combined_file,
            "output_dir": output_dir,
            "integrated_file": os.path.join(output_dir, "integrated_analysis.md"),
            "thinking_file": os.path.join(output_dir, "integrated_analysis_thinking_tokens.md")
        }
    
    @patch("src.legacy.ui.workers.integrated_analysis_thread.PromptManager")
    @patch("src.common.llm.factory.create_provider")
    @patch("src.legacy.ui.workers.integrated_analysis_thread.TokenCounter.count")
    def test_uses_gemini_generate_only(
        self,
        mock_cached_count_tokens,
        mock_create_client,
        mock_prompt_manager,
        mock_gemini_client,
        test_files,
    ):
        """Test that IntegratedAnalysisThread correctly uses only Gemini's extended thinking function."""
        # Setup mocks
        mock_create_client.return_value = mock_gemini_client
        mock_cached_count_tokens.return_value = {"success": True, "token_count": 200000}
        
        # Create thread instance
        thread = IntegratedAnalysisThread(
            parent=None,
            combined_summary_path=test_files["combined_file"],
            original_markdown_files=[],
            output_dir=test_files["output_dir"],
            subject_name="Test Subject",
            subject_dob="1980-01-01",
            case_info="Test case information",
            progress_dialog=None,
            llm_provider_id="gemini",
            llm_model_name="gemini-2.5-pro-preview-05-06"
        )
        
        # Configure stubs to avoid real initialization/prompt loading
        mock_prompt_manager.return_value.get_prompt_template.return_value = {
            "system_prompt": "System prompt for {subject_name}",
            "user_prompt": "Summaries: {combined_summaries}\nOriginal: {original_documents}"
        }

        thread._initialize_llm_provider = MagicMock(return_value=True)
        thread.llm_provider = mock_gemini_client
        thread.llm_provider_label = "Gemini"
        thread.llm_effective_model = "gemini-2.5-pro-preview-05-06"
        mock_gemini_client.generate.return_value = {
            "success": True,
            "content": "This is the final answer content",
            "provider": "gemini",
            "model": "gemini-2.5-pro-preview-05-06"
        }
        
        # Create progress signal mock
        progress_signal_mock = MagicMock()
        thread.progress_signal = progress_signal_mock
        
        # Create finished signal mock
        finished_signal_mock = MagicMock()
        thread.finished_signal = finished_signal_mock
        
        # Run the thread synchronously (not as a QThread)
        thread.run()
        
        # Verify generate was invoked exactly once with our prompt
        mock_gemini_client.generate.assert_called_once()

        # Verify the finished signal was emitted with success
        finished_signal_mock.emit.assert_called_once()
        args = finished_signal_mock.emit.call_args[0]
        assert args[0] is True, "Finished signal did not indicate success"

        # Cleanup test files
        try:
            import shutil
            shutil.rmtree(test_files["test_dir"])
        except Exception as e:
            logger.warning(f"Could not clean up test files: {str(e)}")

if __name__ == "__main__":
    pytest.main(["-v", __file__]) 
