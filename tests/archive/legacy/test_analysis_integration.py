#!/usr/bin/env python
"""
Test script specifically for Analysis Integration tab functionality using pytest.
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.legacy.ui.workers.integrated_analysis_thread import IntegratedAnalysisThread

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


@pytest.fixture
def thread_dependencies(tmp_path: Path) -> dict:
    """Sets up dependencies for the IntegratedAnalysisThread tests."""
    # The tmp_path fixture provides a unique temporary directory for each test function
    combined_file_path = tmp_path / "test_combined.md"
    combined_file_path.write_text("# Test Combined Summary\n\nThis is test content.", encoding="utf-8")

    # Mock Qt-related objects that the thread interacts with
    mock_status_panel = MagicMock()
    mock_progress_dialog = MagicMock()

    return {
        "parent": None,
        "combined_summary_path": str(combined_file_path),
        "output_dir": str(tmp_path),
        "status_panel": mock_status_panel,
        "progress_dialog": mock_progress_dialog,
        "temp_dir": tmp_path,
    }


@patch("src.legacy.ui.workers.integrated_analysis_thread.PromptManager")
@patch("src.legacy.ui.workers.integrated_analysis_thread.get_configured_llm_client")
@patch("builtins.open", new_callable=mock_open)
@patch("src.legacy.ui.workers.integrated_analysis_thread.time.strftime")
def test_integrated_analysis_thread_success(
    mock_strftime: MagicMock,
    mock_open_func: MagicMock,
    mock_get_client: MagicMock,
    mock_prompt_manager: MagicMock,
    thread_dependencies: dict,
):
    """
    Test the successful execution of IntegratedAnalysisThread.
    - Mocks the LLM client to return a successful response.
    - Verifies that the thread writes the correct output file.
    - Checks that the 'finished' signal is emitted with success status.
    """
    # --- Arrange ---
    # Mock PromptManager to return a valid template
    mock_prompt_manager.return_value.get_prompt_template.return_value = {
        "system_prompt": "System Prompt",
        "user_prompt": "User Prompt",
    }
    
    # Mock the timestamp for a predictable output filename
    mock_strftime.return_value = "20231026_120000"
    mock_output_content = "Integrated Analysis Output Content"

    # Mock the LLM client setup
    mock_llm_client = MagicMock()
    mock_llm_client.generate_response.return_value = {
        "success": True,
        "content": mock_output_content,
    }
    mock_llm_client.is_initialized = True
    mock_get_client.return_value = {
        "client": mock_llm_client,
        "provider_label": "mock_provider",
        "effective_model_name": "mock_model",
    }
    
    # Read back the content written by the fixture to pass to mock_open
    mock_open_func.return_value.read.return_value = thread_dependencies["temp_dir"].joinpath("test_combined.md").read_text()

    # Instantiate the thread with dependencies from the fixture
    thread = IntegratedAnalysisThread(
        parent=thread_dependencies["parent"],
        combined_summary_path=thread_dependencies["combined_summary_path"],
        original_markdown_files=[],
        output_dir=thread_dependencies["output_dir"],
        subject_name="Test Subject",
        subject_dob="2000-01-01",
        case_info="This is a test case",
        status_panel=thread_dependencies["status_panel"],
        progress_dialog=thread_dependencies["progress_dialog"],
        llm_provider_id="test_provider",
        llm_model_name="test_model",
    )

    # Mock the Qt signals
    thread.finished_signal = MagicMock()
    thread.error_signal = MagicMock()
    thread.progress_signal = MagicMock()

    # --- Act ---
    thread.run()

    # --- Assert ---
    # Verify the LLM client was initialized and used
    mock_get_client.assert_called_once()
    mock_llm_client.generate_response.assert_called_once()
    
    # Verify the output file was written correctly
    expected_filename = "Test Subject_Integrated_Analysis_20231026_120000.md"
    # The thread creates a specific subdirectory for the output
    expected_output_path = (
        thread_dependencies["temp_dir"] / "integrated_analysis" / expected_filename
    )
    
    # Check that open was called for reading the input and writing the output
    mock_open_func.assert_any_call(thread_dependencies["combined_summary_path"], "r", encoding="utf-8")
    mock_open_func.assert_any_call(str(expected_output_path), "w", encoding="utf-8")
    
    # Check that the content from the LLM was written to the file
    handle = mock_open_func()
    handle.write.assert_any_call(mock_output_content)

    # Verify that the correct signals were emitted
    thread.finished_signal.emit.assert_called_once_with(
        True, "Integrated analysis generated successfully.", str(expected_output_path), thread_dependencies["progress_dialog"]
    )
    thread.error_signal.emit.assert_not_called()

    # Verify progress was reported
    thread.progress_signal.emit.assert_any_call(100, "Integrated analysis complete.")


@patch("src.legacy.ui.workers.integrated_analysis_thread.PromptManager")
@patch("src.legacy.ui.workers.integrated_analysis_thread.get_configured_llm_client")
def test_integrated_analysis_thread_llm_failure(
    mock_get_client: MagicMock,
    mock_prompt_manager: MagicMock,
    thread_dependencies: dict,
):
    """
    Test the IntegratedAnalysisThread's behavior when the LLM call fails.
    - Mocks the LLM client to return a failure response.
    - Verifies that the 'error' signal is emitted.
    - Verifies that the 'finished' signal is emitted with a failure status.
    """
    # --- Arrange ---
    # Mock PromptManager
    mock_prompt_manager.return_value.get_prompt_template.return_value = {
        "system_prompt": "System Prompt",
        "user_prompt": "User Prompt",
    }

    # Mock the LLM client to simulate a failure
    mock_llm_client = MagicMock()
    mock_llm_client.generate_response.return_value = {
        "success": False,
        "error": "Simulated LLM Error",
    }
    mock_llm_client.is_initialized = True
    mock_get_client.return_value = {
        "client": mock_llm_client,
        "provider_label": "mock_provider",
        "effective_model_name": "mock_model",
    }

    # Instantiate the thread
    thread = IntegratedAnalysisThread(
        parent=thread_dependencies["parent"],
        combined_summary_path=thread_dependencies["combined_summary_path"],
        original_markdown_files=[],
        output_dir=thread_dependencies["output_dir"],
        subject_name="Test Subject",
        subject_dob="2000-01-01",
        case_info="This is a test case",
        status_panel=thread_dependencies["status_panel"],
        progress_dialog=thread_dependencies["progress_dialog"],
        llm_provider_id="test_provider",
        llm_model_name="test_model",
    )

    # Mock the Qt signals
    thread.finished_signal = MagicMock()
    thread.error_signal = MagicMock()
    thread.progress_signal = MagicMock()

    # --- Act ---
    thread.run()

    # --- Assert ---
    # Verify signals for failure
    error_message = "API call failed after 3 retries: Simulated LLM Error"
    thread.error_signal.emit.assert_called_once_with(
        f"Error during integrated analysis: {error_message}", thread_dependencies["progress_dialog"]
    )
    thread.finished_signal.emit.assert_called_once_with(
        False, f"Error during integrated analysis: {error_message}", "", thread_dependencies["progress_dialog"]
    ) 
