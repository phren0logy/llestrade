import logging
import os

from llm_utils import LLMClient

# Setup logging
logging.basicConfig(level=logging.DEBUG)

# Initialize client
client = LLMClient()
print("Testing Gemini with large input...")

# Generate a large input text
large_text = ""
for i in range(1, 5000):
    large_text += f"Section {i}: This is a test paragraph with some content that will be used to test Gemini's ability to handle large inputs.\n\n"

print(f"Generated text of length: {len(large_text)} characters")

# Test with the large input
try:
    response = client.generate_response_with_gemini(
        prompt_text=f"Summarize the following text in 3 paragraphs:\n\n{large_text}",
        temperature=0.1,
    )

    print(f"Success: {response['success']}")
    if response["success"]:
        print(f"Response model: {response.get('model', 'Unknown')}")
        print(f"Content: {response['content'][:500]}...")
    else:
        print(f"Error: {response.get('error', 'Unknown error')}")
except Exception as e:
    print(f"Exception occurred: {str(e)}")
