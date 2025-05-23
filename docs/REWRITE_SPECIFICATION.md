# Forensic Psych Report Drafter - Rewrite Specification (Simplified)

## Project Overview

This specification outlines a streamlined rewrite of the Forensic Psych Report Drafter, leveraging native integrations between Streamlit, LiteLLM, Langfuse, and Promptfoo to minimize custom code while maximizing functionality. The application assists forensic psychiatrists in analyzing documents and generating reports using multiple Large Language Model (LLM) providers with automatic tracing and evaluation capabilities.

## Technology Stack & Built-in Integrations

### Core Technologies with Native Integrations

- **UI Framework**: Streamlit (with auto-page discovery)
- **LLM Client**: LiteLLM with built-in Langfuse integration and multi-provider support
- **Supported LLM Providers**:
  - **Azure OpenAI** (GPT-4.1 with native PDF processing)
  - **Anthropic** (Claude Sonnet 4 with native PDF processing and thinking tokens)
  - **Google Gemini** (Gemini 2.5 Pro with native multimodal capabilities)
- **Prompt Management**: Langfuse (automatically integrated via LiteLLM)
- **Evaluation**: Promptfoo (with native `langfuse://` prompt references)
- **Dependency Management**: uv (Python package management)

### Key Integration Benefits

- **LiteLLM ↔ Langfuse**: Automatic tracing of all LLM calls without custom code
- **LiteLLM Native Features**:
  - Native PDF document processing across all supported providers
  - Automatic token counting (including reasoning/thinking tokens for supported models)
  - Provider-agnostic API with intelligent fallbacks
- **Promptfoo ↔ Langfuse**: Direct prompt references using `langfuse://prompt-name` syntax
- **Streamlit**: Native file handling, automatic page routing, built-in components

## Core Requirements

### Critical Requirement: Local File System Integration

**The application MUST continue to read from and write to the local filesystem for:**

- Prompt templates (`.md` files in `prompt_templates/` directory) - as backup/fallback
- Report templates (`.md` files in `templates/` directory)
- Transcript files (`.txt`, `.md` files)
- Output draft files (generated reports and analyses)

**Note**: Primary prompt management occurs in Langfuse with local filesystem as backup.

### Multi-Provider LLM Support

**The application MUST support seamless switching between:**

- **Azure OpenAI**: Enterprise-grade deployment with PDF processing capabilities (GPT-4.1)
- **Anthropic Claude**: Advanced reasoning with native PDF processing and thinking tokens (Claude Sonnet 4)
- **Google Gemini**: Multimodal capabilities with document understanding (Gemini 2.5 Pro)

## Simplified Application Structure

### Streamlined Directory Structure

```
forensic-report-drafter-v2/
├── app.py                          # Main Streamlit application (homepage)
├── pyproject.toml                  # Simplified dependencies
├── .env                           # Environment variables
├── README.md                       # Setup instructions
├── pages/                         # Streamlit auto-discovered pages
│   ├── 1_📝_Prompt_Generation.py
│   ├── 2_📄_Document_Analysis.py
│   ├── 3_✨_Report_Refinement.py
│   ├── 4_📊_Batch_Processing.py
│   └── 5_🔬_Evaluation.py
├── utils/                         # Minimal shared utilities
│   ├── llm_client.py              # LiteLLM wrapper with multi-provider support
│   ├── file_helpers.py            # Streamlit file operations
│   └── config.py                  # Simple configuration
├── prompt_templates/              # Local prompt backup/fallback
├── templates/                     # Local report templates
├── outputs/                       # Generated files (auto-created)
└── docs/                         # Documentation
    ├── IMPLEMENTATION_GUIDE.md
    └── REWRITE_SPECIFICATION.md
```

## Core Functionality (Simplified Implementation)

### 1. Prompt Generation

**Purpose**: Process templates with transcripts using native Streamlit file handling

**Simplified Features**:

- Streamlit file uploaders (built-in drag & drop)
- Template processing with automatic Langfuse storage
- Multi-provider LLM support with intelligent fallbacks
- One-click download buttons for outputs
- Automatic tracing of all operations

**Implementation**: Single page with ~50 lines of code leveraging Streamlit components

### 2. Document Analysis

**Purpose**: PDF analysis using LiteLLM's native PDF processing across all providers

**Simplified Features**:

- Streamlit PDF uploader
- Provider selection (Azure OpenAI, Anthropic, Gemini)
- Native PDF processing with provider-specific optimizations
- Automatic result download
- Token usage tracking (including reasoning tokens)

