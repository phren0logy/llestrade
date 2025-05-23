# Design Document: Forensic Psych Report Drafter v2 (Simplified)

> **📁 Sample Code Extracted**: All implementation code has been moved to [`docs/sample_code/`](sample_code/) for better organization. Each code reference below links to the complete implementation.

## 1. Project Overview

This document outlines the design for a Forensic Psych Report Drafter application. The primary goal is to create a streamlined, robust, and maintainable tool for forensic psychiatrists to analyze documents and generate reports. This is a single-user application. The design **simplicity** and leveraging **native integrations** between core technologies to minimize custom code and maximize functionality.

**Core Purpose**: To assist forensic psych professionals (psychiatrists and psychologists) by automating and enhancing the drafting of reports through LLM-powered document analysis, template-driven prompt generation, and report refinement.

**Core Workflow**: Integrated Template-Driven Report Generation and Refinement

1. **Record Conversion**: Convert PDFs to structured markdown using Azure DocumentIntelligence
2. **Document Summary**: Create document and meta-summaries for analysis preparation
3. **Report Generation & Refinement**: Transform local markdown templates into reports, then iteratively improve them through automated and manual refinement
4. **Human Evaluation**: Manual annotation, side-by-side comparison, and feedback collection

**Primary Use Case**: Forensic professionals maintain standardized markdown report templates locally. The system processes these templates section-by-section, combining each section with interview transcripts to generate comprehensive, structured forensic reports that follow established professional standards.

**Key Technologies**:

- **UI Framework**: Streamlit (with auto-page discovery)
- **LLM Orchestration**: LiteLLM Router with automatic Langfuse integration
- **Supported LLM Providers**:
  - Azure OpenAI (most recent GPT models, currently GPT-4.1 family) and Azure DocumentIntelligence
  - Anthropic (most recent Sonnet models, currently Claude Sonnet 4)
  - Google Gemini (most recent Gemini Pro models, currently Gemini 2.5 Pro)
- **Observability & Prompt Management**: Langfuse (automatic tracing via LiteLLM + centralized prompt CMS)
- **Evaluation Framework**: Native Langfuse evaluation tools with Streamlit UI
- **Dependency Management**: uv
- **PDF Handling**:
  - PyMuPDF (for pre-checks and metadata extraction)
  - Azure DocumentIntelligence (for PDF to markdown/JSON conversion)

## 2. Architecture

### 2.1. Template-Centric Directory Structure

Following 2025 Streamlit best practices with emphasis on local template management:

```
forensic-report-drafter-v2/
├── app.py                          # Main homepage with status display
├── pyproject.toml                  # uv-managed dependencies
├── .env                            # Environment variables
├── pages/                          # Streamlit auto-discovered pages
│   ├── 1_🔄_Record_Conversion.py   # Convert PDFs to markdown/JSON
│   ├── 2_📋_Summary.py             # Create document and meta-summaries
│   ├── 3_📝_Report_Generation.py   # Generate and refine reports from templates (CONSOLIDATED)
│   └── 4_🔬_Evaluation.py          # Manage prompts and evaluate outputs
├── lib/                            # Simple business logic
│   ├── config.py                   # Simple configuration with env vars
│   ├── llm.py                      # LiteLLM router & client
│   ├── prompts.py                  # Langfuse prompt management
│   ├── files.py                    # File operations
│   ├── chunking.py                 # Simple header-based document chunking
│   ├── template_processor.py       # Local template processing engine
│   └── state.py                    # Session state helpers
├── report_templates/               # User's local markdown report templates
│   ├── forensic_evaluation.md      # Standard forensic evaluation template
│   ├── competency_evaluation.md    # Competency to stand trial template
│   ├── risk_assessment.md          # Violence risk assessment template
│   ├── substance_abuse.md          # Substance abuse evaluation template
│   └── custom/                     # User-created custom templates
├── prompt_instructions/            # LLM processing instructions
│   ├── section_processing.md       # How to process template sections
│   ├── report_generation.md        # Standard report generation instructions
│   └── refinement.md               # Report refinement instructions
├── outputs/                        # Generated files
└── README.md                       # Setup and usage instructions
```

**Key Decisions for Simplicity**:

- **Auto-discovery over configuration** - LiteLLM detects available models automatically
- **lib/ for business logic** - Simple, focused modules without over-engineering
- **Streamlit native patterns** - Pages contain their own logic, proper caching
- **Direct LiteLLM integration** - No complex routing, automatic Langfuse tracing
- **Single-user optimized** - Simplified for local deployment and distribution

### 2.2. Technology Integration Philosophy

**Multi-Provider with Native Observability**: Leverage auto-discovery and built-in integrations:

- **LiteLLM Auto-Discovery**: Automatically detect available models from Azure, Anthropic, Gemini
- **LiteLLM → Langfuse**: Automatic tracing via built-in callbacks for all providers
- **Smart Configuration**: Environment variable detection with graceful fallbacks
- **Minimal Setup**: Single-user optimized with one-command configuration
- **Streamlit Native Patterns**: Use `st.cache_resource` and reactive model appropriately

### 2.3. Template-Centric Architecture

The system is designed around **locally maintained markdown report templates** as the primary workflow:

**Template Workflow**:

1. **Local Storage**: Users maintain markdown templates in `report_templates/` directory
2. **Section Parsing**: Templates are split by Header 1 sections using LangChain
3. **Prompt Generation**: Each section becomes a structured LLM prompt
4. **Transcript Integration**: Section prompts are combined with interview transcripts
5. **Report Assembly**: Generated sections are combined into complete reports
6. **Iterative Refinement**: Reports can be improved through automated and manual refinement processes

**Key Benefits**:

- **User Control**: Templates are locally stored and fully customizable
- **Section Focus**: Each template section gets dedicated LLM attention
- **Consistent Structure**: All reports follow established forensic standards
- **Iterative Improvement**: Users can refine templates based on experience

This template-driven approach ensures that the LLM generation follows established forensic reporting standards while allowing customization for different evaluation types and practice preferences.

## 3. Core Modules & Implementation

### 3.1. Simplified Multi-Provider Configuration (`lib/config.py`)

Auto-discovery of available models with minimal configuration:

**See implementation:** [`docs/sample_code/config.py`](sample_code/config.py)

**Key Features:**

- **Auto-discovery of models** from each configured provider via LiteLLM
- **Smart provider detection** automatically enables available providers based on environment variables
- **Graceful fallbacks** to common models when auto-discovery fails
- **Minimal configuration** - just API keys required, everything else auto-configured
- **Current model families** - automatically resolves to most recent available versions

### 3.2. LLM Client with Auto-Discovery (`lib/llm.py`)

Multi-provider client with automatic Langfuse integration:

```python
# lib/llm.py - Simple but multi-provider
import streamlit as st
import litellm
from langfuse import Langfuse
from datetime import datetime
from typing import List, Optional, Dict, Any
from .config import get_all_available_models, get_recommended_model, LANGFUSE_CONFIG
from .chunking import SimpleHeaderChunking

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
```

### 3.3. Streamlined Prompt Management (`lib/prompts.py`)

Using Langfuse native patterns with simple fallbacks:

```python
# lib/prompts.py
import streamlit as st
import os
from langfuse import Langfuse
from .config import LANGFUSE_CONFIG

@st.cache_resource
def get_langfuse_client():
    """Get cached Langfuse client"""
    return Langfuse(
        public_key=LANGFUSE_CONFIG["public_key"],
        secret_key=LANGFUSE_CONFIG["secret_key"],
        host=LANGFUSE_CONFIG["host"]
    )

@st.cache_data(ttl=300)  # Cache prompts for 5 minutes
def get_prompt(name: str, label: str = "production"):
    """Get prompt with caching and simple fallback"""
    try:
        client = get_langfuse_client()
        return client.get_prompt(name, label=label)
    except Exception as e:
        st.warning(f"Could not fetch prompt '{name}' from Langfuse: {e}")
        # Simple fallback to local file
        fallback_path = f"templates/{name}.md"
        if os.path.exists(fallback_path):
            with open(fallback_path) as f:
                content = f.read()
                # Simple fallback object that mimics Langfuse prompt
                class FallbackPrompt:
                    def __init__(self, content):
                        self.prompt = content
                        self.name = name
                        self.type = "text"
                    def compile(self, **kwargs):
                        result = self.prompt
                        for key, value in kwargs.items():
                            result = result.replace(f"{{{{{key}}}}}", str(value))
                        return result
                return FallbackPrompt(content)
        raise Exception(f"No prompt found for {name} (neither in Langfuse nor local fallback)")
```

