# File Location: lib/chunking.py
# Section: 3.7 Simple Document Chunking
# Description: Lightweight chunking strategy that respects Azure DocumentIntelligence's markdown structure

from typing import Any, Dict, List

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)


class SimpleHeaderChunking:
    """Simple header-based chunking for Azure DocumentIntelligence markdown output"""

    # Azure DocumentIntelligence typically produces these header levels
    DEFAULT_HEADERS = [
        ("#", "Header 1"),      # Main sections
        ("##", "Header 2"),     # Subsections
        ("###", "Header 3"),    # Sub-subsections
        ("####", "Header 4"),   # Detail sections
    ]

    def __init__(self, max_chunk_size: int = 8000, chunk_overlap: int = 200):
        """Initialize simple chunker with conservative defaults"""
        self.max_chunk_size = max_chunk_size * 4  # Convert to characters
        self.chunk_overlap = chunk_overlap * 4

        # Primary splitter by headers
        self.header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.DEFAULT_HEADERS,
            strip_headers=False  # Keep headers for context
        )

        # Secondary splitter for large sections
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.max_chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", " "],  # Respect boundaries
        )

    def chunk_for_model(self, content: str, model_key: str, source_file: str = None) -> List[Dict[str, Any]]:
        """Chunk document with model-specific context window awareness"""

        # Simple model context window mapping
        model_context_windows = {
            "gpt-4": 8192,
            "gpt-4-32k": 32768,
            "gpt-4-1106-preview": 128000,
            "claude-3-sonnet": 200000,
            "claude-3-5-sonnet": 200000,
            "gemini-pro": 32768,
            "gemini-1.5-pro": 1000000,
        }

        # Extract base model and get context window
        base_model = model_key.split('/')[-1] if '/' in model_key else model_key
        context_window = model_context_windows.get(base_model, 8192)

        # Reserve 20% for prompt/response
        safe_chunk_size = int(context_window * 0.8)

        # Step 1: Split by headers first
        header_chunks = self.header_splitter.split_text(content)

        final_chunks = []
        for doc in header_chunks:
            if len(doc.page_content) <= safe_chunk_size * 4:  # Small enough
                chunk = {
                    "content": doc.page_content,
                    "metadata": {
                        **doc.metadata,
                        "chunk_index": len(final_chunks),
                        "chunk_type": "header_section",
                        "source_file": source_file,
                        "estimated_tokens": len(doc.page_content) // 4,
                        "target_model": model_key,
                        "model_context_window": context_window
                    }
                }
                final_chunks.append(chunk)
            else:
                # Too large - split further while preserving header context
                sub_chunks = self.text_splitter.split_text(doc.page_content)
                for j, sub_content in enumerate(sub_chunks):
                    chunk = {
                        "content": sub_content,
                        "metadata": {
                            **doc.metadata,
                            "chunk_index": len(final_chunks),
                            "chunk_type": "header_section_part",
                            "section_part": f"{j+1}_of_{len(sub_chunks)}",
                            "source_file": source_file,
                            "estimated_tokens": len(sub_content) // 4,
                            "target_model": model_key,
                            "model_context_window": context_window
                        }
                    }
                    final_chunks.append(chunk)

        # Add total chunk count to all chunks
        for chunk in final_chunks:
            chunk["metadata"]["total_chunks"] = len(final_chunks)

        return final_chunks

# Simple utility for debugging
def preview_chunks(chunks: List[Dict[str, Any]], max_preview: int = 100):
    """Preview chunks for debugging"""
    for i, chunk in enumerate(chunks):
        content_preview = chunk["content"][:max_preview] + "..." if len(chunk["content"]) > max_preview else chunk["content"]
        metadata = chunk["metadata"]

        print(f"\n--- Chunk {i+1} ---")
        print(f"Headers: {metadata.get('Header 1', 'N/A')} > {metadata.get('Header 2', 'N/A')}")
        print(f"Type: {metadata.get('chunk_type', 'unknown')}")
        print(f"Tokens: ~{metadata.get('estimated_tokens', 0)}")
        print(f"Content preview: {content_preview}") 
