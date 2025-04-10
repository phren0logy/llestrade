import logging
import os

logging.basicConfig(level=logging.DEBUG)

from llm_utils import LLMClient

# Initialize client
client = LLMClient()
print("Initializing Gemini client...")
client._init_gemini_client()
print(f"Gemini initialized: {client.gemini_initialized}")

# Test with a simple prompt
print("Testing Gemini with a simple prompt...")
response = client.generate_response_with_gemini(
    prompt_text="Summarize this document: This is a test document about Test Subject, born on January 1, 2000. The subject has had various life experiences.",
    system_prompt="You are creating a summary for Test Subject (DOB: 2000-01-01).",
    temperature=0.1,
)

print(f"Response success: {response['success']}")
if response["success"]:
    print(f"Response content: {response['content']}")
else:
    print(f"Error: {response.get('error', 'Unknown error')}")

# Test with a longer prompt that would normally exceed Claude's token limit
print("\nTesting Gemini with a longer prompt...")
long_prompt = "I need to summarize a very long document. " + (
    "This is test text. " * 1000
)
response = client.generate_response_with_gemini(
    prompt_text=long_prompt,
    system_prompt="You are creating a summary for Test Subject (DOB: 2000-01-01).",
    temperature=0.1,
)

print(f"Response success: {response['success']}")
if response["success"]:
    print(f"Response content summary (first 100 chars): {response['content'][:100]}...")
else:
    print(f"Error: {response.get('error', 'Unknown error')}")
