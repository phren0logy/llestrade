#!/usr/bin/env python
"""
Diagnostic script for testing specific markdown files with LLM.
Allows processing one file at a time to identify issues.
"""

import logging
import os
import sys
import traceback
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def test_specific_file(file_path, output_dir=None):
    """Test summarizing one specific file."""
    if not os.path.exists(file_path):
        print(f"Error: File does not exist: {file_path}")
        return False

    print(f"\n=== Testing File Processing ===\n")
    print(f"File: {file_path}")

    # Setup output directory
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(file_path), "diagnosis")
    os.makedirs(output_dir, exist_ok=True)

    basename = os.path.splitext(os.path.basename(file_path))[0]
    output_file = os.path.join(output_dir, f"{basename}_diagnosis.md")

    print(f"Output will be saved to: {output_file}")

    # Check file stats
    try:
        file_size = os.path.getsize(file_path)
        print(f"File size: {file_size} bytes")

        if file_size == 0:
            print("Error: File is empty")
            return False

        if file_size > 10_000_000:  # 10MB
            print(f"Warning: File is very large ({file_size} bytes)")
    except Exception as e:
        print(f"Error checking file stats: {e}")
        return False

    # Try reading the file
    try:
        print("\nAttempting to read file...")
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        print(f"Successfully read file: {len(content)} characters")

        # Show file sample
        print("\nFile sample (first 200 chars):")
        print("-" * 40)
        print(content[:200])
        print("-" * 40)

    except UnicodeDecodeError:
        print("UTF-8 decoding failed, trying with latin-1 encoding...")
        try:
            with open(file_path, "r", encoding="latin-1") as f:
                content = f.read()
            print(
                f"Successfully read file with latin-1 encoding: {len(content)} characters"
            )
        except Exception as e:
            print(f"Error reading file with latin-1 encoding: {e}")
            return False
    except Exception as e:
        print(f"Error reading file: {e}")
        return False

    # Process with LLM
    try:
        print("\nInitializing LLM client...")
        from llm_utils import LLMClient

        client = LLMClient()

        # Test token counting
        print("\nCounting tokens...")
        token_result = client.count_tokens(text=content)
        if token_result["success"]:
            token_count = token_result["token_count"]
            print(f"Token count: {token_count}")

            if token_count > 30000:
                print(
                    f"Warning: File has {token_count} tokens, which exceeds recommended limits"
                )
                print("Consider chunking or shortening the file")
        else:
            print(
                f"Error counting tokens: {token_result.get('error', 'Unknown error')}"
            )
            # Estimate tokens based on characters
            estimated_tokens = len(content) // 4
            print(f"Estimated token count (based on characters): ~{estimated_tokens}")

        # Create a prompt
        print("\nCreating prompt...")
        system_prompt = "You are analyzing a document for a forensic psychology report."

        prompt = f"""
## Document Content
<document-content>
{content}
</document-content>

# Document Analysis Task

## Document Information
- **Subject Name**: Test Subject 
- **Date of Birth**: 1990-01-01

## Instructions
Please analyze the document content above, wrapped in "document-content" tags, and provide a summary.
Include only factual information directly stated in the document.
Keep your analysis brief and focused.
"""

        print(f"Created prompt: {len(prompt)} characters")

        # Generate summary
        print("\nSending request to LLM API...")
        start_import = __import__("time").time()

        response = client.generate_response(
            prompt_text=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
        )

        end_time = __import__("time").time()
        elapsed = end_time - start_import

        if response["success"]:
            print(f"\n✅ Successfully generated summary ({elapsed:.2f} seconds)")
            print(f"Summary length: {len(response['content'])} characters")

            if "usage" in response:
                print(
                    f"Input tokens: {response['usage'].get('input_tokens', 'unknown')}"
                )
                print(
                    f"Output tokens: {response['usage'].get('output_tokens', 'unknown')}"
                )

            # Write to file
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(f"# Diagnostic Summary for {basename}\n\n")
                f.write(response["content"])

            print(f"\nSummary saved to: {output_file}")
            return True
        else:
            print(
                f"\n❌ Failed to generate summary: {response.get('error', 'Unknown error')}"
            )
            return False

    except Exception as e:
        print(f"\n❌ Error in LLM processing: {str(e)}")
        print(traceback.format_exc())
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python test_diagnosis.py <path_to_markdown_file> [output_directory]"
        )
        sys.exit(1)

    file_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    success = test_specific_file(file_path, output_dir)

    if success:
        print("\n✅ File processed successfully!")
    else:
        print("\n❌ File processing failed!")
