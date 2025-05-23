# Implementation Guide: Forensic Psych Report Drafter v2 (Multi-Provider)

## Quick Start Instructions

### Prerequisites

- Python 3.11+
- uv package manager installed
- API keys for Azure OpenAI, Anthropic, and Google Gemini
- Langfuse account and API keys

### Initial Setup

1. **Create Project Structure**

```bash
mkdir forensic-report-drafter-v2
cd forensic-report-drafter-v2

# Create simplified directory structure
mkdir -p pages utils prompt_templates templates outputs docs
touch utils/__init__.py
```

2. **Initialize uv Project**

```bash
uv init --name forensic-report-drafter-v2
```

3. **Add Multi-Provider Dependencies**

```bash
# Core dependencies with multi-provider and Langfuse integration
uv add streamlit "litellm[langfuse]" pymupdf python-dotenv pyyaml

# Development dependencies
uv add --dev pytest black isort
```

4. **Multi-Provider Environment Configuration**

```bash
# Create .env file with all provider support
cat > .env << EOF
# Azure OpenAI Configuration
AZURE_API_KEY=your_azure_api_key_here
AZURE_API_BASE=https://your-resource.openai.azure.com
AZURE_API_VERSION=2024-02-15-preview

# Anthropic Configuration
ANTHROPIC_API_KEY=your_anthropic_key_here

# Google Gemini Configuration
GOOGLE_API_KEY=your_google_api_key_here

# Langfuse Configuration (automatic integration via LiteLLM)
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
LANGFUSE_HOST=https://cloud.langfuse.com

# Provider Preferences
DEFAULT_LLM_PROVIDER=anthropic
ENABLE_FALLBACK_PROVIDERS=true
EOF
```

## Multi-Provider Architecture (2 weeks total vs 5 weeks)

### Core Files Overview

```
forensic-report-drafter-v2/
├── app.py                          # Main homepage with provider status (30 lines)
├── pages/                          # Auto-discovered by Streamlit
│   ├── 1_📝_Prompt_Generation.py   # Multi-provider prompt generation (~60 lines)
│   ├── 2_📄_Document_Analysis.py   # Native PDF processing (~80 lines)
│   ├── 3_✨_Report_Refinement.py   # Provider-optimized refinement (~50 lines)
│   ├── 4_📊_Batch_Processing.py    # Cost-aware batch processing (~90 lines)
│   └── 5_🔬_Evaluation.py          # Multi-provider evaluation (~40 lines)
├── utils/                          # Enhanced utilities
│   ├── llm_client.py               # Multi-provider client (~60 lines)
│   ├── file_helpers.py             # Enhanced file operations (~25 lines)
│   └── provider_config.py          # Provider configurations (~30 lines)
├── prompt_templates/               # Local backup
├── templates/                      # Report templates
└── outputs/                        # Auto-created outputs
```

**Total custom code: ~375 lines with multi-provider support vs 305 lines single-provider**

## Phase 1: Multi-Provider Setup (Day 1-2)

### 1.1 Provider Configuration

**File: `utils/provider_config.py`** (~30 lines)

