"""
Utility functions for interacting with the Anthropic Claude API.
Handles LLM connections and prompt management.
"""

import base64
import os
import time
from typing import Any, Dict, List, Optional, Union

import anthropic
import httpx


def get_client(
    timeout: float = 60.0,
    max_retries: int = 2,
) -> anthropic.Anthropic:
    """
    Initialize and return an Anthropic client with timeout configuration.

    Args:
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries for failed requests

    Returns:
        Configured Anthropic client

    Raises:
        ValueError: If ANTHROPIC_API_KEY environment variable is not set
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    return anthropic.Anthropic(
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
    )


def get_client_with_extended_thinking(
    timeout: float = 60.0,
    max_retries: int = 2,
    thinking_budget_tokens: int = 16000,
) -> anthropic.Anthropic:
    """
    Initialize and return an Anthropic client configured for extended thinking.

    Extended thinking gives Claude 3.7 Sonnet enhanced reasoning capabilities for complex tasks,
    while also providing transparency into its step-by-step thought process.

    Args:
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries for failed requests
        thinking_budget_tokens: Maximum number of tokens Claude is allowed to use for its internal reasoning process
                               (must be less than max_tokens in any request)

    Returns:
        Configured Anthropic client with extended thinking parameters

    Raises:
        ValueError: If ANTHROPIC_API_KEY environment variable is not set
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    return anthropic.Anthropic(
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
    )


def generate_response(
    prompt,
    max_tokens=32000,
    temperature=0.0,
    timeout=60,
    retry_delay=1,
    max_retries=3,
    max_retry_delay=10,
    model="claude-3-7-sonnet-latest",
):
    """
    Generate a response from Claude with error handling and retries.

    Args:
        prompt: The prompt to send to Claude
        max_tokens: Maximum number of tokens to generate
        temperature: Temperature for response generation
        timeout: Timeout for the request in seconds
        retry_delay: Initial delay between retries in seconds
        max_retries: Maximum number of retries
        max_retry_delay: Maximum delay between retries in seconds
        model: Model to use for generation (default: "claude-3-7-sonnet-latest")

    Returns:
        Dictionary containing:
            - 'success': Boolean indicating if the request was successful
            - 'content': Generated response text if successful
            - 'error': Error message if unsuccessful
    """
    result = {"success": False, "content": None, "error": None}

    retries = 0
    current_delay = retry_delay

    while retries <= max_retries:
        try:
            client = get_client(
                timeout=timeout, max_retries=0
            )  # Handle retries manually

            # Split the prompt to separate system instructions from transcript content
            # Assuming the prompt format is consistent and contains transcript content
            # that can be identified and separated

            # Extract transcript content from the prompt if it exists
            transcript_content = None
            user_query = prompt

            # Check if prompt contains a transcript section (simple check for demonstration)
            # In a real implementation, you might need a more sophisticated way to identify the transcript
            if "TRANSCRIPT:" in prompt:
                parts = prompt.split("TRANSCRIPT:", 1)
                user_query = parts[0].strip()
                if len(parts) > 1:
                    transcript_content = "TRANSCRIPT:" + parts[1]

            # Prepare the messages with caching if transcript content exists
            system_messages = [
                {
                    "type": "text",
                    "text": "You are an advanced assistant designed to help a forensic psychiatrist. Your task is to analyze and objectively document case information in a formal clinical style, maintaining professional psychiatric documentation standards. Distinguish between information from the subject and objective findings. Report specific details such as dates, frequencies, dosages, and other relevant clinical data. Document without emotional language or judgment.",
                }
            ]

            # Add transcript content with cache_control if it exists
            if transcript_content:
                system_messages.append(
                    {
                        "type": "text",
                        "text": transcript_content,
                        "cache_control": {"type": "ephemeral"},
                    }
                )

                # Use only the user query part for the user message
                user_message = user_query
            else:
                # If no transcript was detected, use the entire prompt
                user_message = prompt

            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_messages,
                messages=[{"role": "user", "content": user_message}],
                timeout=timeout,  # Apply timeout at the method level for consistency
            )

            result["success"] = True
            result["content"] = message.content[0].text

            # Add cache usage information if available
            if hasattr(message, "usage"):
                result["cache_info"] = {
                    "cache_creation_input_tokens": getattr(
                        message.usage, "cache_creation_input_tokens", 0
                    ),
                    "cache_read_input_tokens": getattr(
                        message.usage, "cache_read_input_tokens", 0
                    ),
                    "input_tokens": getattr(message.usage, "input_tokens", 0),
                    "output_tokens": getattr(message.usage, "output_tokens", 0),
                }

            return result

        except httpx.TimeoutException as e:
            error_msg = f"Request timed out after {timeout} seconds: {str(e)}"
            print(error_msg)
            result["error"] = error_msg

        except anthropic.APIError as e:
            # Handle rate limiting or server errors that might benefit from retries
            if hasattr(e, "status_code") and e.status_code in (429, 500, 502, 503, 504):
                error_msg = f"API error (status {e.status_code}): {str(e)}"
                print(error_msg)
                result["error"] = error_msg
            else:
                # Don't retry client errors or other API errors
                error_msg = f"API error: {str(e)}"
                print(error_msg)
                result["error"] = error_msg
                return result

        except Exception as e:
            # Don't retry other exceptions
            error_msg = f"Unexpected error: {str(e)}"
            print(error_msg)
            result["error"] = error_msg
            return result

        # If we reach here, we should retry
        retries += 1
        if retries <= max_retries:
            print(
                f"Retrying request ({retries}/{max_retries}) after {current_delay} seconds..."
            )
            time.sleep(current_delay)
            # Exponential backoff with jitter
            current_delay = min(current_delay * 2, max_retry_delay)
        else:
            print(f"Maximum retries ({max_retries}) reached. Giving up.")

    return result


