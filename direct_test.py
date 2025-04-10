#!/usr/bin/env python
"""
Direct test for LLM API calls without using the Qt framework.
"""

import logging
import os
import time
import traceback

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def test_llm_api():
    """Test basic LLM API functionality."""
    try:
        print("Importing LLMClient...")
        from llm_utils import AnthropicClient, GeminiClient, LLMClient, LLMClientFactory

        # Test importing
        print("\n=== Testing import phase ===")
        print(f"LLMClient imported: {'✅' if LLMClient else '❌'}")
        print(f"LLMClientFactory imported: {'✅' if LLMClientFactory else '❌'}")
        print(f"AnthropicClient imported: {'✅' if AnthropicClient else '❌'}")
        print(f"GeminiClient imported: {'✅' if GeminiClient else '❌'}")

        # Try direct Anthropic client
        print("\n=== Testing Anthropic client directly ===")
        try:
            anthropic = AnthropicClient()
            print(
                f"Anthropic initialized: {'✅' if anthropic.is_initialized else '❌'}"
            )

            if anthropic.is_initialized:
                # Token counting test
                token_result = anthropic.count_tokens(text="This is a test")
                print(
                    f"Token counting: {'✅' if token_result.get('success') else '❌'}"
                )
                if token_result.get("success"):
                    print(f"Token count: {token_result.get('token_count')}")
                else:
                    print(f"Token counting error: {token_result.get('error')}")

                # Simple response test
                response = anthropic.generate_response(
                    prompt_text="What is an LLM?", temperature=0.1
                )
                print(
                    f"Response generation: {'✅' if response.get('success') else '❌'}"
                )
                if response.get("success"):
                    print(f"Response length: {len(response.get('content', ''))}")
                    print(f"Response snippet: {response.get('content', '')[:100]}...")
                else:
                    print(f"Response error: {response.get('error')}")
            else:
                print("Skipping API tests since Anthropic client failed to initialize")
        except Exception as e:
            print(f"❌ Error testing Anthropic client: {str(e)}")
            traceback.print_exc()

        # Try direct Gemini client
        print("\n=== Testing Gemini client directly ===")
        try:
            gemini = GeminiClient()
            print(f"Gemini initialized: {'✅' if gemini.is_initialized else '❌'}")

            if gemini.is_initialized:
                # Test Gemini token counting (note: this uses estimation)
                token_result = gemini.count_tokens(text="This is a test")
                print(
                    f"Token counting: {'✅' if token_result.get('success') else '❌'}"
                )
                if token_result.get("success"):
                    print(f"Token count: {token_result.get('token_count')}")
                else:
                    print(f"Token counting error: {token_result.get('error')}")

                # Simple response test
                response = gemini.generate_response(
                    prompt_text="What is an LLM?", temperature=0.1
                )
                print(
                    f"Response generation: {'✅' if response.get('success') else '❌'}"
                )
                if response.get("success"):
                    print(f"Response length: {len(response.get('content', ''))}")
                    print(f"Response snippet: {response.get('content', '')[:100]}...")
                else:
                    print(f"Response error: {response.get('error')}")
            else:
                print("Skipping API tests since Gemini client failed to initialize")
        except Exception as e:
            print(f"❌ Error testing Gemini client: {str(e)}")
            traceback.print_exc()

        # Test legacy client (the one used by the application)
        print("\n=== Testing legacy LLMClient ===")
        try:
            legacy_client = LLMClient()
            print(
                f"Legacy client anthropic_initialized: {'✅' if legacy_client.anthropic_initialized else '❌'}"
            )
            print(
                f"Legacy client gemini_initialized: {'✅' if legacy_client.gemini_initialized else '❌'}"
            )

            # Token counting test
            token_result = legacy_client.count_tokens(text="This is a test")
            print(f"Token counting: {'✅' if token_result.get('success') else '❌'}")
            if token_result.get("success"):
                print(f"Token count: {token_result.get('token_count')}")
            else:
                print(f"Token counting error: {token_result.get('error')}")

            # Simple response test
            response = legacy_client.generate_response(
                prompt_text="What is an LLM?", temperature=0.1
            )
            print(f"Response generation: {'✅' if response.get('success') else '❌'}")
            if response.get("success"):
                print(f"Response length: {len(response.get('content', ''))}")
                print(f"Response snippet: {response.get('content', '')[:100]}...")
            else:
                print(f"Response error: {response.get('error')}")

        except Exception as e:
            print(f"❌ Error testing legacy client: {str(e)}")
            traceback.print_exc()

    except Exception as e:
        print(f"❌ Error importing LLM modules: {str(e)}")
        traceback.print_exc()


def test_summarization_specific():
    """Test summarization-specific functionality."""
    print("\n=== Testing specific summarization workflow ===")

    try:
        # Create test directory and file
        test_dir = "test_direct"
        os.makedirs(test_dir, exist_ok=True)

        test_file_path = os.path.join(test_dir, "test_doc.md")
        with open(test_file_path, "w") as f:
            f.write(
                """# Test Document

This is a simple test document for summarization.

## Subject Information
John Doe, born 1988-01-15, is the subject of this document.

## Education
- Graduated high school in 2006
- Received Bachelor's degree in Computer Science in 2010
- Completed Master's in Information Technology in 2012
"""
            )

        # Create summarization thread manually
        print("Creating summarization thread...")
        from ui.workers.llm_summary_thread import LLMSummaryThread

        # Create a custom progress handler
        def progress_handler(percent, message):
            print(f"Progress {percent}%: {message}")

        def finish_handler(results):
            print(f"Summarization complete: {results}")

        def error_handler(error):
            print(f"Summarization error: {error}")

        # Initialize thread
        output_dir = os.path.join(test_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        thread = LLMSummaryThread(
            markdown_files=[test_file_path],
            output_dir=output_dir,
            subject_name="John Doe",
            subject_dob="1988-01-15",
            case_info="This is a test case.",
        )

        # Connect handlers
        thread.progress_signal.connect(progress_handler)
        thread.finished_signal.connect(finish_handler)
        thread.error_signal.connect(error_handler)

        # Run thread
        print("Starting summarization thread...")
        thread.run()  # Direct run instead of thread.start() to keep it in main thread

        # Wait a moment to let all output flush
        time.sleep(1)

    except Exception as e:
        print(f"❌ Error in summarization test: {str(e)}")
        traceback.print_exc()


if __name__ == "__main__":
    try:
        print("Running direct LLM API tests...")
        test_llm_api()

        print("\nRunning summarization workflow test...")
        test_summarization_specific()

    except Exception as e:
        print(f"❌ Critical error in test script: {str(e)}")
        traceback.print_exc()