### 3.4. Simple State Management (`lib/state.py`)

Following Streamlit 2025 patterns:

```python
# lib/state.py
import streamlit as st

def init_session_state():
    """Initialize session state with defaults"""
    defaults = {
        "total_cost": 0.0,
        "selected_model": None,
        "conversation_history": []
    }

    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

def get_session_cost() -> float:
    """Get current session cost"""
    return st.session_state.get("total_cost", 0.0)

def reset_session_cost():
    """Reset session cost tracking"""
    st.session_state.total_cost = 0.0
```

### 3.5. File Operations with Minimal Metadata (`lib/files.py`)

File handling utilities with lightweight YAML frontmatter:

```python
# lib/files.py
import os
import json
import yaml
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

def ensure_directories():
    """Ensure required directories exist"""
    for directory in ["outputs", "templates"]:
        os.makedirs(directory, exist_ok=True)

def scan_for_pdfs(directory: str, recursive: bool = False) -> List[str]:
    """Scan directory for PDF files"""
    path = Path(directory)
    if recursive:
        return list(path.rglob("*.pdf"))
    else:
        return list(path.glob("*.pdf"))

def scan_for_markdown(directory: str) -> List[str]:
    """Scan directory for markdown files"""
    path = Path(directory)
    return list(path.glob("*.md"))

def save_output_with_minimal_metadata(content: str, filename: str, minimal_metadata: Dict[str, Any], output_dir: str = "outputs") -> str:
    """Save content with minimal YAML frontmatter linking to Langfuse"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"{timestamp}_{filename}"

    # Create minimal YAML frontmatter header
    metadata_header = "---\n"
    metadata_header += yaml.dump(minimal_metadata, default_flow_style=False)
    metadata_header += "---\n\n"

    # Combine metadata and content
    full_content = metadata_header + content

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_content)

    return str(output_path)

def save_chunked_output_with_metadata(
    content: str,
    filename: str,
    minimal_metadata: Dict[str, Any],
    chunk_info: Dict[str, Any] = None,
    output_dir: str = "outputs"
) -> str:
    """Save content with enhanced metadata for chunked documents"""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"{timestamp}_{filename}"

    # Enhanced metadata for chunked documents
    enhanced_metadata = {
        **minimal_metadata,
        "chunking_info": {
            "total_chunks": chunk_info.get("total_chunks", 1) if chunk_info else 1,
            "chunking_strategy": chunk_info.get("chunking_strategy", "none") if chunk_info else "none",
            "model_context_window": chunk_info.get("model_context_window") if chunk_info else None,
        } if chunk_info else None
    }

    # Create YAML frontmatter header
    metadata_header = "---\n"
    metadata_header += yaml.dump(enhanced_metadata, default_flow_style=False)
    metadata_header += "---\n\n"

    # Combine metadata and content
    full_content = metadata_header + content

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_content)

    return str(output_path)

def read_metadata_from_file(file_path: str) -> Dict[str, Any]:
    """Extract YAML frontmatter metadata from generated files"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if content.startswith('---\n'):
            end_marker = content.find('\n---\n', 4)
            if end_marker != -1:
                frontmatter = content[4:end_marker]
                return yaml.safe_load(frontmatter)
    except:
        pass

    return {}

def get_rich_context_from_langfuse(trace_id: str) -> Dict[str, Any]:
    """Fetch full generation context from Langfuse using trace ID"""
    try:
        from langfuse import Langfuse
        langfuse = Langfuse()
        trace = langfuse.get_trace(trace_id)

        return {
            "full_prompt": trace.input,
            "model_details": trace.model,
            "cost": trace.cost,
            "tokens": trace.usage,
            "duration": trace.duration,
            "tags": trace.tags,
            "metadata": trace.metadata
        }
    except Exception as e:
        return {"error": f"Could not fetch context: {e}"}

def save_output(content: str, filename: str, output_dir: str = "outputs") -> str:
    """Save content to output directory with timestamp (legacy method)"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"{timestamp}_{filename}"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return str(output_path)
```

### 3.6. UI Components for Human Evaluation and Context Discovery (`lib/ui_components.py`)

Reusable Streamlit components for human evaluation and transparent generation context:

