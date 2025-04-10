#!/usr/bin/env python
"""
Verification script for LLM API connection testing.
This script tests both Anthropic and Gemini API connections.
"""

import logging
import os
import sys
import time
import traceback

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def test_anthropic_connection():
    """Test connection to Anthropic API."""
    print("\n=== Testing Anthropic API Connection ===\n")

    try:
        # Check for API key
        from dotenv import load_dotenv

        load_dotenv()
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("❌ No Anthropic API key found in environment variables")
            print("   Please set ANTHROPIC_API_KEY in your .env file")
            return False

        # Check if the API key is valid (not default or placeholder)
        if api_key in ["your_api_key_here", "sk-ant-", "sk-"]:
            print(
                "❌ API key appears to be a placeholder: ",
                api_key[:8] + "..." if len(api_key) > 8 else api_key,
            )
            print("   Please set a valid Anthropic API key in your .env file")
            return False

        # Test importing the Anthropic library
        try:
            import anthropic

            print("✅ Successfully imported Anthropic library")
        except ImportError:
            print("❌ Failed to import Anthropic library")
            print("   Try installing it with: uv pip install anthropic")
            return False

        # Test direct connection to API
        print("ℹ️ Testing direct Anthropic API connection...")
        try:
            start_time = time.time()
            client = anthropic.Client(api_key=api_key)

            # Try a simple message
            message = client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=100,
                messages=[
                    {
                        "role": "user",
                        "content": "Hello, Claude! Can you respond with 'API connection successful' if you can read this?",
                    }
                ],
                system="You are a helpful assistant.",
            )

            elapsed_time = time.time() - start_time

            # Check response
            content = (
                message.content[0].text
                if hasattr(message, "content") and message.content
                else "No content received"
            )
            if (
                "API connection successful" in content
                or "connection" in content.lower()
            ):
                print(
                    f"✅ Successfully connected to Anthropic API ({elapsed_time:.2f} seconds)"
                )
                print(f"   Response: {content[:100]}...")
                print(f"   Input tokens: {message.usage.input_tokens}")
                print(f"   Output tokens: {message.usage.output_tokens}")
                return True
            else:
                print(
                    f"⚠️ Connected but received unexpected response: {content[:100]}..."
                )
                print("   This may indicate a model behavior change")
                return True

        except Exception as e:
            print(f"❌ Failed to connect to Anthropic API: {str(e)}")
            print(f"   Error details: {traceback.format_exc()}")
            return False

    except Exception as e:
        print(f"❌ Unexpected error testing Anthropic connection: {str(e)}")
        print(f"   Error details: {traceback.format_exc()}")
        return False


def test_gemini_connection():
    """Test connection to Google Gemini API."""
    print("\n=== Testing Google Gemini API Connection ===\n")

    try:
        # Check for API key
        from dotenv import load_dotenv

        load_dotenv()
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("ℹ️ No Google API key found in environment variables")
            print("   Gemini is configured as a fallback option")
            return False

        # Check if the API key is valid (not default or placeholder)
        if api_key in ["your_api_key_here", "AIza"]:
            print(
                "❌ API key appears to be a placeholder: ",
                api_key[:8] + "..." if len(api_key) > 8 else api_key,
            )
            print("   Please set a valid Google API key in your .env file")
            return False

        # Test importing the Google library
        try:
            import google.generativeai as genai

            print("✅ Successfully imported Google Generative AI library")
        except ImportError:
            print("❌ Failed to import Google Generative AI library")
            print("   Try installing it with: uv pip install google-generativeai")
            return False

        # Test direct connection to API
        print("ℹ️ Testing direct Gemini API connection...")
        try:
            start_time = time.time()
            genai.configure(api_key=api_key)

            # Check available models
            models = genai.list_models()
            gemini_models = [m for m in models if "gemini" in m.name.lower()]

            if not gemini_models:
                print("❌ No Gemini models available with the provided API key")
                return False

            print(
                f"ℹ️ Available Gemini models: {', '.join([m.name for m in gemini_models[:3]])}"
            )

            # Use the first available Gemini model
            model = genai.GenerativeModel(gemini_models[0].name)

            # Try a simple generation
            response = model.generate_content(
                "Hello, Gemini! Can you respond with 'API connection successful' if you can read this?"
            )

            elapsed_time = time.time() - start_time

            # Check response
            content = response.text if hasattr(response, "text") else str(response)
            if (
                "API connection successful" in content
                or "connection" in content.lower()
            ):
                print(
                    f"✅ Successfully connected to Gemini API ({elapsed_time:.2f} seconds)"
                )
                print(f"   Response: {content[:100]}...")
                return True
            else:
                print(
                    f"⚠️ Connected but received unexpected response: {content[:100]}..."
                )
                print("   This may indicate a model behavior change")
                return True

        except Exception as e:
            print(f"❌ Failed to connect to Gemini API: {str(e)}")
            print(f"   Error details: {traceback.format_exc()}")
            return False

    except Exception as e:
        print(f"❌ Unexpected error testing Gemini connection: {str(e)}")
        print(f"   Error details: {traceback.format_exc()}")
        return False


