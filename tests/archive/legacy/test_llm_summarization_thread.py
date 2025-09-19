#!/usr/bin/env python
"""
Test script for LLMSummaryThread to verify proper file handling and summary creation.
Tests the fixes for null pointer exceptions and proper file processing workflow.
"""

import logging
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.legacy.ui.workers.llm_summary_thread import LLMSummaryThread

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class TestLLMSummarizationThread:
    """Test class for LLMSummaryThread."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client for testing."""
        mock_client = MagicMock()
        mock_client.initialized = True
        mock_client.provider = "anthropic"
        
        def mock_generate_response(*args, **kwargs):
            """Mock implementation of generate_response."""
            time.sleep(0.1)  # Simulate API call delay
            return {
                "success": True,
                "content": "# Document Summary\n\nThis is a test summary of the document content.",
                "provider": "anthropic",
                "usage": {"input_tokens": 150, "output_tokens": 50}
            }
        
        mock_client.generate_response = MagicMock(side_effect=mock_generate_response)
        return mock_client
    
    @pytest.fixture
    def test_files(self):
        """Create test files needed for the summarization thread."""
        # Create a temporary directory for test files
        test_dir = tempfile.mkdtemp()
        
        # Create test markdown files
        test_file_1 = os.path.join(test_dir, "document_001.md")
        with open(test_file_1, "w", encoding="utf-8") as f:
            f.write("""# Medical Record - Document 001

## Patient Information
- Name: John Doe
- DOB: 1985-03-15
- Date of Service: 2024-01-15

## Assessment
Patient presents with anxiety symptoms following workplace incident.

## Treatment Plan
- Weekly therapy sessions
- Medication evaluation scheduled
- Follow-up in 2 weeks

## Notes
Patient is cooperative and engaged in treatment planning.
""")
        
        test_file_2 = os.path.join(test_dir, "document_002.md")
        with open(test_file_2, "w", encoding="utf-8") as f:
            f.write("""# Police Report - Document 002

## Incident Information
- Date: 2024-01-10
- Time: 14:30
- Location: 123 Main Street

## Description
Minor vehicle accident reported. No injuries sustained.

## Follow-up Actions
- Insurance contacted
- Report filed
- Case closed
""")
        
        # Create output directory
        output_dir = os.path.join(test_dir, "summaries")
        os.makedirs(output_dir, exist_ok=True)
        
        # Return test data
        return {
            "test_dir": test_dir,
            "markdown_files": [test_file_1, test_file_2],
            "output_dir": output_dir,
            "expected_summaries": [
                os.path.join(output_dir, "document_001_summary.md"),
                os.path.join(output_dir, "document_002_summary.md")
            ]
        }
    
    @pytest.fixture
    def mock_status_panel(self):
        """Create a mock status panel."""
        status_panel = MagicMock()
        status_panel.append_details = MagicMock()
        status_panel.append_error = MagicMock()
        status_panel.append_warning = MagicMock()
        return status_panel
    
    @patch("src.legacy.ui.workers.llm_summary_thread.get_configured_llm_provider")
    @patch("src.legacy.ui.workers.llm_summary_thread.count_tokens_cached")
    def test_successful_summarization_with_status_panel(self, mock_count_tokens_cached, 
                                                       mock_get_provider, mock_llm_client, 
                                                       test_files, mock_status_panel):
        """Test successful summarization with status panel logging."""
        # Setup mocks
        mock_get_provider.return_value = {"provider": mock_llm_client}
        mock_count_tokens_cached.return_value = {"success": True, "token_count": 1000}
        
        # Create thread instance
        thread = LLMSummaryThread(
            parent=None,
            markdown_files=test_files["markdown_files"],
            output_dir=test_files["output_dir"],
            subject_name="John Doe",
            subject_dob="1985-03-15",
            case_info="Test case for medical evaluation",
            llm_provider_id="anthropic",
            llm_model_name="claude-3-7-sonnet-latest"
        )
        
        # Create signal mocks
        progress_signal_mock = MagicMock()
        finished_signal_mock = MagicMock()
        file_progress_mock = MagicMock()
        file_finished_mock = MagicMock()
        error_signal_mock = MagicMock()
        
        thread.progress_signal = progress_signal_mock
        thread.finished_signal = finished_signal_mock
        thread.file_progress = file_progress_mock
        thread.file_finished = file_finished_mock
        thread.error_signal = error_signal_mock
        
        # Run the thread synchronously
        thread.run()
        
        # Verify LLM client was called for each file
        assert mock_llm_client.generate_response.call_count == 2, "LLM should be called once per file"
        
        # Verify summary files were created
        for expected_file in test_files["expected_summaries"]:
            assert os.path.exists(expected_file), f"Summary file {expected_file} was not created"
            
            # Check file content
            with open(expected_file, "r", encoding="utf-8") as f:
                content = f.read()
                assert "# Summary of" in content, "Summary should have proper header"
                assert "Document Analysis for John Doe" in content, "Summary should include subject name"
                assert "This is a test summary" in content, "Summary should include LLM response"
        
        # Verify status panel was used for logging
        mock_status_panel.append_details.assert_called()
        
        # Check that initialization logging occurred
        init_calls = [call for call in mock_status_panel.append_details.call_args_list 
                     if "Initializing LLM client" in str(call)]
        assert len(init_calls) > 0, "Should log LLM client initialization"
        
        # Check that success logging occurred
        success_calls = [call for call in mock_status_panel.append_details.call_args_list 
                        if "SUCCESS" in str(call)]
        assert len(success_calls) == 2, "Should log success for each file"
        
        # Verify finished signal was emitted with success
        finished_signal_mock.emit.assert_called_once()
        result = finished_signal_mock.emit.call_args[0][0]
        assert result["status"] == "completed", "Should complete successfully"
        assert result["processed"] == 2, "Should process 2 files"
        assert result["failed"] == 0, "Should have no failures"
        
        # Cleanup
        self._cleanup_test_files(test_files["test_dir"])
    
    @patch("src.legacy.ui.workers.llm_summary_thread.get_configured_llm_provider")
    @patch("src.legacy.ui.workers.llm_summary_thread.count_tokens_cached")
    def test_successful_summarization_without_status_panel(self, mock_count_tokens_cached, 
                                                          mock_get_provider, mock_llm_client, 
                                                          test_files):
        """Test successful summarization without status panel (None) - this was the bug we fixed."""
        # Setup mocks
        mock_get_provider.return_value = {"provider": mock_llm_client}
        mock_count_tokens_cached.return_value = {"success": True, "token_count": 1000}
        
        # Create thread instance with None status panel
        thread = LLMSummaryThread(
            parent=None,
            markdown_files=test_files["markdown_files"],
            output_dir=test_files["output_dir"],
            subject_name="John Doe",
            subject_dob="1985-03-15",
            case_info="Test case for medical evaluation",
            llm_provider_id="anthropic",
            llm_model_name="claude-3-7-sonnet-latest"
        )
        
        # Create signal mocks
        finished_signal_mock = MagicMock()
        thread.finished_signal = finished_signal_mock
        
        # This should not raise an AttributeError anymore
        try:
            thread.run()
            success = True
        except AttributeError as e:
            if "'NoneType' object has no attribute 'append_details'" in str(e):
                success = False
                pytest.fail(f"The null pointer bug was not fixed: {e}")
            else:
                raise e
        
        assert success, "Thread should run without errors when status_panel is None"
        
        # Verify summary files were still created
        for expected_file in test_files["expected_summaries"]:
            assert os.path.exists(expected_file), f"Summary file {expected_file} was not created"
        
        # Verify finished signal was emitted
        finished_signal_mock.emit.assert_called_once()
        
        # Cleanup
        self._cleanup_test_files(test_files["test_dir"])
    
    @patch("src.legacy.ui.workers.llm_summary_thread.get_configured_llm_provider")
    def test_llm_client_initialization_failure(self, mock_get_provider, test_files, mock_status_panel):
        """Test behavior when LLM client initialization fails."""
        # Setup mock to return None (initialization failure)
        mock_get_provider.return_value = None
        
        # Create thread instance
        thread = LLMSummaryThread(
            parent=None,
            markdown_files=test_files["markdown_files"],
            output_dir=test_files["output_dir"],
            subject_name="John Doe",
            subject_dob="1985-03-15",
            case_info="Test case for medical evaluation",
            llm_provider_id="anthropic",
            llm_model_name="claude-3-7-sonnet-latest"
        )
        
        # Create signal mocks
        finished_signal_mock = MagicMock()
        error_signal_mock = MagicMock()
        thread.finished_signal = finished_signal_mock
        thread.error_signal = error_signal_mock
        
        # Run the thread
        thread.run()
        
        # Verify error was handled
        error_signal_mock.emit.assert_called()
        
        # Verify finished signal indicates failure
        finished_signal_mock.emit.assert_called_once()
        result = finished_signal_mock.emit.call_args[0][0]
        assert result["status"] == "error", "Should fail with error status"
        assert result["processed"] == 0, "Should process 0 files"
        assert result["failed"] == len(test_files["markdown_files"]), "All files should be marked as failed"
        
        # Verify no summary files were created
        for expected_file in test_files["expected_summaries"]:
            assert not os.path.exists(expected_file), f"Summary file {expected_file} should not be created on failure"
        
        # Cleanup
        self._cleanup_test_files(test_files["test_dir"])
    
    @patch("src.legacy.ui.workers.llm_summary_thread.get_configured_llm_provider")
    @patch("src.legacy.ui.workers.llm_summary_thread.count_tokens_cached")
    def test_skip_existing_files(self, mock_count_tokens_cached, mock_get_provider, 
                                mock_llm_client, test_files, mock_status_panel):
        """Test that existing summary files are skipped."""
        # Setup mocks
        mock_get_provider.return_value = {"provider": mock_llm_client}
        mock_count_tokens_cached.return_value = {"success": True, "token_count": 1000}
        
        # Create one existing summary file
        existing_summary = test_files["expected_summaries"][0]
        with open(existing_summary, "w", encoding="utf-8") as f:
            f.write("# Existing Summary\nThis file already exists.")
        
        # Create thread instance
        thread = LLMSummaryThread(
            parent=None,
            markdown_files=test_files["markdown_files"],
            output_dir=test_files["output_dir"],
            subject_name="John Doe",
            subject_dob="1985-03-15",
            case_info="Test case for medical evaluation",
            llm_provider_id="anthropic",
            llm_model_name="claude-3-7-sonnet-latest"
        )
        
        # Create signal mocks
        finished_signal_mock = MagicMock()
        thread.finished_signal = finished_signal_mock
        
        # Run the thread
        thread.run()
        
        # Verify LLM client was called only once (for the non-existing file)
        assert mock_llm_client.generate_response.call_count == 1, "LLM should only be called for non-existing files"
        
        # Verify finished signal shows correct counts
        finished_signal_mock.emit.assert_called_once()
        result = finished_signal_mock.emit.call_args[0][0]
        assert result["processed"] == 1, "Should process 1 new file"
        assert result["skipped"] == 1, "Should skip 1 existing file"
        assert result["failed"] == 0, "Should have no failures"
        
        # Verify skip logging occurred
        skip_calls = [call for call in mock_status_panel.append_details.call_args_list 
                     if "SKIPPED" in str(call)]
        assert len(skip_calls) == 1, "Should log skipping of existing file"
        
        # Cleanup
        self._cleanup_test_files(test_files["test_dir"])
    
    @patch("src.legacy.ui.workers.llm_summary_thread.get_configured_llm_provider")
    @patch("src.legacy.ui.workers.llm_summary_thread.count_tokens_cached")
    def test_llm_api_error_handling(self, mock_count_tokens_cached, mock_get_provider, 
                                   test_files, mock_status_panel):
        """Test handling of LLM API errors."""
        # Create mock client that returns errors
        mock_client = MagicMock()
        mock_client.initialized = True
        mock_client.provider = "anthropic"
        
        def mock_generate_error_response(*args, **kwargs):
            """Mock implementation that returns an error."""
            return {
                "success": False,
                "error": "API rate limit exceeded",
                "content": None,
                "provider": "anthropic"
            }
        
        mock_client.generate_response = MagicMock(side_effect=mock_generate_error_response)
        
        # Setup mocks
        mock_get_client.return_value = {"client": mock_client}
        mock_count_tokens_cached.return_value = {"success": True, "token_count": 1000}
        
        # Create thread instance with only one file to avoid excessive errors
        thread = LLMSummaryThread(
            parent=None,
            markdown_files=[test_files["markdown_files"][0]],  # Only test with one file
            output_dir=test_files["output_dir"],
            subject_name="John Doe",
            subject_dob="1985-03-15",
            case_info="Test case for medical evaluation",
            llm_provider_id="anthropic",
            llm_model_name="claude-3-7-sonnet-latest"
        )
        
        # Create signal mocks
        finished_signal_mock = MagicMock()
        file_error_mock = MagicMock()
        thread.finished_signal = finished_signal_mock
        thread.file_error = file_error_mock
        
        # Run the thread
        thread.run()
        
        # Verify error was handled
        file_error_mock.emit.assert_called()
        
        # Verify finished signal shows failure
        finished_signal_mock.emit.assert_called_once()
        result = finished_signal_mock.emit.call_args[0][0]
        assert result["processed"] == 0, "Should process 0 files"
        assert result["failed"] == 1, "Should have 1 failure"
        
        # Verify error logging occurred
        error_calls = [call for call in mock_status_panel.append_details.call_args_list 
                      if "FAILED" in str(call) or "ERROR" in str(call)]
        assert len(error_calls) > 0, "Should log API errors"
        
        # Cleanup
        self._cleanup_test_files(test_files["test_dir"])
    
    def test_file_validation(self, test_files, mock_status_panel):
        """Test file validation logic."""
        # Create thread with a non-existent file
        non_existent_file = os.path.join(test_files["test_dir"], "non_existent.md")
        
        thread = LLMSummaryThread(
            parent=None,
            markdown_files=[non_existent_file],
            output_dir=test_files["output_dir"],
            subject_name="John Doe",
            subject_dob="1985-03-15",
            case_info="Test case for medical evaluation",
            llm_provider_id="anthropic",
            llm_model_name="claude-3-7-sonnet-latest"
        )
        
        # Test the file validation in summarize_markdown_file method
        try:
            thread.summarize_markdown_file(
                non_existent_file,
                os.path.join(test_files["output_dir"], "test_summary.md"),
                "test content"
            )
            pytest.fail("Should raise exception for non-existent file")
        except Exception as e:
            assert "File does not exist" in str(e), "Should validate file existence"
        
        # Cleanup
        self._cleanup_test_files(test_files["test_dir"])
    
    def _cleanup_test_files(self, test_dir):
        """Clean up test files."""
        try:
            import shutil
            shutil.rmtree(test_dir)
        except Exception as e:
            logger.warning(f"Could not clean up test files: {str(e)}")


if __name__ == "__main__":
    pytest.main(["-v", __file__]) 