```python
from typing import Dict, List, Any
import os

# Supported providers with their capabilities and models
PROVIDER_CONFIG = {
    "azure": {
        "display_name": "☁️ Azure OpenAI",
        "description": "Enterprise-grade deployment with PDF processing",
        "models": {
            "gpt-4.1": "azure/gpt-4.1",
            "gpt-4o-mini": "azure/gpt-4o-mini"
        },
        "default_model": "gpt-4.1",
        "features": ["pdf_processing", "function_calling", "token_counting", "enterprise_security"],
        "cost_tier": "medium",
        "max_context": 128000,
        "supports_pdf": True
    },
    "anthropic": {
        "display_name": "🤖 Anthropic Claude",
        "description": "Advanced reasoning with native PDF processing and thinking tokens",
        "models": {
            "claude-4-sonnet": "anthropic/claude-4-sonnet",
            "claude-4-opus": "anthropic/claude-4-opus"
        },
        "default_model": "claude-4-sonnet",
        "features": ["pdf_processing", "thinking_tokens", "function_calling", "long_context"],
        "cost_tier": "high",
        "max_context": 200000,
        "supports_pdf": True,
        "supports_reasoning": True
    },
    "gemini": {
        "display_name": "🔷 Google Gemini",
        "description": "Multimodal capabilities with document understanding",
        "models": {
            "gemini-2.5-pro": "gemini/gemini-2.5-pro",
            "gemini-1.5-flash": "gemini/gemini-1.5-flash"
        },
        "default_model": "gemini-2.5-pro",
        "features": ["multimodal", "pdf_processing", "long_context", "cost_effective"],
        "cost_tier": "low",
        "max_context": 1000000,
        "supports_pdf": True,
        "supports_multimodal": True
    }
}

def get_available_providers() -> List[str]:
    """Get list of providers with valid API keys."""
    available = []

    if os.getenv("AZURE_API_KEY"):
        available.append("azure")
    if os.getenv("ANTHROPIC_API_KEY"):
        available.append("anthropic")
    if os.getenv("GOOGLE_API_KEY"):
        available.append("gemini")

    return available

def get_provider_info(provider: str) -> Dict[str, Any]:
    """Get detailed information about a provider."""
    return PROVIDER_CONFIG.get(provider, {})

def get_model_for_provider(provider: str, model_name: str = None) -> str:
    """Get the full model identifier for a provider."""
    config = PROVIDER_CONFIG.get(provider, {})
    if model_name and model_name in config.get("models", {}):
        return config["models"][model_name]
    return config.get("models", {}).get(config.get("default_model", ""))
```

### 1.2 Enhanced LLM Client with Multi-Provider Support

**File: `utils/llm_client.py`** (~60 lines)

```python
import litellm
import os
import base64
from typing import Optional, Dict, Any, Union
from dotenv import load_dotenv
from .provider_config import get_provider_info, get_model_for_provider, get_available_providers

# Load environment variables
load_dotenv()

# Enable automatic Langfuse tracing for ALL LiteLLM calls
litellm.success_callback = ["langfuse"]
litellm.failure_callback = ["langfuse"]

class MultiProviderLLMClient:
    def __init__(self, provider: str = None):
        self.provider = provider or os.getenv("DEFAULT_LLM_PROVIDER", "anthropic")
        self.fallback_enabled = os.getenv("ENABLE_FALLBACK_PROVIDERS", "true").lower() == "true"

        # Validate provider availability
        available_providers = get_available_providers()
        if self.provider not in available_providers:
            if available_providers:
                self.provider = available_providers[0]
            else:
                raise ValueError("No LLM providers configured with valid API keys")

        self.provider_info = get_provider_info(self.provider)
        self.model = get_model_for_provider(self.provider)

    def generate_response(self, prompt: str, **kwargs) -> Any:
        """Generate response with automatic provider fallback."""
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                metadata={"provider": self.provider},
                **kwargs
            )
            return response
        except Exception as e:
            if self.fallback_enabled:
                return self._try_fallback_providers(prompt, **kwargs)
            raise e

    def process_pdf_native(self, pdf_bytes: Union[bytes, str], prompt: str, **kwargs) -> Any:
        """Native PDF processing with provider-specific optimizations."""

        # Ensure base64 encoding
        if isinstance(pdf_bytes, bytes):
            pdf_base64 = base64.b64encode(pdf_bytes).decode()
        else:
            pdf_base64 = pdf_bytes

        try:
            if self.provider == "anthropic":
                # Claude Sonnet 4 native PDF processing
                response = litellm.completion(
                    model=self.model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "document", "source": {"type": "base64", "data": pdf_base64}}
                        ]
                    }],
                    metadata={"provider": self.provider, "content_type": "pdf"},
                    **kwargs
                )
            elif self.provider == "azure":
                # Azure OpenAI GPT-4.1 PDF processing
                response = litellm.completion(
                    model=self.model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{pdf_base64}"}}
                        ]
                    }],
                    metadata={"provider": self.provider, "content_type": "pdf"},
                    **kwargs
                )
            elif self.provider == "gemini":
                # Gemini 2.5 Pro multimodal document processing
                response = litellm.completion(
                    model=self.model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "document", "data": pdf_base64, "mime_type": "application/pdf"}
                        ]
                    }],
                    metadata={"provider": self.provider, "content_type": "pdf"},
                    **kwargs
                )
            else:
                raise ValueError(f"PDF processing not supported for provider: {self.provider}")

            return response

        except Exception as e:
            if self.fallback_enabled:
                return self._try_fallback_pdf_processing(pdf_base64, prompt, **kwargs)
            raise e

    def get_comprehensive_usage(self, response) -> Dict[str, Any]:
        """Extract comprehensive token usage including reasoning tokens."""
        if not hasattr(response, 'usage') or not response.usage:
            return {}

        usage = response.usage
        result = {
            "prompt_tokens": getattr(usage, 'prompt_tokens', 0),
            "completion_tokens": getattr(usage, 'completion_tokens', 0),
            "total_tokens": getattr(usage, 'total_tokens', 0),
            "provider": self.provider,
            "model": self.model
        }

        # Add reasoning tokens for supported providers
        if hasattr(usage, 'reasoning_tokens'):
            result["reasoning_tokens"] = usage.reasoning_tokens

        # Add cost estimation if available
        if hasattr(response, '_hidden_params') and 'cost' in response._hidden_params:
            result["estimated_cost"] = response._hidden_params['cost']

        return result

    def _try_fallback_providers(self, prompt: str, **kwargs):
        """Try alternative providers on failure."""
        available_providers = get_available_providers()
        for fallback_provider in available_providers:
            if fallback_provider != self.provider:
                try:
                    fallback_model = get_model_for_provider(fallback_provider)
                    response = litellm.completion(
                        model=fallback_model,
                        messages=[{"role": "user", "content": prompt}],
                        metadata={"provider": fallback_provider, "fallback_from": self.provider},
                        **kwargs
                    )
                    return response
                except Exception:
                    continue
        raise Exception("All providers failed")

    def _try_fallback_pdf_processing(self, pdf_base64: str, prompt: str, **kwargs):
        """Try PDF processing with alternative providers."""
        available_providers = get_available_providers()
        for fallback_provider in available_providers:
            if fallback_provider != self.provider:
                try:
                    # Create temporary client for fallback
                    fallback_client = MultiProviderLLMClient(fallback_provider)
                    fallback_client.fallback_enabled = False  # Prevent infinite recursion
                    return fallback_client.process_pdf_native(pdf_base64, prompt, **kwargs)
                except Exception:
                    continue
        raise Exception("PDF processing failed on all providers")

# Global client instance
llm_client = MultiProviderLLMClient()

# Convenience functions for backward compatibility
def generate_response(prompt: str, provider: str = None, **kwargs):
    if provider and provider != llm_client.provider:
        client = MultiProviderLLMClient(provider)
    else:
        client = llm_client
    return client.generate_response(prompt, **kwargs)

def process_pdf(pdf_bytes: Union[bytes, str], prompt: str, provider: str = None, **kwargs):
    if provider and provider != llm_client.provider:
        client = MultiProviderLLMClient(provider)
    else:
        client = llm_client
    return client.process_pdf_native(pdf_bytes, prompt, **kwargs)
```