def test_llm_client():
    """Test the LLMClient from our custom implementation."""
    print("\n=== Testing Custom LLM Client ===\n")

    try:
        # Import the LLM client
        try:
            from llm_utils import AnthropicClient, GeminiClient, LLMClient

            print("✅ Successfully imported custom LLM client classes")
        except ImportError as e:
            print(f"❌ Failed to import custom LLM client: {str(e)}")
            return False

        # Initialize clients
        print("ℹ️ Testing AnthropicClient initialization...")
        try:
            anthropic_client = AnthropicClient()
            if anthropic_client.is_initialized:
                print("✅ Successfully initialized AnthropicClient")
            else:
                print("❌ AnthropicClient failed to initialize properly")
        except Exception as e:
            print(f"❌ Error initializing AnthropicClient: {str(e)}")

        print("ℹ️ Testing GeminiClient initialization...")
        try:
            gemini_client = GeminiClient()
            if gemini_client.is_initialized:
                print("✅ Successfully initialized GeminiClient")
            else:
                print("❌ GeminiClient failed to initialize properly")
        except Exception as e:
            print(f"❌ Error initializing GeminiClient: {str(e)}")

        print("ℹ️ Testing main LLMClient (default/factory) initialization...")
        try:
            llm_client = LLMClient()
            initialized_providers = []

            if (
                hasattr(llm_client, "anthropic_initialized")
                and llm_client.anthropic_initialized
            ):
                initialized_providers.append("Anthropic")

            if (
                hasattr(llm_client, "gemini_initialized")
                and llm_client.gemini_initialized
            ):
                initialized_providers.append("Gemini")

            if initialized_providers:
                print(
                    f"✅ Successfully initialized LLMClient with providers: {', '.join(initialized_providers)}"
                )
            else:
                print("❌ LLMClient initialized but no providers are available")
                return False

        except Exception as e:
            print(f"❌ Error initializing main LLMClient: {str(e)}")
            return False

        # Test token counting
        print("\nℹ️ Testing token counting...")
        try:
            test_text = "This is a test message to count tokens."
            result = llm_client.count_tokens(text=test_text)
            if result["success"]:
                print(f"✅ Successfully counted tokens: {result['token_count']}")
            else:
                print(
                    f"❌ Failed to count tokens: {result.get('error', 'Unknown error')}"
                )

        except Exception as e:
            print(f"❌ Error testing token counting: {str(e)}")

        # Test short generation
        print("\nℹ️ Testing short text generation...")
        try:
            prompt = "Please respond with a single sentence describing what an LLM is."
            result = llm_client.generate_response(
                prompt_text=prompt,
                system_prompt="You are a helpful assistant.",
                temperature=0.1,
            )

            if result["success"]:
                print("✅ Successfully generated text response")
                print(f"   Provider used: {result.get('provider', 'unknown')}")
                print(f"   Response: {result['content'][:100]}...")
                if "usage" in result:
                    print(
                        f"   Input tokens: {result['usage'].get('input_tokens', 'unknown')}"
                    )
                    print(
                        f"   Output tokens: {result['usage'].get('output_tokens', 'unknown')}"
                    )
            else:
                print(
                    f"❌ Failed to generate text: {result.get('error', 'Unknown error')}"
                )
                return False

        except Exception as e:
            print(f"❌ Error testing text generation: {str(e)}")
            return False

        return True

    except Exception as e:
        print(f"❌ Unexpected error testing LLM client: {str(e)}")
        print(f"   Error details: {traceback.format_exc()}")
        return False


