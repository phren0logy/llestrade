"""
Utility functions and classes for interacting with the Anthropic Claude API.
Provides a more structured approach to LLM connections and prompt management.
"""

import base64
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import anthropic
from anthropic.types import ContentBlockDeltaEvent, ContentBlockParam
from dotenv import load_dotenv


class LLMClient:
    """
    A wrapper class for Anthropic's Claude API client with enhanced functionality.
    Provides consistent error handling, retry logic, and specialized response generation methods.
    """

    def __init__(
        self,
        timeout: float = 60.0,
        max_retries: int = 2,
        thinking_budget_tokens: int = 16000,
        default_system_prompt: Optional[str] = None,
    ):
        """
        Initialize the LLM client wrapper.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for API requests
            thinking_budget_tokens: Budget for "thinking" tokens in extended thinking mode
            default_system_prompt: Default system prompt to use when none is provided

        Raises:
            ValueError: If the ANTHROPIC_API_KEY environment variable is not set
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.thinking_budget_tokens = thinking_budget_tokens

        # Set default system prompt if not provided
        if default_system_prompt is None:
            self.default_system_prompt = "You are an advanced assistant designed to help a forensic psychiatrist. Your task is to analyze and objectively document case information in a formal clinical style, maintaining professional psychiatric documentation standards. Distinguish between information from the subject and objective findings. Report specific details such as dates, frequencies, dosages, and other relevant clinical data. Document without emotional language or judgment."
        else:
            self.default_system_prompt = default_system_prompt

        self.client = self._get_client()

    def _get_client(self) -> anthropic.Anthropic:
        """
        Initialize the Anthropic client with error handling.

        Returns:
            Initialized Anthropic client

        Raises:
            ValueError: If the ANTHROPIC_API_KEY environment variable is not set
        """
        # Load environment variables from .env file if not already loaded
        # This provides a fallback if config.setup_environment_variables() hasn't been called
        env_path = Path(".") / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            # Try to use template if .env doesn't exist
            template_path = Path(".") / "config.template.env"
            if template_path.exists():
                load_dotenv(template_path)

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable not set. Please create an .env file with your API key."
            )

        return anthropic.Anthropic(
            api_key=api_key,
            timeout=self.timeout,
            max_retries=self.max_retries,
            default_headers={
                "anthropic-version": "2023-06-01"
            },  # Ensure using most recent version
        )

    def generate_response(
        self,
        prompt_text: str,
        model: str = "claude-3-7-sonnet-20250219",
        max_tokens: int = 32000,
        temperature: float = 0.0,  # Default is 0.0 for non-thinking methods
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Claude for a given prompt.

        Args:
            prompt_text: The prompt to send to Claude
            model: The Claude model to use (defaults to claude-3-7-sonnet-20250219)
            max_tokens: Maximum number of tokens in the response
            temperature: Temperature parameter (randomness)
            system_prompt: Optional system prompt to set context

        Returns:
            Dictionary with response information
        """
        try:
            message_params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt_text}],
            }

            # Use the default system prompt if none is provided
            if system_prompt is None:
                message_params["system"] = self.default_system_prompt
            else:
                message_params["system"] = system_prompt

            # Create the message
            response = self.client.messages.create(
                **message_params,
                timeout=self.timeout,  # Explicitly set timeout on API request
            )

            # Extract content from response
            content = ""
            has_redacted_thinking = False

            for block in response.content:
                if (
                    block.type == "text"
                    and hasattr(block, "text")
                    and block.text is not None
                ):
                    content += block.text
                elif block.type == "redacted_thinking" and hasattr(block, "data"):
                    has_redacted_thinking = True

            # Construct the result
            result = {
                "success": True,
                "content": content,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }

            # If we had redacted thinking (unusual for standard responses), note it
            if has_redacted_thinking:
                result["redacted_thinking_present"] = True

            return result

        except anthropic.APIError as e:
            logging.error(f"Anthropic API error: {str(e)}")
            return {
                "success": False,
                "error": f"API error: {str(e)}",
                "content": None,
            }

        except Exception as e:
            logging.error(f"Unexpected error: {str(e)}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "content": None,
            }

    def generate_response_with_pdf(
        self,
        prompt_text: str,
        pdf_file_path: str,
        model: str = "claude-3-7-sonnet-20250219",
        max_tokens: int = 32000,
        temperature: float = 0.0,  # Default is 0.0 for non-thinking methods
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Claude for a given prompt and PDF file.

        Args:
            prompt_text: The prompt to send to Claude
            pdf_file_path: Path to the PDF file to analyze
            model: The Claude model to use
            max_tokens: Maximum number of tokens in the response
            temperature: Temperature parameter (randomness)
            system_prompt: Optional system prompt to set context

        Returns:
            Dictionary with response information
        """
        try:
            # Verify the PDF file exists
            if not os.path.exists(pdf_file_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_file_path}")

            # Read the PDF file
            with open(pdf_file_path, "rb") as f:
                pdf_data = f.read()

            # Prepare the messages with the PDF attachment
            message_params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text},
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": base64.b64encode(pdf_data).decode("utf-8"),
                                },
                            },
                        ],
                    }
                ],
            }

            # Use the default system prompt if none is provided
            if system_prompt is None:
                message_params["system"] = self.default_system_prompt
            else:
                message_params["system"] = system_prompt

            # Create the message
            response = self.client.messages.create(
                **message_params,
                timeout=self.timeout,  # Explicitly set timeout on API request
            )

            # Extract the response content
            content = ""
            for block in response.content:
                if (
                    block.type == "text"
                    and hasattr(block, "text")
                    and block.text is not None
                ):
                    content += block.text

            # Construct the result
            result = {
                "success": True,
                "content": content,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }

            return result

        except anthropic.APIError as e:
            logging.error(f"Anthropic API error with PDF: {str(e)}")
            return {
                "success": False,
                "error": f"API error: {str(e)}",
                "content": None,
            }

        except Exception as e:
            logging.error(f"Unexpected error with PDF: {str(e)}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "content": None,
            }

    def generate_response_with_extended_thinking(
        self,
        prompt_text: str,
        model: str = "claude-3-7-sonnet-20250219",
        max_tokens: int = 32000,
        temperature: float = 1.0,  # Fixed at 1.0 as required by Anthropic for thinking
        system_prompt: Optional[str] = None,
        thinking_budget_tokens: int = 16000,
    ) -> Dict[str, Any]:
        """
        Generate a response from Claude using extended thinking mode.

        Args:
            prompt_text: The prompt to send to Claude
            model: The Claude model to use
            max_tokens: Maximum number of tokens in the response
            temperature: Temperature parameter (randomness)
            system_prompt: Optional system prompt to set context
            thinking_budget_tokens: Override for thinking token budget (defaults to instance setting)

        Returns:
            Dictionary with response information including thinking and final response
        """
        try:
            # Use instance default if not specified
            if thinking_budget_tokens is None:
                thinking_budget_tokens = self.thinking_budget_tokens

            # Ensure thinking budget is always less than max_tokens
            if thinking_budget_tokens >= max_tokens:
                thinking_budget_tokens = max_tokens - 1000

            # Prepare message parameters with thinking enabled
            message_params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 1.0,  # Always 1.0 for thinking, regardless of parameter
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": thinking_budget_tokens,
                },
                "messages": [{"role": "user", "content": prompt_text}],
            }

            # Use the default system prompt if none is provided
            if system_prompt is None:
                message_params["system"] = self.default_system_prompt
            else:
                message_params["system"] = system_prompt

            # Set up for capturing thinking output if budget allows
            thinking_output = ""

            # Create the message
            response = self.client.messages.create(
                **message_params,
                timeout=self.timeout,  # Explicitly set timeout on API request
            )

            # Extract content and thinking from response
            content = ""
            thinking = ""
            has_redacted_thinking = False

            for block in response.content:
                if (
                    block.type == "text"
                    and hasattr(block, "text")
                    and block.text is not None
                ):
                    content += block.text
                elif (
                    block.type == "thinking"
                    and hasattr(block, "thinking")
                    and block.thinking is not None
                ):
                    thinking += block.thinking
                elif block.type == "redacted_thinking" and hasattr(block, "data"):
                    has_redacted_thinking = True

            # Add note about redacted thinking if present
            if has_redacted_thinking:
                redacted_note = "\n\n[NOTE: Some of Claude's thinking process was flagged by safety systems and encrypted. This doesn't affect the quality of the response, but means some reasoning steps are not visible in this output.]\n\n"
                if thinking:
                    thinking += redacted_note
                else:
                    thinking = redacted_note

            # Construct the result
            result = {
                "success": True,
                "content": content,
                "thinking": thinking,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }

            return result

        except anthropic.APIError as e:
            logging.error(f"Anthropic API error in extended thinking: {str(e)}")
            return {
                "success": False,
                "error": f"API error: {str(e)}",
                "content": None,
                "thinking": None,
            }

        except Exception as e:
            logging.error(f"Unexpected error in extended thinking: {str(e)}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "content": None,
                "thinking": None,
            }

    def generate_response_with_pdf_and_thinking(
        self,
        prompt_text: str,
        pdf_file_path: str,
        model: str = "claude-3-7-sonnet-20250219",
        max_tokens: int = 32000,
        temperature: float = 1.0,  # Fixed at 1.0 as required by Anthropic for thinking
        system_prompt: Optional[str] = None,
        thinking_budget_tokens: int = 16000,
    ) -> Dict[str, Any]:
        """
        Generate a response from Claude for a given prompt and PDF file with extended thinking.

        This method combines PDF handling with extended thinking capabilities.

        Args:
            prompt_text: The prompt to send to Claude
            pdf_file_path: Path to the PDF file to analyze
            model: The Claude model to use
            max_tokens: Maximum number of tokens in the response
            temperature: Temperature parameter (randomness)
            system_prompt: Optional system prompt to set context
            thinking_budget_tokens: Override for thinking token budget (defaults to instance setting)

        Returns:
            Dictionary with response information including thinking and final response
        """
        try:
            # Use instance default if not specified
            if thinking_budget_tokens is None:
                thinking_budget_tokens = self.thinking_budget_tokens

            # Ensure thinking budget is always less than max_tokens
            if thinking_budget_tokens >= max_tokens:
                thinking_budget_tokens = max_tokens - 8000

            # Verify the PDF file exists
            if not os.path.exists(pdf_file_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_file_path}")

            # Read the PDF file
            with open(pdf_file_path, "rb") as f:
                pdf_data = f.read()

            # Prepare the messages with the PDF attachment and thinking enabled
            message_params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 1.0,  # Always 1.0 for thinking, regardless of parameter
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": thinking_budget_tokens,
                },
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text},
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": base64.b64encode(pdf_data).decode("utf-8"),
                                },
                            },
                        ],
                    }
                ],
            }

            # Use the default system prompt if none is provided
            if system_prompt is None:
                message_params["system"] = self.default_system_prompt
            else:
                message_params["system"] = system_prompt

            # Create the message
            response = self.client.messages.create(
                **message_params,
                timeout=self.timeout,  # Explicitly set timeout on API request
            )

            # Extract content and thinking from response
            content = ""
            thinking = ""
            has_redacted_thinking = False

            for block in response.content:
                if (
                    block.type == "text"
                    and hasattr(block, "text")
                    and block.text is not None
                ):
                    content += block.text
                elif (
                    block.type == "thinking"
                    and hasattr(block, "thinking")
                    and block.thinking is not None
                ):
                    thinking += block.thinking
                elif block.type == "redacted_thinking" and hasattr(block, "data"):
                    has_redacted_thinking = True

            # Add note about redacted thinking if present
            if has_redacted_thinking:
                redacted_note = "\n\n[NOTE: Some of Claude's thinking process was flagged by safety systems and encrypted. This doesn't affect the quality of the response, but means some reasoning steps are not visible in this output.]\n\n"
                if thinking:
                    thinking += redacted_note
                else:
                    thinking = redacted_note

            # Construct the result
            result = {
                "success": True,
                "content": content,
                "thinking": thinking,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }

            return result

        except anthropic.APIError as e:
            logging.error(f"Anthropic API error with PDF and thinking: {str(e)}")
            return {
                "success": False,
                "error": f"API error: {str(e)}",
                "content": None,
                "thinking": None,
            }

        except Exception as e:
            logging.error(f"Unexpected error in PDF processing with thinking: {str(e)}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "content": None,
                "thinking": None,
            }

    def generate_conversation_response(
        self,
        conversation_history: List[Dict[str, Any]],
        model: str = "claude-3-7-sonnet-20250219",
        max_tokens: int = 32000,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Claude based on a conversation history.

        Args:
            conversation_history: List of message objects with role and content
            model: The Claude model to use
            max_tokens: Maximum number of tokens in the response
            temperature: Temperature parameter (randomness)
            system_prompt: Optional system prompt to set context

        Returns:
            Dictionary with response information
        """
        try:
            message_params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": conversation_history,
            }

            # Use the default system prompt if none is provided
            if system_prompt is None:
                message_params["system"] = self.default_system_prompt
            else:
                message_params["system"] = system_prompt

            # Create the message
            response = self.client.messages.create(
                **message_params,
                timeout=self.timeout,  # Explicitly set timeout on API request
            )

            # Extract the response content with better type handling
            content = ""
            for block in response.content:
                if (
                    block.type == "text"
                    and hasattr(block, "text")
                    and block.text is not None
                ):
                    content += block.text

            # Construct the result
            result = {
                "success": True,
                "content": content,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }

            return result

        except anthropic.APIError as e:
            logging.error(f"Anthropic API error in conversation: {str(e)}")
            return {
                "success": False,
                "error": f"API error: {str(e)}",
                "content": None,
            }

        except Exception as e:
            logging.error(f"Unexpected error in conversation: {str(e)}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "content": None,
            }

    def stream_response(
        self,
        prompt: str,
        model: str = "claude-3-7-sonnet-20250219",
        max_tokens: int = 32000,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
        callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Stream a response from Claude for a given prompt.

        Args:
            prompt: The prompt to send to Claude
            model: The Claude model to use
            max_tokens: Maximum number of tokens in the response
            temperature: Temperature parameter (randomness)
            system_prompt: Optional system prompt to set context
            callback: Optional callback function to process streaming text

        Returns:
            Dictionary with final response information
        """
        try:
            message_params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            }

            # Use the default system prompt if none is provided
            if system_prompt is None:
                message_params["system"] = self.default_system_prompt
            else:
                message_params["system"] = system_prompt

            # Set up streaming connection
            with self.client.messages.stream(**message_params) as stream:
                accumulated_content = ""

                # Process the text stream
                for text in stream.text_stream:
                    accumulated_content += text
                    if callback:
                        callback(text)

                # Get final message with usage stats
                final_message = stream.get_final_message()

                # Construct the result
                result = {
                    "success": True,
                    "content": accumulated_content,
                    "usage": {
                        "input_tokens": final_message.usage.input_tokens,
                        "output_tokens": final_message.usage.output_tokens,
                    },
                }

                return result

        except anthropic.APIError as e:
            logging.error(f"Anthropic API error in streaming: {str(e)}")
            return {
                "success": False,
                "error": f"API error: {str(e)}",
                "content": None,
            }

        except Exception as e:
            logging.error(f"Unexpected error in streaming: {str(e)}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "content": None,
            }

    def count_tokens(
        self, messages: List[Dict[str, Any]], model: str = "claude-3-7-sonnet-20250219"
    ) -> Dict[str, Any]:
        """
        Count the number of tokens in a list of messages.

        Args:
            messages: List of message objects with role and content
            model: The Claude model to use

        Returns:
            Dictionary with token count information
        """
        try:
            response = self.client.messages.count_tokens(model=model, messages=messages)
            # Fix for newer Anthropic versions (>=0.49.0) where response structure changed
            # The response is now a MessageTokensCount object with input_tokens directly available
            if hasattr(response, "input_tokens"):
                return {"success": True, "token_count": response.input_tokens}
            # Fallback to older API structure if available
            elif hasattr(response, "usage") and hasattr(response.usage, "input_tokens"):
                return {"success": True, "token_count": response.usage.input_tokens}
            else:
                # Last resort - try to access as a dictionary
                try:
                    if isinstance(response, dict) and "input_tokens" in response:
                        return {
                            "success": True,
                            "token_count": response["input_tokens"],
                        }
                    elif (
                        isinstance(response, dict)
                        and "usage" in response
                        and "input_tokens" in response["usage"]
                    ):
                        return {
                            "success": True,
                            "token_count": response["usage"]["input_tokens"],
                        }
                except:
                    pass

                # Could not determine token count structure
                logging.error(
                    f"Could not determine token count from response structure: {response}"
                )
                return {
                    "success": False,
                    "error": "Unknown response structure for token counting",
                }
        except Exception as e:
            logging.error(f"Token counting error: {str(e)}")
            return {"success": False, "error": f"Token counting error: {str(e)}"}

    def generate_response_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        model: str = "claude-3-7-sonnet-20250219",
        max_tokens: int = 32000,
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response from Claude with tool use capabilities.

        Args:
            prompt: The prompt to send to Claude
            tools: List of tool definitions to make available to Claude
            model: The Claude model to use
            max_tokens: Maximum number of tokens in the response
            temperature: Temperature parameter (randomness)
            system_prompt: Optional system prompt to set context

        Returns:
            Dictionary with response information including tool use
        """
        try:
            message_params = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
                "tools": tools,
            }

            # Use the default system prompt if none is provided
            if system_prompt is None:
                message_params["system"] = self.default_system_prompt
            else:
                message_params["system"] = system_prompt

            # Create the message
            response = self.client.messages.create(
                **message_params,
                timeout=self.timeout,  # Explicitly set timeout on API request
            )

            # Extract content from response including tool use blocks
            content = []
            for block in response.content:
                if block.type == "text":
                    content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    content.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )

            # Construct the result
            result = {
                "success": True,
                "content": content,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            }

            return result

        except anthropic.APIError as e:
            logging.error(f"Anthropic API error with tools: {str(e)}")
            return {
                "success": False,
                "error": f"API error: {str(e)}",
                "content": None,
            }

        except Exception as e:
            logging.error(f"Unexpected error with tools: {str(e)}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "content": None,
            }


def combine_transcript_with_fragments(transcript_text: str, fragment: str) -> str:
    """
    Combine transcript text with a template fragment.

    Args:
        transcript_text: The transcript text to combine with the fragment
        fragment: Template fragment as a string

    Returns:
        Combined prompt as a string
    """
    # Add the fragment first, then the transcript with proper wrapping
    combined = f"{fragment}\n\n<transcript>\n{transcript_text}\n</transcript>"

    return combined