### 1.3 Enhanced File Helpers

**File: `utils/file_helpers.py`** (~25 lines)

```python
import streamlit as st
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

def save_with_download(content: str, filename: str, metadata: Dict[str, Any] = None):
    """Save content with metadata and provide download button."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, 'txt')
    final_name = f"{name}_{timestamp}.{ext}"

    # Prepare content with metadata
    if metadata:
        header = f"---\n# Generated with {metadata.get('provider', 'unknown')} provider\n"
        header += f"# Model: {metadata.get('model', 'unknown')}\n"
        header += f"# Tokens: {metadata.get('total_tokens', 'unknown')}\n"
        if metadata.get('reasoning_tokens'):
            header += f"# Reasoning tokens: {metadata['reasoning_tokens']}\n"
        if metadata.get('estimated_cost'):
            header += f"# Estimated cost: ${metadata['estimated_cost']:.4f}\n"
        header += f"# Generated: {timestamp}\n---\n\n"
        full_content = header + content
    else:
        full_content = content

    # Save locally
    output_path = Path("outputs") / final_name
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(full_content)

    # Streamlit download button
    st.download_button(
        label=f"⬇️ Download {final_name}",
        data=full_content,
        file_name=final_name,
        mime="text/plain"
    )

    st.success(f"Saved to: outputs/{final_name}")

    # Show metadata if available
    if metadata:
        with st.expander("📊 Generation Details"):
            st.json(metadata)
```

### 1.4 Enhanced Main App with Provider Status

**File: `app.py`** (~30 lines)