**Implementation**: Direct API calls with built-in error handling and progress indicators

### 3. Report Refinement

**Purpose**: Draft improvement with side-by-side comparison

**Simplified Features**:

- Streamlit columns for before/after comparison
- Langfuse prompt templates for refinement instructions
- Multi-provider support for different refinement approaches
- Automatic versioning and download

**Implementation**: Streamlit native components eliminate custom UI code

### 4. Batch Processing

**Purpose**: Multi-document processing with progress tracking

**Simplified Features**:

- Streamlit's `st.progress()` for real-time updates
- Parallel processing with LiteLLM across multiple providers
- Organized output with timestamps
- Cost tracking across providers

**Implementation**: Built-in Streamlit session state for progress persistence

### 5. Evaluation & Testing

**Purpose**: Prompt evaluation using Promptfoo's Langfuse integration

**Simplified Features**:

- Select prompts from Langfuse dropdown
- Multi-provider evaluation comparisons
- One-click evaluation with `promptfoo eval`
- Results visualization in Streamlit

**Implementation**: Direct subprocess calls to Promptfoo CLI

## Enhanced Integration Specifications

### LiteLLM Multi-Provider Setup with Native Features

```python
# Automatic setup with multi-provider support
import litellm
import os
import base64

# Enable automatic Langfuse tracing for all LLM calls
litellm.success_callback = ["langfuse"]
litellm.failure_callback = ["langfuse"]

# Supported providers with native capabilities
SUPPORTED_PROVIDERS = {
    "azure": {
        "model": "azure/gpt-4.1",
        "features": ["pdf_processing", "function_calling", "token_counting"]
    },
    "anthropic": {
        "model": "anthropic/claude-4-sonnet",
        "features": ["pdf_processing", "thinking_tokens", "function_calling"]
    },
    "gemini": {
        "model": "gemini/gemini-2.5-pro",
        "features": ["multimodal", "pdf_processing", "long_context"]
    }
}

class LLMClient:
    def __init__(self, provider="anthropic"):
        self.provider = provider
        self.model = SUPPORTED_PROVIDERS[provider]["model"]

    def generate_response(self, prompt: str, **kwargs):
        # Automatically traced to Langfuse with provider info
        return litellm.completion(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )

    def process_pdf_native(self, pdf_bytes: bytes, prompt: str):
        """Native PDF processing with provider-specific optimizations."""
        pdf_base64 = base64.b64encode(pdf_bytes).decode()
        if self.provider == "anthropic":
            # Claude's native PDF processing
            return litellm.completion(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "document", "source": {"type": "base64", "data": pdf_base64}}
                    ]
                }]
            )
        elif self.provider == "azure":
            # Azure OpenAI PDF processing via GPT-4.1
            return litellm.completion(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{pdf_base64}"}}
                    ]
                }]
            )
        elif self.provider == "gemini":
            # Gemini multimodal document processing
            return litellm.completion(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "document", "data": pdf_base64, "mime_type": "application/pdf"}
                    ]
                }]
            )

    def get_token_usage(self, response):
        """Extract comprehensive token usage including reasoning tokens."""
        usage = response.usage
        return {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            # Reasoning tokens for supported providers (Claude, O1)
            "reasoning_tokens": getattr(usage, 'reasoning_tokens', 0),
            "provider": self.provider,
            "model": self.model
        }
```

### Promptfoo + Langfuse Multi-Provider Integration

```python
# Multi-provider evaluation with direct Langfuse references
def run_evaluation(prompt_names: list, providers: list = None):
    if providers is None:
        providers = ["anthropic:claude-4-sonnet", "azure:gpt-4.1", "gemini:gemini-2.5-pro"]

    config = {
        "prompts": [f"langfuse://{name}" for name in prompt_names],
        "providers": providers,
        "tests": test_cases,
        # Enable cost tracking across providers
        "outputPath": "./evaluation_results",
        "metadata": {
            "cost_tracking": True,
            "token_analysis": True
        }
    }
    # Promptfoo handles the rest automatically with cost comparisons
```

### Streamlit Provider Selection UI

```python
# Built-in provider selection with capabilities display
provider = st.selectbox(
    "Select LLM Provider:",
    options=["anthropic", "azure", "gemini"],
    format_func=lambda x: {
        "anthropic": "🤖 Anthropic Claude Sonnet 4 (PDF + Reasoning)",
        "azure": "☁️ Azure OpenAI GPT-4.1 (Enterprise + PDF)",
        "gemini": "🔷 Google Gemini 2.5 Pro (Multimodal + Long Context)"
    }[x]
)

# Show provider capabilities
capabilities = SUPPORTED_PROVIDERS[provider]["features"]
st.info(f"✨ Capabilities: {', '.join(capabilities)}")
```