def generate_response_with_extended_thinking(
    prompt,
    max_tokens=32000,
    thinking_budget_tokens=16000,
    timeout=60,
    retry_delay=1,
    max_retries=3,
    max_retry_delay=10,
    model="claude-3-7-sonnet-latest",
):
    """
    Generate a response from Claude with extended thinking capabilities, error handling, and retries.

    Extended thinking allows Claude to show its step-by-step reasoning process before delivering
    the final answer, which can improve response quality for complex problems.

    Note: When using extended thinking, the temperature is automatically set to 1.0 as required by
    the Anthropic API. This parameter cannot be modified.

    Args:
        prompt: The prompt to send to Claude
        max_tokens: Maximum number of tokens to generate (must be greater than thinking_budget_tokens)
        thinking_budget_tokens: Maximum tokens for Claude's internal reasoning process
        timeout: Timeout for the request in seconds
        retry_delay: Initial delay between retries in seconds
        max_retries: Maximum number of retries
        max_retry_delay: Maximum delay between retries in seconds
        model: Model to use for generation (default: "claude-3-7-sonnet-latest")

    Returns:
        Dictionary containing:
            - 'success': Boolean indicating if the request was successful
            - 'content': Generated response text if successful
            - 'thinking': Claude's reasoning process if successful
            - 'error': Error message if unsuccessful
    """
    if thinking_budget_tokens >= max_tokens:
        raise ValueError("thinking_budget_tokens must be less than max_tokens")

    result = {"success": False, "content": None, "thinking": None, "error": None}

    retries = 0
    current_delay = retry_delay

    while retries <= max_retries:
        try:
            client = get_client(
                timeout=timeout, max_retries=0
            )  # Handle retries manually

            # Split the prompt to separate system instructions from transcript content
            # Assuming the prompt format is consistent and contains transcript content
            # that can be identified and separated

            # Extract transcript content from the prompt if it exists
            transcript_content = None
            user_query = prompt

            # Check if prompt contains a transcript section (simple check for demonstration)
            # In a real implementation, you might need a more sophisticated way to identify the transcript
            if "TRANSCRIPT:" in prompt:
                parts = prompt.split("TRANSCRIPT:", 1)
                user_query = parts[0].strip()
                if len(parts) > 1:
                    transcript_content = "TRANSCRIPT:" + parts[1]

            # Prepare the messages with caching if transcript content exists
            system_messages = [
                {
                    "type": "text",
                    "text": "You are an advanced assistant designed to help a forensic psychiatrist. Your task is to analyze and objectively document case information in a formal clinical style, maintaining professional psychiatric documentation standards. Distinguish between information from the subject and objective findings. Report specific details such as dates, frequencies, dosages, and other relevant clinical data. Document without emotional language or judgment.",
                }
            ]

            # Add transcript content with cache_control if it exists
            if transcript_content:
                system_messages.append(
                    {
                        "type": "text",
                        "text": transcript_content,
                        "cache_control": {"type": "ephemeral"},
                    }
                )

                # Use only the user query part for the user message
                user_message = user_query
            else:
                # If no transcript was detected, use the entire prompt
                user_message = prompt

            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=1.0,  # Always use 1.0 for extended thinking as required by the API
                system=system_messages,
                messages=[{"role": "user", "content": user_message}],
                timeout=timeout,  # Apply timeout at the method level for consistency
                thinking={"type": "enabled", "budget_tokens": thinking_budget_tokens},
            )

            result["success"] = True

            # Extract thinking and text content from the response
            for content_block in message.content:
                if content_block.type == "thinking":
                    result["thinking"] = content_block.thinking
                elif content_block.type == "text":
                    result["content"] = content_block.text

            # Add cache usage information if available
            if hasattr(message, "usage"):
                result["cache_info"] = {
                    "cache_creation_input_tokens": getattr(
                        message.usage, "cache_creation_input_tokens", 0
                    ),
                    "cache_read_input_tokens": getattr(
                        message.usage, "cache_read_input_tokens", 0
                    ),
                    "input_tokens": getattr(message.usage, "input_tokens", 0),
                    "output_tokens": getattr(message.usage, "output_tokens", 0),
                }

            return result

        except httpx.TimeoutException as e:
            error_msg = f"Request timed out after {timeout} seconds: {str(e)}"
            print(error_msg)
            result["error"] = error_msg

        except anthropic.APIError as e:
            # Handle rate limiting or server errors that might benefit from retries
            if hasattr(e, "status_code") and e.status_code in (429, 500, 502, 503, 504):
                error_msg = f"API error (status {e.status_code}): {str(e)}"
                print(error_msg)
                result["error"] = error_msg
            else:
                # Don't retry client errors or other API errors
                error_msg = f"API error: {str(e)}"
                print(error_msg)
                result["error"] = error_msg
                return result

        except Exception as e:
            # Don't retry other exceptions
            error_msg = f"Unexpected error: {str(e)}"
            print(error_msg)
            result["error"] = error_msg
            return result

        # If we reach here, we should retry
        retries += 1
        if retries <= max_retries:
            print(
                f"Retrying request ({retries}/{max_retries}) after {current_delay} seconds..."
            )
            time.sleep(current_delay)
            # Exponential backoff with jitter
            current_delay = min(current_delay * 2, max_retry_delay)
        else:
            print(f"Maximum retries ({max_retries}) reached. Giving up.")

    return result


