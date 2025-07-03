#!/usr/bin/env python
"""
Setup script for Report Drafter environment configuration.
This helps users set up their API keys and verify connectivity.
"""

import getpass
import os
import shutil
from pathlib import Path


def setup_api_keys():
    """Interactive setup of API keys in .env file."""
    print("\n=== API Key Configuration ===\n")

    # Check if .env file exists
    env_path = Path(".") / ".env"
    template_path = Path(".") / "config.template.env"

    # Create .env from template if it doesn't exist
    if not env_path.exists():
        if template_path.exists():
            print("Creating .env file from template...")
            shutil.copy(template_path, env_path)
        else:
            print("Creating new .env file...")
            with open(env_path, "w") as f:
                f.write("# Anthropic API Configuration\n")
                f.write("ANTHROPIC_API_KEY=\n\n")
                f.write("# Azure Document Intelligence API Configuration\n")
                f.write("AZURE_ENDPOINT=\n")
                f.write("AZURE_KEY=\n")

    # Read current .env content
    current_env = {}
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    current_env[key] = value

    # Ask for Anthropic API key
    print("\nAn Anthropic Claude API key is required for document summarization.")
    print("You can get one by signing up at: https://console.anthropic.com/\n")

    current_key = current_env.get("ANTHROPIC_API_KEY", "")
    masked_key = "not set"
    if current_key and current_key != "your_api_key_here":
        if len(current_key) > 8:
            masked_key = f"{current_key[:4]}...{current_key[-4:]}"

    print(f"Current Anthropic API key: {masked_key}")

    change_key = input("Would you like to change this key? (y/n): ").lower().strip()
    if change_key == "y":
        new_key = getpass.getpass("Enter your Anthropic API key: ")
        if new_key:
            current_env["ANTHROPIC_API_KEY"] = new_key
            print("Anthropic API key updated.")
        else:
            print("No key entered, keeping existing value.")

    # Ask for Azure keys if needed
    if "AZURE_ENDPOINT" in current_env or "AZURE_KEY" in current_env:
        print("\nAzure Document Intelligence API is optional for PDF processing.")
        change_azure = (
            input("Would you like to configure Azure API settings? (y/n): ")
            .lower()
            .strip()
        )

        if change_azure == "y":
            azure_endpoint = input("Enter Azure endpoint URL: ").strip()
            if azure_endpoint:
                current_env["AZURE_ENDPOINT"] = azure_endpoint

            azure_key = getpass.getpass("Enter Azure API key: ")
            if azure_key:
                current_env["AZURE_KEY"] = azure_key

    # Write updated .env file
    with open(env_path, "w") as f:
        f.write("# Anthropic API Configuration\n")
        f.write(f"ANTHROPIC_API_KEY={current_env.get('ANTHROPIC_API_KEY', '')}\n\n")
        f.write("# Azure Document Intelligence API Configuration\n")
        f.write(f"AZURE_ENDPOINT={current_env.get('AZURE_ENDPOINT', '')}\n")
        f.write(f"AZURE_KEY={current_env.get('AZURE_KEY', '')}\n")

    print("\nEnvironment configuration saved to .env file.")
    return True


def check_dependencies():
    """Check if required Python packages are installed."""
    print("\n=== Dependency Check ===\n")

    required_packages = {
        "anthropic": "LLM API client",
        "python-dotenv": "Environment variable management",
        "PyQt6": "User interface",
    }

    optional_packages = {
        "google.generativeai": "Google Gemini support (optional)",
        "azure.ai.formrecognizer": "Azure PDF processing (optional)",
    }

    # Check required packages
    missing_required = []
    for package, description in required_packages.items():
        package_name = package.split(".")[0]  # Get base package name
        try:
            __import__(package_name)
            print(f"✅ {package} - {description}")
        except ImportError:
            print(f"❌ {package} - {description} (MISSING)")
            missing_required.append(package_name)

    # Check optional packages
    print("\nOptional packages:")
    for package, description in optional_packages.items():
        package_name = package.split(".")[0]  # Get base package name
        try:
            __import__(package_name)
            print(f"✅ {package} - {description}")
        except ImportError:
            print(f"ℹ️ {package} - {description} (not installed)")

    # Provide installation instructions if packages are missing
    if missing_required:
        print("\nMissing required packages. Please install them with:")
        print(f"uv pip install {' '.join(missing_required)}")
        return False

    return True