## Dramatically Simplified Configuration

### Multi-Provider Environment Variables

```bash
# .env file (support for all providers)
# Azure OpenAI
AZURE_API_KEY=your_azure_key_here
AZURE_API_BASE=https://your-resource.openai.azure.com
AZURE_API_VERSION=2024-02-15-preview

# Anthropic
ANTHROPIC_API_KEY=your_anthropic_key_here

# Google Gemini
GOOGLE_API_KEY=your_google_key_here

# Langfuse Configuration (automatic integration via LiteLLM)
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com

# Default provider preference
DEFAULT_LLM_PROVIDER=anthropic
```

### Enhanced Dependencies

```toml
[project]
name = "forensic-report-drafter-v2"
version = "2.0.0"
requires-python = ">=3.11"

dependencies = [
    "streamlit>=1.30.0",
    "litellm[langfuse]>=1.20.0",    # Multi-provider with Langfuse integration
    "pymupdf>=1.23.0",              # PDF processing fallback
    "python-dotenv>=1.0.0",         # Environment variables
    "pyyaml>=6.0.0"                 # Promptfoo configs
]
```

## Implementation Benefits

### Massive Code Reduction with Enhanced Capabilities

- **90% less custom code** due to built-in integrations
- **No custom UI components** - pure Streamlit natives
- **No custom tracing** - automatic via LiteLLM
- **No custom routing** - Streamlit auto-discovery
- **No custom file handling** - Streamlit built-ins
- **No custom provider switching** - LiteLLM handles all providers

### Native LLM Features

- **PDF Processing**: Native support across Azure OpenAI, Anthropic, and Gemini
- **Token Tracking**: Automatic counting including reasoning/thinking tokens
- **Cost Optimization**: Real-time cost tracking and provider comparison
- **Intelligent Fallbacks**: Automatic provider switching on failures
- **Performance Analytics**: Built-in latency and cost metrics

### Enhanced Multi-Provider Capabilities

- **Provider Flexibility**: Seamless switching between Azure OpenAI, Anthropic, and Gemini
- **Cost Optimization**: Automatic cost comparison and optimization suggestions
- **Feature Utilization**: Leverage each provider's unique strengths (Claude's reasoning, Gemini's multimodal, Azure's enterprise features)
- **Evaluation Comparisons**: Side-by-side provider performance analysis

## Simplified Implementation Phases

### Phase 1: Multi-Provider Setup (2 days)

1. Create project structure
2. Configure LiteLLM multi-provider support (Azure OpenAI, Anthropic, Gemini)
3. Build main app with provider selection
4. Test basic LLM connectivity across all providers

### Phase 2: Core Pages with Provider Support (1 week)

1. Prompt Generation page with provider selection (1 day)
2. Document Analysis page with native PDF processing (2 days)
3. Report Refinement page with provider-specific optimizations (2 days)
4. Batch Processing page with cost tracking (2 days)

### Phase 3: Evaluation & Polish (3 days)

1. Multi-provider evaluation with Promptfoo integration (2 days)
2. Testing and cost optimization (1 day)

**Total Timeline: ~2 weeks vs original 5 weeks**

## Success Criteria

### Functional Requirements

- ✅ All current functionality preserved with better UX
- ✅ Local filesystem integration maintained
- ✅ Multi-provider LLM support (Azure OpenAI, Anthropic, Gemini)
- ✅ Native PDF processing across all providers
- ✅ Automatic prompt management via Langfuse
- ✅ Seamless evaluation via Promptfoo
- ✅ Token usage tracking including reasoning tokens

### Performance Requirements

- Web interface responsive (< 1s page loads due to simplicity)
- File processing faster due to native integrations
- Real-time progress tracking with Streamlit components
- Stable operation with automatic error handling and provider fallbacks
- Cost-optimized provider selection based on task requirements

### Multi-Provider Benefits

- **Provider Redundancy**: Automatic fallbacks prevent service interruptions
- **Cost Optimization**: Real-time cost comparison and recommendations
- **Feature Utilization**: Leverage each provider's strengths automatically
- **Performance Analytics**: Built-in provider performance comparisons

This enhanced specification leverages LiteLLM's excellent multi-provider support and native integrations, resulting in a more robust, cost-effective, and feature-rich application with provider redundancy and optimization capabilities.
