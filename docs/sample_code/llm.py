# File Location: lib/llm.py
# Section: 3.2 LLM Client with Auto-Discovery
# Description: Multi-provider client with automatic Langfuse integration

from datetime import datetime
from typing import Any, Dict, List, Optional

import litellm
import streamlit as st
from langfuse import Langfuse

from .chunking import SimpleHeaderChunking
from .config import LANGFUSE_CONFIG, get_all_available_models, get_recommended_model

# Enable automatic Langfuse tracing
litellm.success_callback = ["langfuse"]
litellm.failure_callback = ["langfuse"]

# Configure Langfuse for LiteLLM
if all(LANGFUSE_CONFIG.values()):
    litellm.langfuse_public_key = LANGFUSE_CONFIG["public_key"]
    litellm.langfuse_secret_key = LANGFUSE_CONFIG["secret_key"]
    litellm.langfuse_host = LANGFUSE_CONFIG["host"]

class SimplifiedLLMClient:
    def __init__(self):
        self.available_models = get_all_available_models()
        self.primary_model = get_recommended_model()
        self.langfuse = Langfuse() if all(LANGFUSE_CONFIG.values()) else None
        self.chunker = SimpleHeaderChunking()  # Add simple chunker

    async def generate_with_prompt(
        self,
        model_key: str,
        langfuse_prompt,
        variables: dict,
        **kwargs
    ):
        """Generate with Langfuse prompt - automatic tracing"""

        # Compile prompt
        if hasattr(langfuse_prompt, 'type') and langfuse_prompt.type == "chat":
            messages = langfuse_prompt.compile(**variables)
        else:
            content = langfuse_prompt.compile(**variables)
            messages = [{"role": "user", "content": content}]

        # LiteLLM call with automatic Langfuse tracing
        response = await litellm.acompletion(
            model=model_key,
            messages=messages,
            metadata={
                "prompt_name": getattr(langfuse_prompt, 'name', 'unknown'),
                "variables": variables,
                **kwargs.get("metadata", {})
            },
            **{k: v for k, v in kwargs.items() if k != "metadata"}
        )

        return response

    async def generate_with_context_tracking(
        self,
        model_key: str,
        langfuse_prompt,
        variables: dict,
        case_id: str = None,
        document_type: str = None,
        operation_type: str = "generation",
        source_file: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Enhanced generation with forensic context tracking"""

        # Enhanced metadata for forensic tracing
        enhanced_metadata = {
            "case_id": case_id,
            "document_type": document_type,
            "operation_type": operation_type,
            "source_file": source_file,
            "timestamp": datetime.now().isoformat()
        }

        # Merge with any existing metadata
        kwargs["metadata"] = {**kwargs.get("metadata", {}), **enhanced_metadata}

        # Generate with full tracing
        response = await self.generate_with_prompt(model_key, langfuse_prompt, variables, **kwargs)

        # Extract trace IDs for minimal metadata
        trace_id = getattr(response, '_langfuse_trace_id', None)
        generation_id = getattr(response, '_langfuse_generation_id', None)

        # Return minimal metadata for YAML frontmatter, but with links to details in lanfuse
        minimal_metadata = {
            "timestamp": enhanced_metadata["timestamp"],
            "operation_type": operation_type,
            "langfuse_trace_id": trace_id,
            "langfuse_generation_id": generation_id,
            "model_key": model_key,
            "prompt_name": getattr(langfuse_prompt, 'name', 'unknown'),
            "source_file": source_file,
            "case_id": case_id
        }

        return {
            "response": response,
            "minimal_metadata": minimal_metadata,
            "content": response.choices[0].message.content
        }

    async def generate_simple(self, model_key: str, messages: List[dict], **kwargs):
        """Simple generation without prompt management"""
        return await litellm.acompletion(
            model=model_key,
            messages=messages,
            **kwargs
        )

    def get_available_models(self) -> List[str]:
        """Get list of available models"""
        return self.available_models

    def get_primary_model(self) -> Optional[str]:
        """Get recommended primary model"""
        return self.primary_model

    async def generate_with_chunked_document(
        self,
        model_key: str,
        langfuse_prompt,
        document_content: str,
        variables: dict,
        case_id: str = None,
        source_file: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Enhanced generation with automatic document chunking"""

        # Check if document needs chunking
        chunks = self.chunker.chunk_for_model(document_content, model_key, source_file)

        if len(chunks) == 1:
            # Single chunk - process normally
            variables["document_content"] = document_content
            return await self.generate_with_context_tracking(
                model_key, langfuse_prompt, variables,
                case_id=case_id, source_file=source_file, **kwargs
            )

        # Multi-chunk processing with Streamlit progress indication
        st.info(f"📄 Document split into {len(chunks)} sections based on headers")

        chunk_results = []
        progress_bar = st.progress(0)

        for i, chunk in enumerate(chunks):
            # Update progress
            progress_bar.progress((i + 1) / len(chunks))

            # Show current section being processed
            headers = []
            for level in ["Header 1", "Header 2", "Header 3"]:
                if chunk["metadata"].get(level):
                    headers.append(chunk["metadata"][level])

            section_info = " > ".join(headers) if headers else f"Section {i+1}"
            st.write(f"Processing: {section_info}")

            # Process chunk with enhanced variables
            chunk_variables = {
                **variables,
                "document_content": chunk["content"],
                "section_context": f"Section {i+1} of {len(chunks)}: {section_info}",
                "chunk_metadata": chunk["metadata"]
            }

            result = await self.generate_with_context_tracking(
                model_key, langfuse_prompt, chunk_variables,
                operation_type=f"chunk_processing_{i+1}",
                case_id=case_id,
                source_file=f"{source_file}_chunk_{i+1}",
                **kwargs
            )

            # Add chunk metadata to result
            result["chunk_info"] = chunk["metadata"]
            chunk_results.append(result)

        # Combine results intelligently
        combined_content = self._combine_chunk_results(chunk_results)

        return {
            "response": chunk_results[-1]["response"],  # Use last response for overall metadata
            "content": combined_content,
            "chunk_results": chunk_results,
            "total_chunks": len(chunks),
            "chunking_strategy": "header_based"
        }

    def _combine_chunk_results(self, chunk_results: List[Dict]) -> str:
        """Combine multiple chunk results preserving section structure"""
        combined_sections = []

        for result in chunk_results:
            chunk_info = result.get("chunk_info", {})

            # Add section header for clarity
            headers = []
            for level in ["Header 1", "Header 2", "Header 3"]:
                if chunk_info.get(level):
                    headers.append(chunk_info[level])

            if headers:
                section_title = " > ".join(headers)
                combined_sections.append(f"\n## {section_title}\n")

            combined_sections.append(result["content"])

            # Add separator unless it's the last chunk
            if result != chunk_results[-1]:
                combined_sections.append("\n---\n")

        return "".join(combined_sections)

@st.cache_resource
def get_llm_client():
    """Cached LLM client instance"""
    return SimplifiedLLMClient()

def add_session_cost(response):
    """Add response cost to session tracking"""
    if hasattr(response, 'cost') and response.cost:
        if "total_cost" not in st.session_state:
            st.session_state.total_cost = 0.0
        st.session_state.total_cost += response.cost 