def test_api_connectivity():
    """Test connectivity to the LLM APIs."""
    print("\n=== API Connectivity Test ===\n")

    # Check that environment variables are loaded
    try:
        # Ensure we're using the .env file values
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        print("❌ python-dotenv package not installed.")
        print("   Please install it with: pip install python-dotenv")
        return False

    # Check if the ANTHROPIC_API_KEY is set
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not anthropic_key or anthropic_key == "your_api_key_here":
        print("❌ ANTHROPIC_API_KEY is not set in the .env file.")
        print("   Please run the setup_api_keys() function first.")
        return False

    # Try to import and initialize the LLM client
    try:
        try:
            from llm import create_provider

            print("✅ Successfully imported create_provider")
        except ImportError as e:
            print(f"❌ Failed to import create_provider: {str(e)}")
            return False

        try:
            provider = create_provider(provider="auto")
            if provider:
                print("✅ Successfully initialized LLM provider")
            else:
                print("❌ LLM provider failed to initialize properly")
                return False
        except Exception as e:
            print(f"❌ Error initializing LLM client: {str(e)}")
            return False

        # Test API connectivity with a simple token count request
        try:
            response = provider.count_tokens(text="Test message to count tokens.")

            if response.get("success", False):
                provider_name = getattr(provider, "provider_name", "unknown")
                print(f"✅ Successfully connected to {provider_name.capitalize()} API")
                print(f"   Token count: {response.get('token_count', 'unknown')}")
                return True
            else:
                print(
                    f"❌ API request failed: {response.get('error', 'Unknown error')}"
                )
                return False

        except Exception as e:
            print(f"❌ Error making API request: {str(e)}")
            return False

    except Exception as e:
        import traceback

        print(f"❌ Unexpected error during API connectivity test: {str(e)}")
        print(traceback.format_exc())
        return False


def test_document_summarization():
    """Test actual document summarization."""
    print("\n=== Document Summarization Test ===\n")

    # Create a simple test document
    test_dir = "test_diagnostics"
    test_file = f"{test_dir}/test_doc.md"
    test_output = f"{test_dir}/test_summary.md"

    # Make sure directory exists
    import os

    if not os.path.exists(test_dir):
        os.makedirs(test_dir)

    # Create a simple test file
    test_content = """# Test Document

This is a simple test document to verify LLM summarization.

## Background
John Doe is a 35-year-old individual born on 1988-01-15.

## Education
- Bachelor of Science, 2010
- Master's Degree, 2012
"""

    # Write test file
    with open(test_file, "w") as f:
        f.write(test_content)
    print(f"Created test file at {test_file}")

    # Now try summarizing it directly
    try:
        print("Creating LLM client...")
        from llm import create_provider

        provider = create_provider(provider="auto")

        # Check provider information
        provider_name = getattr(provider, "provider_name", "unknown")
        if provider_name == "anthropic":
            print("Using Anthropic Claude for summarization")
            llm_provider = "Anthropic Claude"
        elif provider_name == "gemini":
            print("Using Google Gemini for summarization")
            llm_provider = "Google Gemini"
        else:
            print(f"Using {provider_name} provider for summarization")
            llm_provider = provider_name.capitalize() if provider_name else "Unknown"

        # Create prompt
        prompt = f"""
## Document Content
<document-content>
{test_content}
</document-content>

# Document Analysis Task

## Document Information
- **Subject Name**: John Doe
- **Date of Birth**: 1988-01-15
- **Document**: Test Document

## Instructions
Please analyze the document content above, wrapped in "document-content" tags, and provide a brief summary.
Include key facts about the subject, education, and other relevant information.

Keep your analysis focused on factual information directly stated in the document.
"""

        print(f"\nSending request to {llm_provider}...")
        print(f"Prompt length: {len(prompt)} characters")

        # Execute summarization
        response = provider.generate(
            prompt=prompt,
            system_prompt="You are analyzing a test document for John Doe.",
            temperature=0.1,
        )

        # Check response
        if response["success"]:
            print("✅ Successfully generated summary!")
            print(f"Response length: {len(response.get('content', ''))} characters")

            # Log token usage
            if "usage" in response:
                print(
                    f"Input tokens: {response['usage'].get('input_tokens', 'unknown')}"
                )
                print(
                    f"Output tokens: {response['usage'].get('output_tokens', 'unknown')}"
                )

            # Save the summary
            with open(test_output, "w") as f:
                f.write("# Test Summary\n\n")
                f.write(response.get("content", ""))

            print(f"Summary saved to {test_output}")
            return True
        else:
            print(
                f"❌ Failed to generate summary: {response.get('error', 'Unknown error')}"
            )
            return False

    except Exception as e:
        import traceback

        print(f"❌ Error during summarization test: {str(e)}")
        print(traceback.format_exc())
        return False


def main():
    """Run the setup process."""
    print("\n=== Report Drafter Environment Setup ===\n")

    # Step 1: Check dependencies
    if not check_dependencies():
        print("\nPlease install missing dependencies before continuing.")
        choice = input("Would you like to continue anyway? (y/n): ").lower().strip()
        if choice != "y":
            return

    # Step 2: Configure API keys
    if not setup_api_keys():
        print("\nAPI key setup failed. Please try again.")
        return

    # Step 3: Test API connectivity
    if not test_api_connectivity():
        print(
            "\n❌ API connectivity test failed. Please check your API key and try again."
        )
        print(
            "   You can run this setup script again or verify your network connectivity."
        )
        return

    # Step 4: Test document summarization
    print(
        "\nWould you like to run a document summarization test to verify the full workflow?"
    )
    choice = input("Run summarization test? (y/n): ").lower().strip()
    if choice == "y":
        if test_document_summarization():
            print("\n✅ Document summarization test was successful!")
        else:
            print(
                "\n❌ Document summarization test failed. This indicates an issue with the LLM summarization workflow."
            )
            print(
                "   The API connection test passed, but there's an issue when generating summaries."
            )
            print("   Check the error details above for more information.")
            return

    print(
        "\n✅ Setup completed successfully! The application should now work correctly."
    )
    print("\nSetup process complete.")


if __name__ == "__main__":
    main()