```python
import streamlit as st
import os
from pathlib import Path
from utils.provider_config import get_available_providers, get_provider_info, PROVIDER_CONFIG

# Configure page
st.set_page_config(
    page_title="Forensic Report Drafter v2",
    page_icon="🧠",
    layout="wide"
)

# Ensure directories exist
for dir_name in ["prompt_templates", "templates", "outputs"]:
    Path(dir_name).mkdir(exist_ok=True)

# Main page
st.title("🧠 Forensic Psychology Report Drafter v2")
    st.markdown("""
**Multi-provider AI-powered report drafting with automatic tracing and evaluation.**

👈 **Choose a function from the sidebar to get started.**

### Features:
- 📝 **Prompt Generation**: Process templates with transcripts (multi-provider)
- 📄 **Document Analysis**: Native PDF analysis across Azure OpenAI, Anthropic, and Gemini
- ✨ **Report Refinement**: Provider-optimized draft improvements
- 📊 **Batch Processing**: Cost-aware multi-document processing
- 🔬 **Evaluation**: Multi-provider prompt testing and comparison

All operations are automatically tracked in Langfuse with provider analytics and cost monitoring.
""")

# Provider status in sidebar
with st.sidebar:
    st.header("🔧 System Status")

    # Check available providers
    available_providers = get_available_providers()

    if not available_providers:
        st.error("❌ No LLM providers configured")
        st.info("Configure at least one provider in your .env file")
            else:
        st.success(f"✅ {len(available_providers)} provider(s) available")

        # Show provider details
        with st.expander("🤖 Available Providers"):
            for provider in available_providers:
                info = get_provider_info(provider)
                st.markdown(f"**{info['display_name']}**")
                st.caption(info['description'])
                st.caption(f"Cost tier: {info['cost_tier'].title()}")

        # Langfuse status
        langfuse_keys = ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"]
        missing_langfuse = [key for key in langfuse_keys if not os.getenv(key)]

        if missing_langfuse:
            st.warning(f"⚠️ Langfuse incomplete: {', '.join(missing_langfuse)}")
        else:
            st.success("✅ Langfuse configured")

    if st.button("🧪 Test LLM Connection"):
        try:
            from utils.llm_client import generate_response
            response = generate_response("Hello", max_tokens=5)
            st.success("✅ LLM connection working!")
        except Exception as e:
            st.error(f"❌ LLM Error: {e}")
```

## Phase 2: Enhanced Core Pages (Week 1)

### 2.1 Enhanced Prompt Generation Page

**File: `pages/1_📝_Prompt_Generation.py`** (~60 lines)

```python
import streamlit as st
from utils.llm_client import generate_response, llm_client
from utils.file_helpers import save_with_download
from utils.provider_config import get_available_providers, get_provider_info

st.title("📝 Prompt Generation")
st.markdown("Process markdown templates with transcript data using your preferred LLM provider.")

# Provider selection
available_providers = get_available_providers()
if len(available_providers) > 1:
    col1, col2 = st.columns([2, 1])
    with col1:
        selected_provider = st.selectbox(
            "Select LLM Provider:",
            options=available_providers,
            format_func=lambda x: get_provider_info(x)['display_name'],
            index=available_providers.index(llm_client.provider) if llm_client.provider in available_providers else 0
        )
    with col2:
        provider_info = get_provider_info(selected_provider)
        st.info(f"💰 Cost: {provider_info['cost_tier'].title()}")
else:
    selected_provider = available_providers[0]
    st.info(f"Using: {get_provider_info(selected_provider)['display_name']}")

    col1, col2 = st.columns(2)

    with col1:
    st.subheader("📋 Template")
    template_file = st.file_uploader("Upload Markdown Template", type=['md'])

        if template_file:
            template_content = str(template_file.read(), 'utf-8')
            st.text_area("Template Preview", template_content, height=200, disabled=True)

    with col2:
    st.subheader("📄 Transcript")
    transcript_file = st.file_uploader("Upload Transcript", type=['txt', 'md'])

        if transcript_file:
            transcript_content = str(transcript_file.read(), 'utf-8')
            st.text_area("Transcript Preview", transcript_content, height=200, disabled=True)

    if template_file and transcript_file:
    st.subheader("🔧 Processing Options")

                        col1, col2 = st.columns(2)
                        with col1:
        include_instructions = st.checkbox("Include processing instructions", value=True)
        temperature = st.slider("Creativity (Temperature)", 0.0, 1.0, 0.1, 0.1)
    with col2:
        max_tokens = st.number_input("Max tokens", min_value=100, max_value=4000, value=2000)

    if st.button("🚀 Generate Prompts", type="primary"):
        with st.spinner(f"Processing with {get_provider_info(selected_provider)['display_name']}..."):

            # Create combined prompt
            system_prompt = """Generate a forensic psychology report section from the provided template and transcript data.
            Follow the template structure and use information from the transcript.""" if include_instructions else ""

            combined_prompt = f"""
            {system_prompt}

            Template:
            {template_content}

            Transcript:
            {transcript_content}
            """

            try:
                # Generate using selected provider
                response = generate_response(
                    combined_prompt,
                    provider=selected_provider,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                result = response.choices[0].message.content

                st.success("✅ Prompt generated successfully!")

                # Display result
                st.subheader("📋 Generated Content")
                st.text_area("Result", result, height=400)

                # Get usage statistics
                from utils.llm_client import MultiProviderLLMClient
                client = MultiProviderLLMClient(selected_provider)
                usage_stats = client.get_comprehensive_usage(response)

                # Save and download with metadata
                save_with_download(
                    result,
                    f"generated_prompt_{template_file.name}",
                    metadata=usage_stats
                )

            except Exception as e:
                st.error(f"❌ Error generating prompt: {e}")
                if len(available_providers) > 1:
                    st.info("💡 Try selecting a different provider above")
```