```python
# lib/ui_components.py
import streamlit as st
from typing import Dict, Any, Optional
from .files import get_rich_context_from_langfuse
from .config import LANGFUSE_CONFIG

def show_generation_context_button(trace_id: str, label: str = "🔍 View Generation Context"):
    """Show button that reveals rich generation context on-demand"""
    if not trace_id:
        return

    if st.button(label, key=f"context_{trace_id}"):
        with st.spinner("Fetching generation details..."):
            context = get_rich_context_from_langfuse(trace_id)

            if "error" in context:
                st.error(context["error"])
                return

        # Rich metrics display
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Cost", f"${context.get('cost', 0):.4f}")
        with col2:
            st.metric("Tokens", context.get('tokens', {}).get('total', 0))
        with col3:
            st.metric("Duration", f"{context.get('duration', 0)}ms")

        # Progressive disclosure
        with st.expander("🔧 Prompt Details"):
            prompt_input = context.get('full_prompt', {})
            if isinstance(prompt_input, list):  # Chat format
                for msg in prompt_input:
                    st.write(f"**{msg.get('role', 'unknown').title()}:**")
                    st.code(msg.get('content', ''))
            else:
                st.code(str(prompt_input))

        with st.expander("🏷️ Tags & Metadata"):
            tags = context.get('tags', [])
            if tags:
                st.write("**Tags:**")
                for tag in tags:
                    st.badge(tag)

            metadata = context.get('metadata', {})
            if metadata:
                st.write("**Metadata:**")
                st.json(metadata)

        # Direct Langfuse link
        langfuse_host = LANGFUSE_CONFIG.get("host", "https://cloud.langfuse.com")
        st.link_button("🌐 Open in Langfuse", f"{langfuse_host}/trace/{trace_id}")

def show_document_metadata_preview(metadata: Dict[str, Any]):
    """Show compact metadata preview for document listings"""
    if not metadata:
        st.caption("No metadata available")
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        if "model_key" in metadata:
            st.write(f"**Model:** {metadata['model_key']}")

    with col2:
        if "prompt_name" in metadata:
            st.write(f"**Prompt:** {metadata['prompt_name']}")

    with col3:
        if "timestamp" in metadata:
            date_str = metadata['timestamp'][:10] if metadata['timestamp'] else "Unknown"
            st.write(f"**Generated:** {date_str}")

def show_case_dashboard(case_id: str):
    """Show case-centric dashboard with all related generations"""
    try:
        from langfuse import Langfuse
        langfuse = Langfuse()

        # Fetch all traces for this case
        traces = langfuse.get_traces(tags=[f"case:{case_id}"])

        if not traces:
            st.info(f"No generations found for case {case_id}")
            return

        # Case summary metrics
        total_cost = sum(getattr(t, 'cost', 0) for t in traces)
        total_docs = len(set(t.metadata.get("source_file", "") for t in traces if hasattr(t, 'metadata')))

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Cost", f"${total_cost:.2f}")
        with col2:
            st.metric("Documents Processed", total_docs)
        with col3:
            st.metric("AI Generations", len(traces))

        # Document list with context buttons
        st.subheader("Generated Documents")
        for trace in traces[-10:]:  # Show last 10
            with st.expander(f"📄 {trace.metadata.get('source_file', 'Unknown')} - {trace.metadata.get('operation_type', 'generation')}"):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"**Model:** {trace.model}")
                    st.write(f"**Cost:** ${getattr(trace, 'cost', 0):.4f}")
                with col2:
                    show_generation_context_button(trace.id, "View Details")

    except Exception as e:
        st.error(f"Error loading case dashboard: {e}")

def show_model_comparison_widget(document_traces: list):
    """Widget to compare how different models handled the same document"""
    if len(document_traces) < 2:
        return

    st.subheader("🔄 Model Comparison")

    # Group by model
    by_model = {}
    for trace in document_traces:
        model = getattr(trace, 'model', 'unknown')
        if model not in by_model:
            by_model[model] = []
        by_model[model].append(trace)

    # Show comparison
    for model, traces in by_model.items():
        avg_cost = sum(getattr(t, 'cost', 0) for t in traces) / len(traces)
        st.metric(f"{model} Average Cost", f"${avg_cost:.4f}")

def create_human_evaluation_interface(trace_id: str, content: str, document_type: str = "general"):
    """Create forensic-specific human evaluation interface"""
    st.subheader("🔍 Human Evaluation")

    # Display content for evaluation
    st.text_area("Generated Content", value=content, height=250, disabled=True)

    # Forensic-specific evaluation criteria
    col1, col2 = st.columns(2)

    with col1:
        accuracy = st.slider("Factual Accuracy (1-5)", 1, 5, 3, key=f"accuracy_{trace_id}")
        completeness = st.slider("Completeness (1-5)", 1, 5, 3, key=f"completeness_{trace_id}")
        clarity = st.slider("Clarity (1-5)", 1, 5, 3, key=f"clarity_{trace_id}")

    with col2:
        forensic_relevance = st.slider("Forensic Relevance (1-5)", 1, 5, 3, key=f"forensic_{trace_id}")
        ethical_compliance = st.slider("Ethical Standards (1-5)", 1, 5, 3, key=f"ethical_{trace_id}")
        usability = st.slider("Professional Usability (1-5)", 1, 5, 3, key=f"usability_{trace_id}")

    evaluation_notes = st.text_area(
        "Evaluation Notes",
        placeholder="Specific observations, areas for improvement, or concerns...",
        key=f"notes_{trace_id}"
    )

    if st.button("Submit Evaluation", type="primary", key=f"submit_{trace_id}"):
        # Calculate overall score
        overall_score = (accuracy + completeness + clarity + forensic_relevance +
                        ethical_compliance + usability) / 6

        try:
            from lib.prompts import get_langfuse_client
            langfuse_client = get_langfuse_client()
            langfuse_client.score(
                trace_id=trace_id,
                name="human_evaluation",
                value=overall_score,
                metadata={
                    "document_type": document_type,
                    "accuracy": accuracy,
                    "completeness": completeness,
                    "clarity": clarity,
                    "forensic_relevance": forensic_relevance,
                    "ethical_compliance": ethical_compliance,
                    "usability": usability,
                    "evaluation_notes": evaluation_notes,
                    "evaluator": st.session_state.get("evaluator_name", "unknown"),
                    "evaluation_timestamp": datetime.now().isoformat()
                }
            )
            st.success("Evaluation submitted successfully!")
            return True
        except Exception as e:
            st.error(f"Failed to submit evaluation: {e}")
            return False

def show_annotation_queue_dashboard():
    """Dashboard for managing annotation workflow"""
    st.subheader("📋 Annotation Queue Status")

    try:
        from lib.prompts import get_langfuse_client
        langfuse = get_langfuse_client()

        # Get traces needing annotation
        all_traces = langfuse.get_traces(tags=["needs_annotation"])

        if not all_traces:
            st.info("No documents currently in annotation queue")
            return

        # Show queue statistics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Pending Annotations", len(all_traces))
        with col2:
            completed_today = len([t for t in all_traces if t.metadata.get("annotation_date") == datetime.now().strftime("%Y-%m-%d")])
            st.metric("Completed Today", completed_today)
        with col3:
            avg_score = sum(t.score for t in all_traces if hasattr(t, 'score')) / max(len([t for t in all_traces if hasattr(t, 'score')]), 1)
            st.metric("Average Score", f"{avg_score:.2f}")

        # List pending annotations
        st.subheader("Pending Annotations")
        for trace in all_traces[:5]:  # Show first 5
            with st.expander(f"📄 {trace.metadata.get('source_file', 'Unknown')} - {trace.metadata.get('operation_type', 'generation')}"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**Generated:** {trace.metadata.get('timestamp', 'Unknown')}")
                    st.write(f"**Model:** {trace.metadata.get('model_key', 'Unknown')}")
                with col2:
                    if st.button("Annotate", key=f"annotate_{trace.id}"):
                        st.session_state.current_annotation_trace = trace.id
                        st.rerun()

    except Exception as e:
        st.error(f"Error loading annotation queue: {e}")

def show_evaluation_analytics():
    """Show analytics from human evaluations"""
    st.subheader("📊 Evaluation Analytics")

    try:
        from lib.prompts import get_langfuse_client
        langfuse = get_langfuse_client()

        # Get all human evaluations
        evaluations = langfuse.get_traces(tags=["human_evaluated"])

        if not evaluations:
            st.info("No human evaluations available yet")
            return

        # Calculate metrics
        scores = [e.score for e in evaluations if hasattr(e, 'score')]

        if scores:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Evaluations", len(scores))
            with col2:
                st.metric("Average Score", f"{sum(scores)/len(scores):.2f}")
            with col3:
                high_quality = len([s for s in scores if s >= 4.0])
                st.metric("High Quality (≥4.0)", f"{high_quality}/{len(scores)}")

        # Show evaluation trends
        if len(evaluations) > 1:
            st.line_chart([e.score for e in evaluations[-10:] if hasattr(e, 'score')])

    except Exception as e:
        st.error(f"Error loading evaluation analytics: {e}")
```

### 3.7. Simple Document Chunking (`lib/chunking.py`)

Lightweight chunking strategy that respects Azure DocumentIntelligence's markdown structure:

```python
# lib/chunking.py - Simple header-based chunking
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from typing import List, Dict, Any

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
```

**Key Design Principles**:

- **Header-First Chunking**: Leverages Azure DocumentIntelligence's natural markdown structure
- **Model-Aware Sizing**: Automatically adjusts chunk sizes based on model context windows
- **Boundary Respect**: Uses LangChain's proven patterns for semantic boundary preservation
- **Simple Fallback**: Falls back to character-based splitting only when header sections are too large
- **Rich Metadata**: Preserves header hierarchy and source information for traceability

**Benefits**:

- **Maintains Document Structure**: Respects the logical organization Azure DocumentIntelligence provides
- **No Over-Engineering**: Simple approach using proven LangChain components
- **Context Preservation**: Header metadata provides semantic context for each chunk
- **Model Compatibility**: Automatically adapts to different model context windows
- **Debugging Support**: Clear metadata and preview utilities for troubleshooting

### 3.8. Local Template Processing Engine (`lib/template_processor.py`)

The template processor is the **core engine** that transforms user-maintained markdown report templates into structured LLM workflows. This is the primary value proposition of the system.

```python
# lib/template_processor.py - Core template-to-prompt conversion
from langchain_text_splitters import MarkdownHeaderTextSplitter
from typing import List, Dict, Any
from pathlib import Path
import streamlit as st
from .prompts import get_prompt

class LocalTemplateProcessor:
    """
    Core processor for locally stored markdown report templates.

    This enables the primary workflow: forensic professionals maintain
    standardized markdown templates locally, and this system converts
    them into section-based LLM prompts for comprehensive report generation.
    """

    def __init__(self, template_directory: str = "report_templates"):
        self.template_directory = Path(template_directory)
        self.header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "Header 1")],  # Split on main sections
            strip_headers=False  # Preserve headers for context
        )
        self._ensure_template_directory()

    def _ensure_template_directory(self):
        """Ensure template directory exists with example templates"""
        self.template_directory.mkdir(exist_ok=True)

        # Create example templates for new users
        if not any(self.template_directory.glob("*.md")):
            self._create_starter_templates()

    def get_available_templates(self) -> List[str]:
        """Get list of user's local markdown templates"""
        return sorted([f.name for f in self.template_directory.glob("*.md")])

    def load_template(self, template_name: str) -> str:
        """Load template content from user's local directory"""
        template_path = self.template_directory / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_name}")

        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()

    def process_template_to_sections(self, template_name: str) -> List[Dict[str, Any]]:
        """
        Split user's template into sections for individual processing.

        Each Header 1 section becomes a separate prompt, allowing focused
        generation and better quality control.
        """
        template_content = self.load_template(template_name)

        # Use LangChain to split by headers while preserving structure
        sections = self.header_splitter.split_text(template_content)

        processed_sections = []
        for i, section in enumerate(sections, start=1):
            if hasattr(section, "page_content") and hasattr(section, "metadata"):
                section_name = section.metadata.get("Header 1", f"Section {i}")

                processed_sections.append({
                    "name": section_name,
                    "content": section.page_content,
                    "metadata": section.metadata,
                    "template_source": template_name,
                    "section_index": i
                })

        return processed_sections

    def generate_section_prompts(self, template_name: str) -> List[Dict[str, Any]]:
        """
        Convert template sections into LLM-ready prompts.

        This is where user templates become structured prompts that guide
        LLM generation for each section of the forensic report.
        """
        sections = self.process_template_to_sections(template_name)

        # Get standardized instructions for report generation
        try:
            instructions = get_prompt("section_processing")
        except:
            # Fallback instructions if Langfuse unavailable
            instructions = """Generate this section of a forensic psychiatric evaluation report. Use information from the interview transcript. Organize relevant information including direct quotes. Write in complete paragraphs following professional forensic reporting standards."""

        prompts = []
        for section in sections:
            # Structure as template + instructions
            prompt_content = f"""<template>
# {section['name']}

{section['content']}
</template>

{instructions}"""

            prompts.append({
                "name": section['name'],
                "content": prompt_content,
                "template_source": template_name,
                "section_index": section['section_index'],
                "metadata": section['metadata']
            })

        return prompts

    def combine_with_transcript(self, section_prompt: Dict[str, Any], transcript_content: str) -> str:
        """Combine section prompt with interview transcript for final generation"""
        return f"""{section_prompt['content']}

<transcript>
{transcript_content}
</transcript>"""

@st.cache_resource
def get_template_processor():
    """Cached template processor instance"""
    return LocalTemplateProcessor()
```