def generate_response_with_pdf(
    prompt_text: str,
    pdf_file_path: str,
    max_tokens=32000,
    thinking_budget_tokens=16000,
    temperature=1.0,  # Set default temperature to 1.0 for extended thinking
    timeout=120,
    retry_delay=1,
    max_retries=3,
    max_retry_delay=10,
    model="claude-3-7-sonnet-latest",
):
    """
    Generate a response from Claude with PDF input and extended thinking capabilities.

    Uses Anthropic's native PDF handling to process PDF files directly and
    extended thinking for improved reasoning on complex tasks.

    Args:
        prompt_text: Text prompt to guide Claude's analysis of the PDF
        pdf_file_path: Path to the PDF file to be analyzed
        max_tokens: Maximum number of tokens to generate (must be greater than thinking_budget_tokens)
        thinking_budget_tokens: Maximum tokens for Claude's internal reasoning process
        temperature: Temperature for response generation (must be 1.0 when using extended thinking)
        timeout: Timeout for the request in seconds
        retry_delay: Initial delay between retries in seconds
        max_retries: Maximum number of retries
        max_retry_delay: Maximum delay between retries in seconds
        model: Model to use for generation (default: "claude-3-7-sonnet-latest")

    Returns:
        Dictionary containing:
            - 'success': Boolean indicating if the request was successful
            - 'content': Generated response text if successful
            - 'thinking': Claude's reasoning process if successful
            - 'error': Error message if unsuccessful
    """
    if thinking_budget_tokens >= max_tokens:
        raise ValueError("thinking_budget_tokens must be less than max_tokens")

    result = {"success": False, "content": None, "thinking": None, "error": None}

    retries = 0
    current_delay = retry_delay

    while retries <= max_retries:
        try:
            client = get_client(
                timeout=timeout, max_retries=0
            )  # Handle retries manually

            # Prepare the system messages
            system_messages = [
                {
                    "type": "text",
                    "text": "You are an advanced assistant designed to help a forensic psychiatrist. Your task is to analyze and objectively document case information in a formal clinical style, maintaining professional psychiatric documentation standards. Distinguish between information from the subject and objective findings. Report specific details such as dates, frequencies, dosages, and other relevant clinical data. Document without emotional language or judgment.",
                }
            ]

            # Open and read the PDF file, then encode as base64
            with open(pdf_file_path, "rb") as pdf_file:
                pdf_content = pdf_file.read()
                pdf_base64 = base64.b64encode(pdf_content).decode("utf-8")

            # Create the message with PDF attachment and extended thinking
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=1.0,  # Always use temperature 1.0 with extended thinking
                system=system_messages,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text},
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_base64,
                                },
                            },
                        ],
                    }
                ],
                timeout=timeout,
                thinking={"type": "enabled", "budget_tokens": thinking_budget_tokens},
            )

            result["success"] = True

            # Extract thinking and text content from the response
            for content_block in message.content:
                if content_block.type == "thinking":
                    result["thinking"] = content_block.thinking
                elif content_block.type == "text":
                    result["content"] = content_block.text

            # Add usage information if available
            if hasattr(message, "usage"):
                result["usage_info"] = {
                    "input_tokens": getattr(message.usage, "input_tokens", 0),
                    "output_tokens": getattr(message.usage, "output_tokens", 0),
                }

            return result

        except httpx.TimeoutException as e:
            error_msg = f"Request timed out after {timeout} seconds: {str(e)}"
            print(error_msg)
            result["error"] = error_msg

        except anthropic.APIError as e:
            # Handle rate limiting or server errors that might benefit from retries
            if hasattr(e, "status_code") and e.status_code in (429, 500, 502, 503, 504):
                error_msg = f"API error (status {e.status_code}): {str(e)}"
                print(error_msg)
                result["error"] = error_msg
            else:
                # Don't retry client errors or other API errors
                error_msg = f"API error: {str(e)}"
                print(error_msg)
                result["error"] = error_msg
                return result

        except Exception as e:
            # Don't retry other exceptions
            error_msg = f"Unexpected error: {str(e)}"
            print(error_msg)
            result["error"] = error_msg
            return result

        # If we reach here, we should retry
        retries += 1
        if retries <= max_retries:
            print(
                f"Retrying request ({retries}/{max_retries}) after {current_delay} seconds..."
            )
            time.sleep(current_delay)
            # Exponential backoff with jitter
            current_delay = min(current_delay * 2, max_retry_delay)
        else:
            print(f"Maximum retries ({max_retries}) reached. Giving up.")

    return result


def combine_transcript_with_fragments(
    transcript_text: str, fragments: List[str]
) -> List[str]:
    """
    Combines transcript text with template fragments to create complete prompts for LLM processing.

    Args:
        transcript_text: The full text of the transcript file
        fragments: List of template fragments generated from markdown sections

    Returns:
        List of complete prompts, each containing the transcript and a template fragment
    """
    # Wrap transcript text with tags
    wrapped_transcript = f"<transcript>\n{transcript_text}\n</transcript>"

    # Combine each fragment with the transcript
    complete_prompts = []
    for fragment in fragments:
        # Combine the fragment with the transcript
        complete_prompt = f"{wrapped_transcript}\n\n{fragment}"
        complete_prompts.append(complete_prompt)

    return complete_prompts