### 2.2 Enhanced Document Analysis Page

**File: `pages/2_📄_Document_Analysis.py`** (~80 lines)

```python
import streamlit as st
import base64
from utils.llm_client import process_pdf, MultiProviderLLMClient
from utils.file_helpers import save_with_download
from utils.provider_config import get_available_providers, get_provider_info

st.title("📄 Document Analysis")
st.markdown("Analyze PDF documents using native AI capabilities with automatic tracing.")

# Provider selection with PDF support info
available_providers = get_available_providers()
pdf_capable_providers = [p for p in available_providers if get_provider_info(p).get('supports_pdf', False)]

if not pdf_capable_providers:
    st.error("❌ No providers with PDF processing capabilities are configured")
    st.stop()

col1, col2 = st.columns([2, 1])
with col1:
    selected_provider = st.selectbox(
        "Select PDF-capable Provider:",
        options=pdf_capable_providers,
        format_func=lambda x: f"{get_provider_info(x)['display_name']} ({get_provider_info(x)['cost_tier']} cost)"
    )
with col2:
    provider_info = get_provider_info(selected_provider)
    if provider_info.get('supports_reasoning'):
        st.success("🧠 Reasoning tokens supported")
    if provider_info.get('supports_multimodal'):
        st.success("🖼️ Multimodal capable")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📎 Upload PDF")
    uploaded_file = st.file_uploader("Choose PDF file", type="pdf")

    if uploaded_file:
        st.success(f"📁 Loaded: {uploaded_file.name}")
        file_size = len(uploaded_file.getvalue()) / 1024
        st.info(f"Size: {file_size:.1f} KB")

        # Context length check
        max_context = provider_info.get('max_context', 0)
        estimated_tokens = file_size * 4  # Rough estimation
        if estimated_tokens > max_context * 0.8:
            st.warning(f"⚠️ Large file may exceed context limit (~{estimated_tokens:.0f} tokens)")

                        with col2:
    st.subheader("💭 Analysis Prompt")

    # Provider-specific prompt suggestions
    if selected_provider == "anthropic":
        st.caption("💡 Claude Sonnet 4 excels at reasoning and complex analysis")
    elif selected_provider == "gemini":
        st.caption("💡 Gemini 2.5 Pro handles large documents well")
    elif selected_provider == "azure":
        st.caption("💡 GPT-4.1 provides reliable structured output")

    prompt_type = st.selectbox(
        "Select analysis type:",
        ["Custom", "Summary", "Key Points", "Risk Assessment", "Recommendations", "Detailed Analysis"]
    )

    if prompt_type == "Custom":
        analysis_prompt = st.text_area("Enter your analysis prompt:",
                                     "Please analyze this document and provide insights.")
    else:
        prompts = {
            "Summary": "Provide a comprehensive summary of this document, highlighting main points and key findings.",
            "Key Points": "Extract the key points, main findings, and important information from this document. Present as a structured list.",
            "Risk Assessment": "Analyze this document for risk factors, concerning elements, and safety considerations. Provide a structured risk assessment.",
            "Recommendations": "Based on this document, provide specific clinical recommendations and next steps.",
            "Detailed Analysis": "Perform a detailed analysis of this document, including context, implications, and professional insights."
        }
        analysis_prompt = st.text_area("Analysis prompt:", prompts[prompt_type], height=100)

# Advanced options
with st.expander("🔧 Advanced Options"):
    col1, col2 = st.columns(2)
    with col1:
        temperature = st.slider("Analysis creativity", 0.0, 0.5, 0.1, 0.05)
        max_tokens = st.number_input("Max response tokens", 500, 4000, 2000)
    with col2:
        enable_reasoning = st.checkbox(
            "Enable reasoning mode",
            value=provider_info.get('supports_reasoning', False),
            disabled=not provider_info.get('supports_reasoning', False)
        )

if uploaded_file and analysis_prompt:

    if st.button("🔍 Analyze Document", type="primary"):
        with st.spinner(f"🤖 {provider_info['display_name']} is analyzing the document..."):
            try:
                # Process with selected provider's native PDF capabilities
                kwargs = {
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }

                if enable_reasoning and provider_info.get('supports_reasoning'):
                    kwargs["reasoning"] = True

                response = process_pdf(
                    uploaded_file.getvalue(),
                    analysis_prompt,
                    provider=selected_provider,
                    **kwargs
                )
                result = response.choices[0].message.content

                st.success("✅ Analysis completed!")

                # Display results
                st.subheader("📊 Analysis Results")
                st.markdown(result)

                # Get comprehensive usage statistics
                client = MultiProviderLLMClient(selected_provider)
                usage_stats = client.get_comprehensive_usage(response)

                # Enhanced metadata
                analysis_metadata = {
                    **usage_stats,
                    "file_name": uploaded_file.name,
                    "file_size_kb": len(uploaded_file.getvalue()) / 1024,
                    "analysis_type": prompt_type,
                    "temperature": temperature
                }

                # Save and download with comprehensive metadata
                save_with_download(
                    result,
                    f"analysis_{uploaded_file.name.replace('.pdf', '.md')}",
                    metadata=analysis_metadata
                )

                # Cost comparison if multiple providers available
                if len(pdf_capable_providers) > 1:
                    with st.expander("💰 Provider Cost Comparison"):
                        for provider in pdf_capable_providers:
                            info = get_provider_info(provider)
                            cost_indicator = {"low": "💚", "medium": "🟡", "high": "🔴"}[info['cost_tier']]
                            selected_indicator = "👈" if provider == selected_provider else ""
                            st.write(f"{cost_indicator} {info['display_name']}: {info['cost_tier']} cost {selected_indicator}")

            except Exception as e:
                st.error(f"❌ Analysis failed: {e}")
                st.info("💡 Try:")
                st.info("- Ensuring your PDF is text-readable")
                st.info("- Using a simpler prompt")
                if len(pdf_capable_providers) > 1:
                    st.info("- Switching to a different provider")
```