**Key Design Principles**:

- **User Template Ownership**: Templates are stored locally and fully under user control
- **Section-Based Processing**: Each Header 1 section gets dedicated LLM attention
- **Professional Standards**: Templates encode established forensic reporting practices
- **Graceful Fallbacks**: System works with or without Langfuse connectivity
- **Simple Integration**: Clean integration with Streamlit file handling patterns

**Benefits for Forensic Workflow**:

- **Consistency**: All reports follow user's established templates
- **Quality Control**: Section-by-section processing improves focus and accuracy
- **Customization**: Users can modify templates for different evaluation types
- **Professional Standards**: Templates enforce proper forensic report structure
- **Efficiency**: Automated processing while maintaining professional quality

## 4. Streamlit Pages Implementation

### 4.1. Main Application with Auto-Discovery (`app.py`)

Homepage with automatic model discovery and provider status:

```python
# app.py - Auto-discovery on startup
import streamlit as st
import asyncio
from lib.llm import get_llm_client
from lib.config import discover_available_models, LANGFUSE_CONFIG
from lib.state import init_session_state, get_session_cost
from lib.files import ensure_directories

st.set_page_config(
    page_title="Forensic Report Drafter",
    page_icon="⚖️",
    layout="wide"
)

# Initialize
init_session_state()
ensure_directories()

# Auto-discovery on first load
if "models_discovered" not in st.session_state:
    with st.spinner("🔍 Discovering available models..."):
        st.session_state.available_models = discover_available_models()
        st.session_state.models_discovered = True

st.title("⚖️ Forensic Psych Report Drafter")
st.markdown("*Streamlined LLM-powered document analysis and report generation*")

# Sidebar status with auto-discovered info
with st.sidebar:
    st.header("System Status")

    # Show discovered providers and models
    total_models = 0
    for provider, models in st.session_state.available_models.items():
        st.success(f"✅ {provider.title()}: {len(models)} models")
        total_models += len(models)

        # Show models in expander
        with st.expander(f"View {provider} models"):
            for model in models:
                st.write(f"  • {model.split('/')[-1]}")

    if total_models == 0:
        st.error("❌ No models available")
        st.info("Run setup to configure providers")

    # Langfuse status
    if all(LANGFUSE_CONFIG.values()):
        st.success("✅ Langfuse tracing enabled")
    else:
        st.warning("⚠️ Langfuse disabled")

    st.divider()

    # Session cost tracking
    st.metric("Session Cost", f"${get_session_cost():.4f}")

    # Quick model test
    if st.button("🧪 Test Primary Model"):
        client = get_llm_client()
        if client.primary_model:
            try:
                # Quick test call
                response = asyncio.run(client.generate_simple(
                    client.primary_model,
                    [{"role": "user", "content": "Say 'Test successful'"}]
                ))
                st.success(f"✅ {client.primary_model} working")
            except Exception as e:
                st.error(f"❌ Error: {e}")

# Main content
col1, col2 = st.columns(2)

with col1:
    st.subheader("🔄 Workflow")
    st.markdown("""
    1. **Record Conversion**: Convert PDFs to structured markdown
    2. **Document Summary**: Create document and meta-summaries for analysis preparation
    3. **Report Generation & Refinement**: Generate comprehensive reports from templates and iteratively improve them
    4. **Human Evaluation**: Manual annotation, side-by-side comparison, and feedback collection
    """)

with col2:
    st.subheader("🚀 Quick Start")
    st.markdown("""
    - Upload PDFs in **Record Conversion**
    - Generate summaries in **Summary**
    - Generate and refine reports in **Report Generation**
    - Evaluate outputs with **Human Evaluation**
    """)

# Provider setup help
if total_models == 0:
    st.warning("⚠️ **No LLM providers configured**")
    st.info("""
    **To get started:**
    1. Set environment variables for at least one provider:
       - **Azure OpenAI**: `AZURE_API_KEY`, `AZURE_API_BASE`
       - **Anthropic**: `ANTHROPIC_API_KEY`
       - **Google Gemini**: `GOOGLE_API_KEY`
    2. Optional: Set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` for tracing
    3. Restart the application
    """)

if st.button("Reset Session Cost"):
    from lib.state import reset_session_cost
    reset_session_cost()
    st.rerun()
```

### 4.2. Report Generation & Refinement - Consolidated Workflow Page (`pages/3_📝_Report_Generation.py`)

This is the **primary user interface** for the complete report lifecycle. Users select local templates, upload transcripts, generate section-based reports, and iteratively refine them through both automated and manual processes.

```python
# pages/3_📝_Report_Templates.py - Core template processing workflow
import streamlit as st
import asyncio
from pathlib import Path
from lib.template_processor import get_template_processor
from lib.llm import get_llm_client
from lib.files import save_output_with_minimal_metadata
from lib.ui_components import show_generation_context_button
from datetime import datetime

st.title("📝 Report Templates")
st.markdown("**Generate forensic reports from your local markdown templates**")

# Initialize processors
processor = get_template_processor()
client = get_llm_client()

# Step 1: Template Selection
st.subheader("1. Select Report Template")

available_templates = processor.get_available_templates()

if not available_templates:
    st.warning("⚠️ No templates found in `report_templates/` directory")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📁 Open Template Directory"):
            # Platform-specific directory opening code
            pass
    with col2:
        if st.button("➕ Create Example Templates"):
            processor._create_starter_templates()
            st.rerun()
else:
    selected_template = st.selectbox(
        "Choose your report template:",
        available_templates,
        help="Select from your locally stored markdown templates"
    )

    # Template preview and section breakdown
    if selected_template:
        with st.expander("🔍 Preview Template Structure"):
            sections = processor.process_template_to_sections(selected_template)

            col1, col2 = st.columns([1, 2])
            with col1:
                st.metric("Template Sections", len(sections))
                for section in sections:
                    st.write(f"• {section['name']}")

            with col2:
                template_content = processor.load_template(selected_template)
                st.text_area("Template Content", template_content, height=200, disabled=True)

# Step 2: Transcript Upload
st.subheader("2. Upload Interview Transcript")

transcript_file = st.file_uploader(
    "Select interview transcript:",
    type=['txt', 'md'],
    help="Upload the interview transcript to combine with your template"
)

# Step 3: Generation Options and Processing
if available_templates and selected_template and transcript_file:
    transcript_content = transcript_file.read().decode('utf-8')

    st.subheader("3. Generation Options")

    col1, col2, col3 = st.columns(3)

    with col1:
        # Model selection with provider grouping
        available_models = client.get_available_models()
        selected_model = st.selectbox(
            "Model:",
            available_models,
            format_func=lambda x: f"{x.split('/')[0].title()}: {x.split('/')[1]}"
        )

    with col2:
        case_id = st.text_input("Case ID (optional):")

    with col3:
        save_individual = st.checkbox("Save individual sections", value=True)
        generate_combined = st.checkbox("Create combined report", value=True)

    # Main generation workflow
    if st.button("🚀 Generate Report from Template", type="primary"):

        # Process template into section prompts
        with st.spinner("Processing template sections..."):
            section_prompts = processor.generate_section_prompts(selected_template)

        st.info(f"📋 Processing {len(section_prompts)} sections from **{selected_template}**")

        # Generate each section with progress tracking
        async def generate_sections():
            progress = st.progress(0)
            results = []

            for i, section_prompt in enumerate(section_prompts):
                # Show current section being processed
                st.write(f"🔄 Generating: **{section_prompt['name']}**")

                # Combine section prompt with transcript
                final_prompt = processor.combine_with_transcript(section_prompt, transcript_content)

                # Generate with full context tracking
                variables = {"prompt_content": final_prompt}

                # Get Langfuse prompt or use fallback
                try:
                    from lib.prompts import get_prompt
                    langfuse_prompt = get_prompt("direct_generation")
                except:
                    class SimplePrompt:
                        def compile(self, **kwargs):
                            return kwargs.get("prompt_content", "")
                    langfuse_prompt = SimplePrompt()

                result = await client.generate_with_context_tracking(
                    selected_model,
                    langfuse_prompt,
                    variables,
                    case_id=case_id,
                    document_type="report_section",
                    operation_type="template_section_generation",
                    source_file=f"{selected_template}_{section_prompt['name']}"
                )

                # Save individual section if requested
                if save_individual:
                    section_filename = f"section_{section_prompt['name'].replace(' ', '_').lower()}.md"
                    save_output_with_minimal_metadata(
                        result["content"],
                        section_filename,
                        {
                            **result["minimal_metadata"],
                            "template_source": selected_template,
                            "section_name": section_prompt['name']
                        }
                    )

                results.append({
                    "name": section_prompt['name'],
                    "content": result["content"],
                    "trace_id": result["minimal_metadata"].get("langfuse_trace_id"),
                    "section_index": section_prompt['section_index']
                })

                progress.progress((i + 1) / len(section_prompts))

            return results

        # Execute generation
        section_results = asyncio.run(generate_sections())

        st.success(f"✅ Generated {len(section_results)} sections from **{selected_template}**")

        # Display results with context links
        st.subheader("📄 Generated Report Sections")

        for result in section_results:
            with st.expander(f"📝 {result['name']}"):
                st.text_area(
                    "Content:",
                    value=result['content'],
                    height=200,
                    disabled=True,
                    key=f"content_{result['section_index']}"
                )

                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        "📥 Download Section",
                        data=result['content'],
                        file_name=f"{result['name'].replace(' ', '_')}.md",
                        mime="text/markdown",
                        key=f"download_{result['section_index']}"
                    )
                with col2:
                    if result['trace_id']:
                        show_generation_context_button(result['trace_id'])

        # Generate combined report
        if generate_combined:
            st.subheader("📋 Complete Report")

            combined_content = f"# Forensic Evaluation Report\n\n"
            combined_content += f"**Template**: {selected_template}\n"
            combined_content += f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            combined_content += f"**Case ID**: {case_id or 'Not specified'}\n\n---\n\n"

            # Add sections in order
            for result in sorted(section_results, key=lambda x: x['section_index']):
                combined_content += f"## {result['name']}\n\n{result['content']}\n\n"

            # Save with enhanced metadata
            combined_path = save_output_with_minimal_metadata(
                combined_content,
                f"report_{selected_template.replace('.md', '')}.md",
                {
                    "timestamp": datetime.now().isoformat(),
                    "operation_type": "complete_template_report",
                    "template_source": selected_template,
                    "total_sections": len(section_results),
                    "case_id": case_id,
                    "model_used": selected_model
                }
            )

            st.text_area("Complete Report:", value=combined_content, height=300, disabled=True)

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "📥 Download Complete Report",
                    data=combined_content,
                    file_name=f"report_{selected_template.replace('.md', '')}.md",
                    mime="text/markdown",
                    type="primary"
                )
            with col2:
                st.metric("Report Length", f"{len(combined_content.split())} words")

# Template Management Section
st.divider()
st.subheader("🔧 Template Management")

col1, col2 = st.columns(2)

with col1:
    st.write("**Your Local Templates**")
    st.write(f"📁 Stored in: `{processor.template_directory}`")

    if st.button("📂 Open Template Folder"):
        # Platform-specific code to open folder
        pass

with col2:
    st.write("**Template Actions**")
    if st.button("🔄 Refresh Template List"):
        st.rerun()

    if st.button("➕ Create New Template"):
        # Template creation interface
        pass
```

**Key UI Design Principles**:

- **Integrated Workflow**: Complete report lifecycle in a single interface - generation, refinement, and comparison
- **Template-First**: Template selection is the primary workflow entry point
- **Section Visibility**: Users can see how their template will be processed
- **Progress Transparency**: Clear indication of section-by-section processing
- **Context Access**: Every generation links to detailed Langfuse context
- **Local Control**: Easy access to template directory for user customization
- **Professional Output**: Generated reports maintain forensic standards
- **Iterative Improvement**: Seamless transition from generation to refinement with session state preservation

### 4.3. Summary Generation with Dynamic Model Selection (`pages/2_📋_Summary.py`)

Simplified implementation with auto-discovered models:

### 4.4. Human Evaluation with Native Langfuse Integration (`pages/5_🔬_Evaluation.py`)

Human-centric evaluation with native Langfuse integration:

```python
# pages/5_🔬_Evaluation.py
import streamlit as st
import asyncio
from datetime import datetime
from pathlib import Path
from lib.files import scan_for_markdown, read_metadata_from_file
from lib.prompts import get_langfuse_client
from lib.config import get_available_models
from lib.llm import get_llm_client
from lib.ui_components import show_generation_context_button, create_human_evaluation_interface

st.title("🔬 Human Evaluation & Testing")

tab1, tab2, tab3, tab4 = st.tabs(["📋 Manual Annotation", "⚖️ Side-by-Side Comparison", "📊 User Feedback", "🤖 Automated Evaluation"])

with tab1:
    st.subheader("Manual Annotation Queue")

    # Document selection for annotation
    annotation_dir = st.text_input("Generated Documents Directory", value="./outputs")

    if st.button("Load Annotation Queue"):
        if Path(annotation_dir).exists():
            markdown_files = scan_for_markdown(annotation_dir)
            # Filter files that need annotation
            unannotated_files = []
            for file_path in markdown_files:
                metadata = read_metadata_from_file(str(file_path))
                if not metadata.get("human_annotation_score"):
                    unannotated_files.append(str(file_path))

            st.session_state.annotation_queue = unannotated_files
            st.success(f"Loaded {len(unannotated_files)} documents needing annotation")

    if "annotation_queue" in st.session_state and st.session_state.annotation_queue:
        # Current document for annotation
        current_file = st.session_state.annotation_queue[0]
        st.info(f"Annotating: {Path(current_file).name}")

        # Read document content
        with open(current_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract metadata for context
        metadata = read_metadata_from_file(current_file)

        # Display document content
        st.text_area("Generated Content", value=content, height=300, disabled=True)

        # Show generation context button
        if metadata.get("langfuse_trace_id"):
            show_generation_context_button(metadata["langfuse_trace_id"], "🔍 View Generation Details")

        # Annotation interface
        col1, col2 = st.columns(2)

        with col1:
            accuracy_score = st.slider("Accuracy (1-5)", 1, 5, 3, key="accuracy")
            completeness_score = st.slider("Completeness (1-5)", 1, 5, 3, key="completeness")
            clarity_score = st.slider("Clarity (1-5)", 1, 5, 3, key="clarity")

        with col2:
            forensic_relevance = st.slider("Forensic Relevance (1-5)", 1, 5, 3, key="forensic")
            factual_accuracy = st.slider("Factual Accuracy (1-5)", 1, 5, 3, key="factual")
            ethical_compliance = st.slider("Ethical Compliance (1-5)", 1, 5, 3, key="ethical")

        annotation_notes = st.text_area("Annotation Notes", placeholder="Specific observations, corrections, or recommendations...")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("✅ Submit Annotation", type="primary"):
                # Calculate overall score
                overall_score = (accuracy_score + completeness_score + clarity_score +
                               forensic_relevance + factual_accuracy + ethical_compliance) / 6

                # Send annotation to Langfuse
                try:
                    langfuse_client = get_langfuse_client()
                    langfuse_client.score(
                        trace_id=metadata.get("langfuse_trace_id"),
                        name="human_annotation",
                        value=overall_score,
                        metadata={
                            "accuracy": accuracy_score,
                            "completeness": completeness_score,
                            "clarity": clarity_score,
                            "forensic_relevance": forensic_relevance,
                            "factual_accuracy": factual_accuracy,
                            "ethical_compliance": ethical_compliance,
                            "notes": annotation_notes,
                            "annotator": st.session_state.get("annotator_name", "unknown"),
                            "annotation_timestamp": datetime.now().isoformat()
                        }
                    )

                    # Remove from queue and advance
                    st.session_state.annotation_queue.pop(0)
                    st.success("Annotation submitted successfully!")
                    st.rerun()

                except Exception as e:
                    st.error(f"Failed to submit annotation: {e}")

        with col2:
            if st.button("⏭️ Skip Document"):
                st.session_state.annotation_queue.append(st.session_state.annotation_queue.pop(0))
                st.rerun()

        with col3:
            st.metric("Remaining", len(st.session_state.annotation_queue))

with tab2:
    st.subheader("Side-by-Side Model Comparison")

    # Model selection for comparison
    available_models = get_available_models()
    if len(available_models) >= 2:
        col1, col2 = st.columns(2)
        with col1:
            model_a = st.selectbox("Model A", available_models, key="model_a")
        with col2:
            model_b = st.selectbox("Model B", available_models, index=1, key="model_b")

        # Document selection
        test_document = st.text_area("Test Document Content", height=150)
        prompt_type = st.selectbox("Prompt Type", ["document-summary", "report-generation", "analysis"])

        if st.button("Generate Comparison") and test_document:
            async def run_comparison():
                client = get_llm_client()
                prompt = get_langfuse_client().get_prompt(prompt_type)

                variables = {"document_content": test_document}

                # Generate with both models
                result_a = await client.generate_with_context_tracking(
                    model_a, prompt, variables,
                    operation_type="comparison_a",
                    document_type="test_comparison"
                )

                result_b = await client.generate_with_context_tracking(
                    model_b, prompt, variables,
                    operation_type="comparison_b",
                    document_type="test_comparison"
                )

                return result_a, result_b

            with st.spinner("Generating responses..."):
                result_a, result_b = asyncio.run(run_comparison())

            # Display side-by-side comparison
            col1, col2 = st.columns(2)

            with col1:
                st.subheader(f"📊 {model_a}")
                st.text_area("Response A", value=result_a["content"], height=300, disabled=True)
                if result_a["minimal_metadata"].get("langfuse_trace_id"):
                    show_generation_context_button(result_a["minimal_metadata"]["langfuse_trace_id"])

            with col2:
                st.subheader(f"📊 {model_b}")
                st.text_area("Response B", value=result_b["content"], height=300, disabled=True)
                if result_b["minimal_metadata"].get("langfuse_trace_id"):
                    show_generation_context_button(result_b["minimal_metadata"]["langfuse_trace_id"])

            # Comparison voting
            st.subheader("Human Preference")
            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button(f"👍 Prefer {model_a}", type="primary"):
                    # Record preference in Langfuse
                    langfuse_client = get_langfuse_client()
                    langfuse_client.score(
                        trace_id=result_a["minimal_metadata"]["langfuse_trace_id"],
                        name="human_preference",
                        value=1.0,
                        metadata={"comparison_winner": model_a, "comparison_loser": model_b}
                    )
                    langfuse_client.score(
                        trace_id=result_b["minimal_metadata"]["langfuse_trace_id"],
                        name="human_preference",
                        value=0.0,
                        metadata={"comparison_winner": model_a, "comparison_loser": model_b}
                    )
                    st.success(f"{model_a} preference recorded!")

            with col2:
                if st.button(f"👍 Prefer {model_b}", type="primary"):
                    # Record preference in Langfuse
                    langfuse_client = get_langfuse_client()
                    langfuse_client.score(
                        trace_id=result_b["minimal_metadata"]["langfuse_trace_id"],
                        name="human_preference",
                        value=1.0,
                        metadata={"comparison_winner": model_b, "comparison_loser": model_a}
                    )
                    langfuse_client.score(
                        trace_id=result_a["minimal_metadata"]["langfuse_trace_id"],
                        name="human_preference",
                        value=0.0,
                        metadata={"comparison_winner": model_b, "comparison_loser": model_a}
                    )
                    st.success(f"{model_b} preference recorded!")

            with col3:
                if st.button("🤝 Tie/Equal"):
                    # Record tie in Langfuse
                    langfuse_client = get_langfuse_client()
                    for result, model in [(result_a, model_a), (result_b, model_b)]:
                        langfuse_client.score(
                            trace_id=result["minimal_metadata"]["langfuse_trace_id"],
                            name="human_preference",
                            value=0.5,
                            metadata={"comparison_result": "tie", "compared_models": [model_a, model_b]}
                        )
                    st.success("Tie recorded!")

with tab3:
    st.subheader("User Feedback Collection")

    # Load recent generations for feedback
    feedback_dir = st.text_input("Generated Documents Directory", value="./outputs", key="feedback_dir")

    if st.button("Load Recent Generations"):
        if Path(feedback_dir).exists():
            markdown_files = list(Path(feedback_dir).glob("*.md"))
            # Sort by modification time, most recent first
            recent_files = sorted(markdown_files, key=lambda x: x.stat().st_mtime, reverse=True)[:10]
            st.session_state.feedback_files = [str(f) for f in recent_files]
            st.success(f"Loaded {len(recent_files)} recent documents")

    if "feedback_files" in st.session_state:
        selected_file = st.selectbox("Select Document for Feedback", st.session_state.feedback_files)

        if selected_file:
            # Read and display document
            with open(selected_file, 'r', encoding='utf-8') as f:
                content = f.read()

            metadata = read_metadata_from_file(selected_file)

            st.text_area("Document Content", value=content, height=200, disabled=True)

            # Feedback interface
            col1, col2 = st.columns(2)

            with col1:
                overall_rating = st.slider("Overall Quality (1-5)", 1, 5, 3)
                usefulness = st.slider("Usefulness for Forensic Work (1-5)", 1, 5, 3)

            with col2:
                trust_score = st.slider("Trust in Output (1-5)", 1, 5, 3)
                would_use = st.radio("Would you use this in practice?", ["Yes", "No", "With modifications"])

            feedback_text = st.text_area("Detailed Feedback", placeholder="What worked well? What could be improved?")

            if st.button("Submit Feedback", type="primary"):
                try:
                    langfuse_client = get_langfuse_client()
                    langfuse_client.score(
                        trace_id=metadata.get("langfuse_trace_id"),
                        name="user_feedback",
                        value=overall_rating,
                        metadata={
                            "overall_rating": overall_rating,
                            "usefulness": usefulness,
                            "trust_score": trust_score,
                            "would_use": would_use,
                            "feedback_text": feedback_text,
                            "feedback_timestamp": datetime.now().isoformat()
                        }
                    )
                    st.success("Feedback submitted successfully!")
                except Exception as e:
                    st.error(f"Failed to submit feedback: {e}")

with tab4:
    st.subheader("Automated Evaluation (Optional)")
    st.info("Automated evaluation is available but secondary to human evaluation for forensic applications.")

    # Simplified automated evaluation options
    eval_type = st.selectbox("Evaluation Type", ["Basic Quality Checks", "Factual Consistency", "Format Validation"])

    if st.button("Run Automated Evaluation"):
        st.info("This feature can be implemented as needed, but human evaluation takes priority.")
```

### 4.3. Summary Generation with Dynamic Model Selection (`pages/2_📋_Summary.py`)

Simplified implementation with auto-discovered models:

```python
# pages/2_📋_Summary.py
import streamlit as st
import asyncio
from pathlib import Path
from lib.files import scan_for_markdown, save_output_with_minimal_metadata
from lib.prompts import get_prompt
from lib.llm import get_llm_client, add_session_cost

st.title("📋 Document Summary Generation")

# Get LLM client with auto-discovered models
client = get_llm_client()
available_models = client.get_available_models()

if not available_models:
    st.error("❌ No LLM models available. Please configure providers first.")
    st.stop()

# Directory selection
source_dir = st.text_input("Source Directory", value="./outputs")

if st.button("Scan for Markdown Files"):
    if Path(source_dir).exists():
        markdown_files = scan_for_markdown(source_dir)
        st.session_state.markdown_files = [str(f) for f in markdown_files]
        st.success(f"Found {len(markdown_files)} markdown files")
    else:
        st.error("Directory does not exist")

# Dynamic model selection with provider grouping
def show_model_selector():
    """Show grouped model selection"""
    models_by_provider = {}
    for model in available_models:
        provider = model.split("/")[0]
        if provider not in models_by_provider:
            models_by_provider[provider] = []
        models_by_provider[provider].append(model)

    # Show available providers in sidebar
    with st.sidebar:
        st.subheader("Available Providers")
        for provider, models in models_by_provider.items():
            st.success(f"✅ {provider.title()}: {len(models)} models")

    # Model selection with better formatting
    selected_model = st.selectbox(
        "Select Model",
        available_models,
        index=0,
        format_func=lambda x: f"{x.split('/')[0].title()}: {x.split('/')[1]}"
    )

    return selected_model

selected_model = show_model_selector()

# File selection for summarization
if "markdown_files" in st.session_state:
    selected_files = st.multiselect(
        "Select Files to Summarize",
        st.session_state.markdown_files
    )

    if st.button("Generate Summaries") and selected_files:
        async def generate_summaries():
            # Get prompt from Langfuse
            prompt = get_prompt("document-summary")

            progress_bar = st.progress(0)
            results = []

            for i, file_path in enumerate(selected_files):
                st.write(f"Processing: {file_path}")

                # Read file content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Generate summary with context tracking
                variables = {
                    "document_content": content,
                    "document_type": "forensic document"
                }

                result = await client.generate_with_context_tracking(
                    selected_model,
                    prompt,
                    variables,
                    document_type="forensic_summary",
                    operation_type="document_summary",
                    source_file=Path(file_path).name
                )

                summary = result["content"]

                # Save summary with minimal metadata
                summary_path = save_output_with_minimal_metadata(
                    summary,
                    f"summary_{Path(file_path).stem}.md",
                    result["minimal_metadata"]
                )

                results.append({
                    "file": file_path,
                    "summary_path": summary_path,
                    "summary": summary[:200] + "...",
                    "trace_id": result["minimal_metadata"].get("langfuse_trace_id")
                })

                # Update cost tracking
                add_session_cost(result["response"])

                # Update progress
                progress_bar.progress((i + 1) / len(selected_files))

            return results

        # Run async summary generation
        results = asyncio.run(generate_summaries())

        st.success(f"Generated {len(results)} summaries")
        for result in results:
            with st.expander(f"Summary: {Path(result['file']).name}"):
                st.write(result['summary'])
                st.caption(f"Saved to: {result['summary_path']}")

                # Show context button if available
                if result.get('trace_id'):
                    from lib.ui_components import show_generation_context_button
                    show_generation_context_button(result['trace_id'])
```

## 5. Data Management

### 5.1. Simplified File Handling with Native Observability

- **Streamlit Native Upload**: Use `st.file_uploader` for all document inputs
- **Local Directory Scanning**: Simple directory-based file management
- **Output Organization**: Timestamped files in `outputs/` directory
- **Minimal Metadata**: Lightweight YAML frontmatter with Langfuse trace links
- **Rich Context On-Demand**: Full generation context available via Langfuse integration

#### Generated Document Format (Hybrid Approach)

All summaries and reports include minimal YAML frontmatter that links to rich Langfuse context:

```yaml
---
timestamp: "2025-01-15T14:30:22.123456"
operation_type: "document_summary"
langfuse_trace_id: "trace_abc123"
langfuse_generation_id: "gen_def456"
model_key: "azure-gpt-4.1"
prompt_name: "document-summary"
source_file: "police_report_001.md"
case_id: "case_2025_001"
---
# Document Summary

[Generated content follows here...]
```

#### Rich Context via Native Integrations

**LiteLLM → Langfuse Automatic Tracing** captures complete generation context:

- **Full prompts** (system + user) with variable substitution
- **Model details** and provider information
- **Token usage** and cost breakdown
- **Response metadata** and performance metrics
- **Document lineage** through custom tags

**Streamlit UI Components** provide on-demand access:

- "🔍 View Generation Context" buttons fetch rich data from Langfuse
- Progressive disclosure: simple view → detailed context when needed
- Direct Langfuse links for power users

This hybrid approach provides:

- **Clean Documents**: Minimal metadata keeps files readable and focused
- **Complete Transparency**: Full context available when needed via Langfuse API
- **Zero Manual Overhead**: LiteLLM automatically captures everything
- **Enterprise Observability**: Centralized tracking, analytics, and search
- **Performance**: No API calls unless user requests details

### 5.2. Simple State Management

- **Session State**: Use `st.session_state` for UI state and cost tracking
- **Caching**: `st.cache_resource` for expensive objects, `st.cache_data` for serializable data
- **No Complex State Management**: Embrace Streamlit's reactive model

### 5.3. Native Integrations

- **LiteLLM → Langfuse**: Automatic tracing via built-in callbacks
- **Langfuse Native Evaluation**: Built-in prompt testing and comparison tools
- **Langfuse Prompt CMS**: Central prompt management with local fallbacks

## 6. Human-Centric Evaluation Framework

### 6.1. Evaluation Philosophy for Forensic Applications

For forensic psychiatry and psychology applications, **human evaluation takes precedence over automated metrics**. While LLM-as-a-judge tools have their place, the critical nature of forensic work demands expert human oversight at every stage.

**Why Human Evaluation is Critical**:

- **Legal Accountability**: Forensic reports may be used in legal proceedings where human judgment is required
- **Ethical Standards**: Professional ethical guidelines require human oversight of AI-generated content
- **Domain Expertise**: Forensic psychologists understand nuances that automated tools cannot capture
- **Quality Assurance**: Human evaluation catches errors that automated metrics might miss

### 6.2. Three-Tier Human Evaluation System

**1. Manual Annotation Queue**

- Structured evaluation workflow for generated documents
- Forensic-specific scoring criteria (accuracy, completeness, ethical compliance)
- Collaborative annotation with multiple expert reviewers
- Progress tracking and quality metrics

**2. Side-by-Side Model Comparison**

- Real-time comparison of different models on identical inputs
- Evidence-based model selection for different document types
- Human preference recording with detailed justification
- Cost-quality trade-off analysis

**3. User Feedback Collection**

- Professional usability assessment from practicing forensic psychologists
- Trust and confidence ratings for AI-generated content
- Detailed qualitative feedback for iterative improvement
- Integration with daily forensic workflow

### 6.3. Native Langfuse Integration Benefits

**Seamless Data Flow**:

- All human evaluations automatically captured in Langfuse traces
- Rich metadata linking evaluations to generation context
- No additional infrastructure or manual data export required

**Complete Audit Trail**:

- Full forensic lineage from source document to final evaluation
- Professional accountability through comprehensive logging
- Regulatory compliance through immutable evaluation records

**Progressive Disclosure**:

- Clean evaluation interfaces with detailed context available on-demand
- Evaluators can access full generation details when needed
- Balanced simplicity and transparency

## 7. Enhanced Observability & Transparency

### 7.1. LiteLLM Enhanced Callbacks with Smart Tagging

Leverage LiteLLM's callback system for automatic enrichment:

```python
# Custom callback for forensic document lineage
def forensic_callback(kwargs, response, start_time, end_time):
    langfuse.tag_generation(
        trace_id=response.trace_id,
        tags=[
            f"case:{case_id}",
            f"doc_type:{document_type}",
            f"operation:{operation_type}",
            f"model:{model_key}",
            f"prompt_version:{prompt_label}"
        ],
        metadata={
            "document_chain": document_lineage,
            "source_file": source_filename,
            "cost_center": cost_center
        }
    )
```

**Benefits**:

- **Smart Organization**: Filter by case, document type, model, or prompt version
- **Document Lineage**: Track how summaries feed into reports
- **Cost Analysis**: "How much did Case X cost across all documents?"
- **Quality Tracking**: See impact of prompt changes over time

### 7.2. Streamlit UI Components for Context Discovery

Enhanced UI patterns for transparency:

```python
# On-demand context fetching
def show_generation_context(trace_id: str):
    if st.button("🔍 View Generation Context"):
        trace_data = langfuse.get_trace(trace_id)

        # Rich metrics display
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Cost", f"${trace_data.cost:.4f}")
        with col2:
            st.metric("Tokens", trace_data.usage.total)
        with col3:
            st.metric("Duration", f"{trace_data.duration}ms")

        # Progressive disclosure
        with st.expander("🔧 Prompt Details"):
            st.code(trace_data.input.system_prompt)
            st.json(trace_data.input.variables)

        with st.expander("🔗 Related Documents"):
            show_document_lineage(trace_data.tags)

        # Direct Langfuse link for power users
        st.link_button("🌐 Open in Langfuse",
                      f"{LANGFUSE_HOST}/trace/{trace_id}")
```

### 7.3. Native Langfuse Evaluation Tools

Leverage Langfuse's built-in evaluation capabilities directly through the Streamlit interface:

```python
# Native Langfuse evaluation in Streamlit
def create_prompt_comparison_interface():
    """Compare different prompt versions using native Langfuse tools"""

    # Get prompt versions from Langfuse
    prompt_versions = langfuse_client.get_prompt_versions("document-summary")

    col1, col2 = st.columns(2)
    with col1:
        version_a = st.selectbox("Prompt Version A", prompt_versions)
    with col2:
        version_b = st.selectbox("Prompt Version B", prompt_versions)

    # Test document selection
    test_document = st.text_area("Test Document", height=150)

    if st.button("Compare Prompt Versions"):
        # Generate with both versions
        results_a = await client.generate_with_prompt(
            selected_model, version_a, {"document": test_document}
        )
        results_b = await client.generate_with_prompt(
            selected_model, version_b, {"document": test_document}
        )

        # Side-by-side display with evaluation
        display_comparison_results(results_a, results_b)

def create_model_evaluation_interface():
    """Compare different models on same prompt using Langfuse datasets"""

    # Load evaluation dataset from Langfuse
    dataset = langfuse_client.get_dataset("forensic_evaluation_set")

    selected_models = st.multiselect("Models to Compare", available_models)

    if st.button("Run Model Comparison"):
        evaluation_results = {}

        for model in selected_models:
            model_results = []
            for item in dataset.items:
                result = await client.generate_with_context_tracking(
                    model, item.prompt, item.variables,
                    operation_type="model_evaluation",
                    dataset_item_id=item.id
                )
                model_results.append(result)

            evaluation_results[model] = model_results

        # Display comparative results
        display_model_comparison_results(evaluation_results)
```

**Workflow Benefits**:

- **Native Integration**: Direct access to Langfuse prompt management and datasets
- **Real-time Comparison**: Live model and prompt version testing within Streamlit
- **Evaluation Datasets**: Reusable test sets managed in Langfuse
- **Cost Tracking**: Automatic cost comparison across models and prompts
- **Quality Metrics**: Human evaluation scores tracked alongside automated metrics

### 7.4. Case-Based Organization

Smart tagging enables case-centric workflows:

```python
# Case dashboard components
def show_case_dashboard(case_id: str):
    # Fetch all generations for this case
    traces = langfuse.get_traces(tags=[f"case:{case_id}"])

    # Case summary metrics
    total_cost = sum(t.cost for t in traces)
    total_docs = len(set(t.metadata.get("source_file") for t in traces))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Cost", f"${total_cost:.2f}")
    with col2:
        st.metric("Documents Processed", total_docs)
    with col3:
        st.metric("AI Generations", len(traces))

    # Document lineage visualization
    show_document_flow(traces)
```

## 8. Benefits of Simplified Multi-Provider Architecture

### 8.1. Simplified Configuration with Enhanced Capabilities

- **Auto-discovery of models** - no manual model lists to maintain
- **Smart provider detection** - automatically enables available providers
- **Minimal environment setup** - just API keys, everything else auto-configured
- **Built-in transparency** through minimal metadata + rich Langfuse context
- **Zero-overhead observability** via LiteLLM automatic tracing

### 8.2. Multi-Provider Flexibility with Single-User Simplicity

- **Multiple LLM providers** (Azure OpenAI, Anthropic, Gemini) via single interface
- **Automatic model discovery** from each configured provider
- **Smart fallback strategies** - automatically recommends best available model
- **Cost optimization** through provider comparison and tracking
- **No vendor lock-in** - easily switch between providers

### 8.3. Production-Ready Observability

- **Automatic Langfuse tracing** for all LLM calls via LiteLLM
- **Forensic document lineage** through metadata tracking
- **Cost analysis** across providers and models
- **Human-centric quality evaluation** with comprehensive annotation workflows
- **Case-centric organization** for forensic workflow tracking

### 8.4. Developer Experience Optimized for Single User

- **One-command setup** with interactive configuration
- **Visual provider status** showing available models and capabilities
- **Real-time model testing** to validate configuration
- **Progressive disclosure** - simple UI with expert features available
- **Easy distribution** via Docker or standalone executable

### 8.5. Forensic Psychology Workflow Alignment

- **Document pipeline tracing** from PDF → summary → report with full audit trails
- **Human-centric quality assurance** through comprehensive annotation workflows
- **Side-by-side model comparison** for evidence-based model selection
- **Professional feedback collection** tailored to forensic practice standards
- **Cost control** for expensive forensic document processing
- **Evidence lineage** through comprehensive metadata and Langfuse integration
- **Forensic-specific evaluation criteria** (accuracy, ethical compliance, professional usability)
- **Intelligent document chunking** that preserves Azure DocumentIntelligence structure while respecting model context windows
- **Section-aware processing** with automatic progress tracking and transparent chunking decisions

### 8.6. Document Chunking Strategy

**Philosophy**: Leverage Azure DocumentIntelligence's natural markdown structure rather than creating complex custom logic.

**Implementation Approach**:

- **Header-First Chunking**: Use LangChain's `MarkdownHeaderTextSplitter` to respect document structure
- **Model-Aware Sizing**: Automatically adjust chunk sizes based on target model context windows
- **Boundary Preservation**: Split on semantic boundaries (headers, paragraphs, sentences) not arbitrary character counts
- **Transparency**: Show users exactly how documents are being split with clear progress indicators

**Key Benefits**:

- **Maintains Context**: Headers provide semantic meaning for each chunk
- **Simple & Reliable**: Uses proven LangChain components rather than custom implementations
- **Model Compatibility**: Automatically adapts to different LLM context window sizes
- **Debug-Friendly**: Rich metadata and preview utilities for troubleshooting
- **Forensic Appropriate**: Respects document structure without over-engineering

**Workflow Integration**:

1. Azure DocumentIntelligence creates structured markdown with headers
2. `SimpleHeaderChunking` splits on headers while checking model context windows
3. Large header sections are further split while preserving header context
4. Each chunk retains full header hierarchy in metadata
5. Results are intelligently recombined with section headers preserved
6. Full audit trail maintained through Langfuse integration

This approach balances simplicity with effectiveness, avoiding the complexity of domain-specific chunking while still respecting the inherent structure of forensic documents.

### 8.7. Template-Driven Professional Workflow

- **User Template Ownership** - Forensic professionals maintain and customize their own standardized templates
- **Section-Based Quality Control** - Each report section receives focused LLM attention for better accuracy
- **Professional Standards Compliance** - Templates encode established forensic reporting practices
- **Workflow Integration** - Seamless integration with existing forensic evaluation processes
- **Consistency Across Cases** - All reports follow user's established professional standards
- **Iterative Template Improvement** - Users can refine templates based on experience and feedback
- **Local Version Control** - Templates can be version controlled with Git alongside case files
- **Multi-Evaluation Support** - Different templates for competency, risk assessment, etc.

## 9. Future Enhancements

As needed, the following can be added while maintaining simplicity:

- **Advanced Error Handling**: Structured error management
- **Multiple Output Formats**: PDF, DOCX export options
- **Batch Processing**: Queue-based processing for large datasets
- **Enhanced Human Evaluation Tools**: Advanced annotation workflows, inter-rater reliability metrics
- **Automated Evaluation Integration**: Optional LLM-as-a-judge tools when human evaluation capacity is reached

**Note**: The architecture prioritizes human evaluation as the primary quality assurance mechanism for forensic applications, leveraging Langfuse's native evaluation tools for systematic prompt and model comparison. These tools supplement, rather than replace, expert human judgment.

The key principle is to add complexity only when necessary and always favor native integrations over custom implementations.
