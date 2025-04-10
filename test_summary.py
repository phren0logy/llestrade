#!/usr/bin/env python
"""
Test script for LLM summarization of a markdown file.
This can be used to diagnose issues with the summarization process.
"""

import logging
import os
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Ensure the current directory is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def create_test_markdown():
    """Create a simple test markdown file if none exists."""
    test_dir = Path("test_data")
    test_dir.mkdir(exist_ok=True)

    test_file = test_dir / "test_sample.md"

    if not test_file.exists():
        with open(test_file, "w") as f:
            f.write(
                """# Test Document

## Personal Information
John Doe is a 35-year-old male, born on 1988-01-15. He currently resides in Springfield.

## Medical History
- Diagnosed with hypertension in 2020
- Fractured right arm in 2015 following a bicycle accident
- History of seasonal allergies

## Education
- Bachelor's degree in Computer Science (2010)
- Master's degree in Information Systems (2012)

## Employment
- Software Developer at XYZ Corp (2012-2018)
- Senior Developer at ABC Inc (2018-present)

## Legal History
No significant legal issues reported.

## Family History
- Father (deceased, 2018) had history of heart disease
- Mother (68) alive and healthy
- One sister (33) with no significant health issues
"""
            )
        logging.info(f"Created test markdown file at {test_file}")

    return test_file


def test_summarization(markdown_file):
    """Test summarization of a markdown file."""
    try:
        from llm_utils import LLMClient

        logging.info("Imported LLMClient successfully")

        # Initialize LLM client
        client = LLMClient()
        logging.info("Initialized LLMClient")

        # Read the markdown file
        with open(markdown_file, "r") as f:
            content = f.read()
        logging.info(f"Read markdown file: {len(content)} characters")

        # Create a prompt
        prompt = f"""
## Document Content
<document-content>
{content}
</document-content>

# Document Analysis Task

## Document Information
- **Subject Name**: John Doe
- **Date of Birth**: 1988-01-15
- **Document**: Test document

## Case Background
This is a test document for API verification purposes.

## Instructions
Please analyze the document content above, wrapped in "document-content" tags, and provide a comprehensive summary that includes:

- Key facts and information about the subject
- Significant events and dates mentioned
- Family and romantic relationships
- Early childhood history
- Educational history
- Employment history
- Medical history
- Any notable statements or quotes
- A timeline of events in a markdown table format with columns for Date, Event, and Significance

## Timeline Instructions
- Create a timeline of events in a markdown table format with columns for Date, Event, and Significance
- Using the subject's date of birth (1988-01-15), calculate the subject's age at each event when relevant
- When exact dates aren't provided, estimate years when possible and mark them with "(est.)"
- Organize the timeline chronologically with the most recent events at the bottom
"""
        logging.info(f"Created prompt: {len(prompt)} characters")

        # Generate response
        logging.info("Calling LLM API...")
        response = client.generate_response(
            prompt_text=prompt,
            system_prompt="You are analyzing a test document.",
            temperature=0.1,
        )

        # Check response
        if response["success"]:
            output_file = Path("test_data") / "test_summary_result.md"
            with open(output_file, "w") as f:
                f.write(f"# Test Summary Result\n\n")
                f.write(response["content"])

            logging.info(
                f"✅ Successfully generated summary! Output saved to {output_file}"
            )
            logging.info(
                f"Tokens used: Input={response['usage']['input_tokens']}, Output={response['usage']['output_tokens']}"
            )
            return True
        else:
            logging.error(
                f"❌ Failed to generate summary: {response.get('error', 'Unknown error')}"
            )
            return False

    except Exception as e:
        logging.error(f"❌ Error in test summarization: {str(e)}")
        return False


def main():
    """Run the test."""
    print("\n=== LLM Summarization Test ===\n")

    # Create or get test file
    test_file = create_test_markdown()
    print(f"Using test file: {test_file}\n")

    # Test summarization
    success = test_summarization(test_file)

    if success:
        print("\n✅ Summarization test completed successfully!")
    else:
        print("\n❌ Summarization test failed. See logs for details.")

    print("\n=== Test Complete ===\n")


if __name__ == "__main__":
    main()
