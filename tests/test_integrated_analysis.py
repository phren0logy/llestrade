#!/usr/bin/env python
"""
Test script for IntegratedAnalysisThread to verify it uses Gemini's extended thinking API properly.
"""

import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure we can import from the parent directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from llm.providers import GeminiProvider
from ui.workers.integrated_analysis_thread import IntegratedAnalysisThread

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class TestIntegratedAnalysisThread:
    """Test class for IntegratedAnalysisThread."""
    
    @pytest.fixture
    def mock_gemini_provider(self):
        """Create a mock GeminiProvider with extended thinking capability."""
        mock_provider = MagicMock(spec=GeminiProvider)
        mock_provider.initialized = True
        
        # Setup the standard response (should be called)
        def mock_generate(*args, **kwargs):
            """Mock implementation of generate."""
            time.sleep(0.5)  # Simulate API call delay
            return {
                "success": True,
                "content": "This is the final answer content",
                "thinking": "## Thinking\nThis is the thinking process in detail",
                "model": "gemini-2.5-pro-preview-05-06",
                "provider": "gemini",
                "usage": {"input_tokens": 100, "output_tokens": 200}
            }
        
        # Setup the extended thinking response (should not be called in this thread)
        def mock_generate_with_extended_thinking(*args, **kwargs):
            """Mock implementation of generate_with_extended_thinking."""
            # This method should not be called by IntegratedAnalysisThread
            return {
                "success": False,
                "error": "This method should not be called by IntegratedAnalysisThread",
                "content": None,
                "provider": "gemini",
            }
        
        mock_provider.generate = MagicMock(
            side_effect=mock_generate
        )
        mock_provider.generate_with_extended_thinking = MagicMock(
            side_effect=mock_generate_with_extended_thinking
        )
        return mock_provider
    
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
    
    @patch("ui.workers.integrated_analysis_thread.PromptManager")
    @patch("ui.workers.integrated_analysis_thread.get_configured_llm_provider")
    @patch("ui.workers.integrated_analysis_thread.count_tokens_cached")
    def test_uses_gemini_standard_generate(self, mock_count_tokens_cached, mock_get_configured_llm_provider, mock_prompt_manager, 
                                               mock_gemini_provider, test_files):
        """Test that IntegratedAnalysisThread correctly uses Gemini's standard generate function."""
        # Setup mocks
        mock_get_configured_llm_provider.return_value = {
            "provider": mock_gemini_provider,
            "provider_label": "Gemini",
            "effective_model_name": "gemini-2.5-pro-preview-05-06"
        }
        mock_count_tokens_cached.return_value = {"success": True, "token_count": 200000}
        
        # Mock the prompt manager
        mock_prompt_manager_instance = MagicMock()
        mock_prompt_manager.return_value = mock_prompt_manager_instance
        mock_prompt_manager_instance.get_prompt_template.return_value = {
            "system": "You are a helpful assistant.",
            "user": "Please analyze the following document."
        }
        
        # Create mock objects for additional required parameters
        mock_status_panel = MagicMock()
        mock_status_panel.append_details = MagicMock()
        mock_status_panel.append_error = MagicMock()
        mock_status_panel.append_warning = MagicMock()
        mock_progress_dialog = MagicMock()
        
        # Create thread instance with None parent (valid for QThread)
        thread = IntegratedAnalysisThread(
            parent=None,  # Use None instead of mock for Qt compatibility
            combined_summary_path=test_files["combined_file"],
            original_markdown_files=[],  # Empty list for test
            output_dir=test_files["output_dir"],
            subject_name="Test Subject",
            subject_dob="1980-01-01",
            case_info="Test case information",
            status_panel=mock_status_panel,
            progress_dialog=mock_progress_dialog,
            llm_provider_id="gemini",
            llm_model_name="gemini-2.5-pro-preview-05-06"
        )
        
        # Override LLM provider with our mock
        thread.llm_provider = mock_gemini_provider
        
        # Create progress signal mock
        progress_signal_mock = MagicMock()
        thread.progress_signal = progress_signal_mock
        
        # Create finished signal mock
        finished_signal_mock = MagicMock()
        thread.finished_signal = finished_signal_mock
        
        # Run the thread synchronously (not as a QThread)
        thread.run()
        
        # Verify that only generate was called
        mock_gemini_provider.generate.assert_called_once()
        mock_gemini_provider.generate_with_extended_thinking.assert_not_called()
        
        # Note: We're not checking file creation in this test since it's focused on
        # verifying the correct API method is called. File creation would require
        # more complex mocking of the entire workflow.
        
        # Cleanup test files
        try:
            import shutil
            shutil.rmtree(test_files["test_dir"])
        except Exception as e:
            logger.warning(f"Could not clean up test files: {str(e)}")

if __name__ == "__main__":
    pytest.main(["-v", __file__]) 