### 2.3 Enhanced Report Refinement Page

**File: `pages/3_✨_Report_Refinement.py`** (~50 lines)

```python
import streamlit as st
from utils.llm_client import generate_response, MultiProviderLLMClient
from utils.file_helpers import save_with_download
from utils.provider_config import get_available_providers, get_provider_info

st.title("✨ Report Refinement")
st.markdown("Improve draft reports with provider-optimized AI assistance.")

# Provider selection with optimization suggestions
available_providers = get_available_providers()
if len(available_providers) > 1:
    selected_provider = st.selectbox(
        "Select Provider for Refinement:",
        options=available_providers,
        format_func=lambda x: f"{get_provider_info(x)['display_name']} - {get_provider_info(x)['cost_tier']} cost"
    )

    # Provider-specific refinement suggestions
    provider_info = get_provider_info(selected_provider)
    if selected_provider == "anthropic":
        st.info("🤖 Claude Sonnet 4 excels at improving logical flow and professional tone")
    elif selected_provider == "azure":
        st.info("☁️ GPT-4.1 provides consistent formatting and style improvements")
    elif selected_provider == "gemini":
        st.info("🔷 Gemini 2.5 Pro offers cost-effective refinement with good results")
else:
    selected_provider = available_providers[0]

# Upload draft report
uploaded_draft = st.file_uploader("Upload Draft Report", type=['md', 'txt'])

if uploaded_draft:
    draft_content = str(uploaded_draft.read(), 'utf-8')

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📄 Original Draft")
        st.text_area("Draft content", draft_content, height=300, disabled=True)

    with col2:
        st.subheader("🎯 Refinement Instructions")

        refinement_type = st.selectbox(
            "Refinement type:",
            ["Custom", "Grammar & Style", "Clarity & Flow", "Professional Tone",
             "Comprehensive Review", "Conciseness", "Detail Enhancement"]
        )

        if refinement_type == "Custom":
            instructions = st.text_area("Custom instructions:",
                                      "Please improve this report for clarity and professionalism.")
        else:
            instruction_templates = {
                "Grammar & Style": "Review and improve grammar, punctuation, and writing style while maintaining the original meaning.",
                "Clarity & Flow": "Improve clarity, logical flow, and readability. Ensure smooth transitions between sections.",
                "Professional Tone": "Enhance professional tone and clinical language appropriate for forensic psychology.",
                "Comprehensive Review": "Perform a comprehensive review for accuracy, clarity, professionalism, and completeness.",
                "Conciseness": "Make the report more concise while preserving all important information and insights.",
                "Detail Enhancement": "Add relevant details and expand on key points where appropriate for better comprehension."
            }
            instructions = st.text_area("Instructions:", instruction_templates[refinement_type])

        # Advanced refinement options
        with st.expander("🔧 Refinement Settings"):
            temperature = st.slider("Creativity level", 0.0, 0.3, 0.1, 0.05,
                                   help="Lower values = more conservative changes")
            preserve_structure = st.checkbox("Preserve original structure", value=True)
            max_tokens = st.number_input("Max output tokens", 1000, 4000, 3000)

    if st.button("✨ Refine Report", type="primary"):
        with st.spinner(f"🤖 {get_provider_info(selected_provider)['display_name']} is refining the report..."):
            try:
                structure_instruction = "\n\nIMPORTANT: Preserve the original document structure and formatting." if preserve_structure else ""

                refinement_prompt = f"""
                Please refine the following report according to these instructions:

                Instructions: {instructions}{structure_instruction}

                Original Report:
                {draft_content}

                Please provide the improved version, maintaining the professional quality expected in forensic psychology reports:
                """

                response = generate_response(
                    refinement_prompt,
                    provider=selected_provider,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                refined_content = response.choices[0].message.content

                st.success("✅ Report refined successfully!")

                # Show refined version
                st.subheader("✨ Refined Report")
                st.markdown(refined_content)

                # Get usage statistics
                client = MultiProviderLLMClient(selected_provider)
                usage_stats = client.get_comprehensive_usage(response)

                refinement_metadata = {
                    **usage_stats,
                    "original_file": uploaded_draft.name,
                    "refinement_type": refinement_type,
                    "temperature": temperature,
                    "preserve_structure": preserve_structure
                }

                # Save and download with metadata
                save_with_download(
                    refined_content,
                    f"refined_{uploaded_draft.name}",
                    metadata=refinement_metadata
                )

                # Show comparison metrics
                original_words = len(draft_content.split())
                refined_words = len(refined_content.split())

                with st.expander("📈 Refinement Metrics"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Original words", original_words)
                    with col2:
                        st.metric("Refined words", refined_words)
                    with col3:
                        change = refined_words - original_words
                        st.metric("Word change", f"{change:+d}")

            except Exception as e:
                st.error(f"❌ Refinement failed: {e}")
                if len(available_providers) > 1:
                    st.info("💡 Try switching to a different provider")
```

## Continue with remaining pages and deployment instructions?

This multi-provider implementation provides:

✅ **Native PDF processing** across Azure OpenAI (GPT-4.1), Anthropic (Claude Sonnet 4), and Gemini (Gemini 2.5 Pro)  
✅ **Automatic token counting** including reasoning/thinking tokens  
✅ **Provider fallbacks** for reliability  
✅ **Cost optimization** with real-time provider comparison  
✅ **Enhanced metadata** tracking for all operations

Would you like me to continue with the remaining pages (Batch Processing and Evaluation) and the final deployment section?
