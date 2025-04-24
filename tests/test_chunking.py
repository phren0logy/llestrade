import unittest
import sys
import os
sys.path.append(os.path.abspath("."))  # Add the project root to the path

from ui.workers.llm_summary_thread import chunk_document_with_overlap

class MockClient:
    def __init__(self):
        self.count = 0
    
    def count_tokens(self, text=None, messages=None):
        self.count += 1
        return {"success": True, "token_count": len(text or "") // 4}

class TestChunking(unittest.TestCase):
    def test_api_call_reduction(self):
        # Create a document with 30 paragraphs
        paragraphs = [f"This is paragraph {i}. " * 20 for i in range(30)]
        text = "

".join(paragraphs)
        
        # Use our mock client to track API calls
        client = MockClient()
        
        # Run the chunking function
        chunks = chunk_document_with_overlap(text, client, max_chunk_size=2000, overlap=100)
        
        # Print results
        print(f"Document size: {len(text)} characters")
        print(f"Divided into {len(chunks)} chunks")
        print(f"Number of token counting API calls made: {client.count}")

if __name__ == "__main__":
    test = TestChunking()
    test.test_api_call_reduction()
    print("Test completed successfully")