def run_network_diagnostics():
    """Run basic network diagnostics."""
    print("\n=== Network Diagnostics ===\n")

    try:
        import socket

        import requests

        # Test internet connectivity
        print("ℹ️ Testing internet connectivity...")
        try:
            # First test DNS resolution
            socket.gethostbyname("anthropic.com")
            socket.gethostbyname("google.com")
            print("✅ DNS resolution working")

            # Now test HTTP connectivity
            response = requests.get("https://www.google.com", timeout=5)
            if response.status_code == 200:
                print("✅ HTTP connectivity working")
            else:
                print(f"⚠️ HTTP connectivity issues: status code {response.status_code}")

        except socket.gaierror:
            print("❌ DNS resolution failed - check your internet connection")
            return False
        except requests.exceptions.RequestException as e:
            print(f"❌ HTTP connectivity failed: {str(e)}")
            return False

        # Test API endpoints
        print("\nℹ️ Testing API endpoints connectivity...")
        try:
            # Try connecting to Anthropic API endpoint (without authentication)
            response = requests.get("https://api.anthropic.com/v1/models", timeout=5)
            if response.status_code in [401, 403]:  # Unauthorized is expected
                print("✅ Anthropic API endpoint reachable")
            elif response.status_code >= 500:
                print(f"⚠️ Anthropic API having server issues: {response.status_code}")
            else:
                print(f"ℹ️ Anthropic API returned status code: {response.status_code}")

        except requests.exceptions.RequestException as e:
            print(f"❌ Could not reach Anthropic API endpoint: {str(e)}")

        return True

    except Exception as e:
        print(f"❌ Error running network diagnostics: {str(e)}")
        return False


def run_all_tests():
    """Run all diagnostics and tests."""
    print("=== LLM API Connectivity Test ===")
    print("Running comprehensive diagnostics...\n")

    # Test network first
    network_ok = run_network_diagnostics()
    if not network_ok:
        print("\n⚠️ Network issues detected. API tests may fail.")

    # Test individual providers
    anthropic_ok = test_anthropic_connection()
    gemini_ok = test_gemini_connection()

    # Test our client implementation
    client_ok = test_llm_client()

    # Print summary
    print("\n=== Test Summary ===\n")
    print(f"Network Diagnostics: {'✅ PASS' if network_ok else '⚠️ ISSUES'}")
    print(f"Anthropic API: {'✅ PASS' if anthropic_ok else '❌ FAIL'}")
    print(f"Gemini API: {'✅ PASS' if gemini_ok else '⚠️ NOT CONFIGURED'}")
    print(f"Custom LLM Client: {'✅ PASS' if client_ok else '❌ FAIL'}")

    # Final verdict
    if anthropic_ok or gemini_ok:
        print("\n✅ At least one LLM provider is working!")
        if client_ok:
            print("✅ You should be able to use the application normally.")
        else:
            print("⚠️ Direct API access works but the custom client has issues.")
    else:
        print(
            "\n❌ No LLM providers are working. Please check your API keys and connection."
        )

    return anthropic_ok or gemini_ok


if __name__ == "__main__":
    run_all_tests()
