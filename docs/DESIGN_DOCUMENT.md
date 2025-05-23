# Design Document: Forensic Psych Report Drafter v2 (Rewrite)

## 1. Project Overview

This document outlines the design for the rewritten Forensic Psych Report Drafter application. The primary goal is to create a streamlined, robust, and maintainable tool for forensic psychiatrists to analyze documents and generate reports. This rewrite emphasizes leveraging native integrations between core technologies to minimize custom code and maximize functionality.

**Core Purpose**: To assist forensic psychology professionals by automating and enhancing the drafting of reports through LLM-powered document analysis, prompt generation, and report refinement.

**Key Technologies**:

- **UI Framework**: Streamlit (with auto-page discovery)
- **LLM Orchestration**: LiteLLM (with built-in Langfuse integration and multi-provider support, including LiteLLM Router for fallbacks and routing strategies, instantiated via `st.cache_resource`). Utilizes LiteLLM for token counting and cost estimation.
- **Supported LLM Providers**:
  - Azure OpenAI (e.g., GPT-4.1, GPT-4o-mini)
  - Anthropic (e.g., Claude 3 Sonnet, Claude 3 Opus)
  - Google Gemini (e.g., Gemini 2.5 Pro, Gemini 1.5 Flash)
- **Observability & Prompt Management**: Langfuse.
  - **Observability**: Integrated via LiteLLM for tracing LLM calls.
  - **Prompt Management**: Used as a Prompt Content Management System (CMS) for creating, editing, versioning, and deploying prompts via its UI and SDK. Prompts are fetched dynamically by the application. ([Langfuse Docs - Prompt Management](https://langfuse.com/docs/prompts/get-started))
- **Evaluation Framework**: Promptfoo (with native `langfuse://` prompt references and Langfuse Dataset integration)
- **Dependency Management**: uv
- **PDF Handling**: PyMuPDF (for pre-checks and metadata extraction)

## 2. Core Architecture

### 2.1. Simplified Directory Structure

```
forensic-report-drafter-v2/
├── app.py                          # Main Streamlit application (homepage & provider status, session cost display)
├── pyproject.toml                  # Project dependencies (managed by uv)
├── .env                            # Environment variables for API keys and config
├── README.md                       # Setup and usage instructions
├── pages/                          # Streamlit auto-discovered pages
│   ├── 1_📝_Prompt_Generation.py
│   ├── 2_📄_Document_Analysis.py
│   ├── 3_✨_Report_Refinement.py
│   ├── 4_📊_Batch_Processing.py
│   └── 5_🔬_Evaluation.py
├── utils/                          # Shared utilities
│   ├── __init__.py
│   ├── provider_config.py          # Provider configurations, models, capabilities, pricing
│   ├── llm_client.py               # LiteLLM wrapper (using cached Router & Client), cost estimation
│   └── file_helpers.py             # Streamlit file operations (saving, downloads)
├── prompt_templates/               # Local prompt backup/fallback (.md files) for Langfuse prompts
├── templates/                      # Local report templates (.md files)
├── outputs/                        # Generated files (reports, analyses)
└── docs/                           # Documentation
    ├── IMPLEMENTATION_GUIDE.md     # Original implementation guide
    ├── REWRITE_SPECIFICATION.md    # Specification for this rewrite
    └── DESIGN_DOCUMENT.md          # This document
```

### 2.2. Technology Stack & Key Integrations

- **Streamlit**: Used for all UI components, file uploads/downloads, page routing, and state management. Includes `st.data_editor` for configuration viewing and `st.session_state` for session cost tracking. Manages caching of global resources like the LLM router and client via `st.cache_resource`. Users will interact with UI elements to provide values for dynamic prompt templates.
- **LiteLLM**:
  - Handles communication with all LLM providers via `litellm.Router`.
  - Automatic Langfuse integration for tracing.
  - Native PDF document processing.
  - Relies on native cost tracking (`response.cost`) and `litellm.token_counter`.
  - Uses `litellm.acompletion` via the router.
- **Langfuse**:
  - **Observability**: Receives all LLM call traces automatically from LiteLLM.
  - **Prompt Management**:
    - Serves as the central Prompt CMS. All prompts are created, edited, versioned, and managed (e.g., using labels like "production", "staging") within the Langfuse UI.
    - The application fetches prompts using the Langfuse SDK (e.g., `langfuse.get_prompt("prompt_name", label="production")`).
    - Prompts are designed as templates (e.g., `Analyze {{document_type}} for {{specific_focus}}`).
    - The Langfuse SDK's `prompt.compile(**variables)` method will be used to inject dynamic values provided by the user through the Streamlit UI into these templates before sending to the LLM.
    - The `config` field within a Langfuse prompt object can store associated metadata (e.g., default model parameters, version notes).
    - Local prompts in `prompt_templates/` can serve as fallbacks if specified in the `langfuse.get_prompt(..., fallback="...")` call, ensuring availability.
- **Promptfoo**:
  - Used for LLM output evaluation.
  - Integrates with Langfuse for referencing prompts (e.g., `langfuse://<prompt-name>`) and datasets. This ensures evaluations use the same centrally managed prompts.
  - Called as a subprocess from the Streamlit application.
- **PyMuPDF**: Used for pre-processing and validation of PDF files.
- **uv**: For Python package management.

(Other sections like Environment Config, Dependency Management remain largely the same)

## 3. Key Modules & Functionality

### 3.1. `app.py` (Main Homepage & Provider Status)

- Sets Streamlit page configuration.
- Ensures necessary directories (`outputs`, `templates`, `prompt_templates`) exist.
- Displays a welcome message and overview of application features.
- Sidebar:
  - System status: Checks and displays available LLM providers based on `.env` configuration and `utils/provider_config.py`.
  - Langfuse connection status.
  - Link to documentation.
  - A "Test LLM Connection" button.
  - **Session Cost Tracking**: Displays `Total Estimated Session Cost: $ {st.session_state.get("total_session_cost", 0.0):.4f}`. Initialize `if "total_session_cost" not in st.session_state: st.session_state.total_session_cost = 0.0`.
  - **Admin Feature**: An expander titled "⚙️ Admin: View Provider Configuration" which, when activated, uses `st.data_editor` to display the contents of `PROVIDER_CONFIG` from `utils.provider_config` in the main area or a modal for review.

### 3.2. `utils/provider_config.py`

This file centralizes definitions, including model pricing for pre-call cost estimation.

```python
from typing import Dict, List, Any
import os

# Centralized provider configuration
PROVIDER_CONFIG = {
    "azure": {
        "display_name": "☁️ Azure OpenAI",
        "description": "Enterprise-grade deployment with PDF processing.",
        "models": {
            "gpt-4o": {
                "litellm_name": "azure/gpt-4o", # Actual name LiteLLM uses for the API call
                "input_cost_per_token": 0.000005, # Example: $5.00 / 1M tokens
                "output_cost_per_token": 0.000015, # Example: $15.00 / 1M tokens
                "max_tokens": 128000
            },
            "gpt-4o-mini": {
                "litellm_name": "azure/gpt-4o-mini",
                "input_cost_per_token": 0.00000015, # Example: $0.15 / 1M tokens
                "output_cost_per_token": 0.0000006,  # Example: $0.60 / 1M tokens
                "max_tokens": 128000
            }
            # Add other Azure models similarly
        },
        "default_model_alias": "gpt-4o", # Alias used in UI and for router
        "features": ["pdf_processing", "function_calling", "token_counting", "enterprise_security"],
        "cost_tier": "medium",
        "supports_pdf": True
    },
    "anthropic": {
        "display_name": "🤖 Anthropic Claude",
        "description": "Advanced reasoning with native PDF processing and thinking tokens.",
        "models": {
            "claude-3-opus-20240229": {
                "litellm_name": "anthropic/claude-3-opus-20240229",
                "input_cost_per_token": 0.000015,  # Example: $15 / 1M tokens
                "output_cost_per_token": 0.000075, # Example: $75 / 1M tokens
                "max_tokens": 200000
            },
            "claude-3-sonnet-20240229": {
                "litellm_name": "anthropic/claude-3-sonnet-20240229",
                "input_cost_per_token": 0.000003,   # Example: $3 / 1M tokens
                "output_cost_per_token": 0.000015,  # Example: $15 / 1M tokens
                "max_tokens": 200000
            }
        },
        "default_model_alias": "claude-3-sonnet-20240229",
        "features": ["pdf_processing", "thinking_tokens", "function_calling", "long_context"],
        "cost_tier": "high",
        "supports_pdf": True,
        "supports_reasoning_tokens": True
    },
    "gemini": {
        "display_name": "🔷 Google Gemini",
        "description": "Multimodal capabilities with document understanding.",
        "models": {
            "gemini-1.5-pro-latest": {
                "litellm_name": "gemini/gemini-1.5-pro-latest",
                "input_cost_per_token": 0.0000035,  # Example: $3.50 / 1M tokens (adjust based on actuals)
                "output_cost_per_token": 0.0000105, # Example: $10.50 / 1M tokens
                "max_tokens": 1000000
            },
            "gemini-1.5-flash-latest": {
                "litellm_name": "gemini/gemini-1.5-flash-latest",
                "input_cost_per_token": 0.00000035, # Example: $0.35 / 1M tokens
                "output_cost_per_token": 0.00000105,# Example: $1.05 / 1M tokens
                "max_tokens": 1000000
            }
        },
        "default_model_alias": "gemini-1.5-pro-latest",
        "features": ["multimodal", "pdf_processing", "long_context", "cost_effective"],
        "cost_tier": "low",
        "supports_pdf": True,
        "supports_multimodal": True
    }
}

def get_available_providers() -> List[str]:
    # ... (implementation based on os.getenv checks for relevant API keys)
    available = []
    if os.getenv("AZURE_API_KEY") and os.getenv("AZURE_API_BASE"):
        available.append("azure")
    if os.getenv("ANTHROPIC_API_KEY"):
        available.append("anthropic")
    if os.getenv("GOOGLE_API_KEY"):
        available.append("gemini")
    return available

def get_provider_info(provider_key: str) -> Dict[str, Any]:
    return PROVIDER_CONFIG.get(provider_key, {})

def get_model_aliases_for_provider(provider_key: str) -> List[str]:
    """Returns a list of model aliases (UI friendly names) for a given provider."""
    provider_conf = PROVIDER_CONFIG.get(provider_key, {})
    return list(provider_conf.get("models", {}).keys())

def get_model_details(provider_key: str, model_alias: str) -> Dict[str, Any]:
    """Returns specific details (litellm_name, pricing, max_tokens) for a model alias."""
    provider_conf = PROVIDER_CONFIG.get(provider_key, {})
    return provider_conf.get("models", {}).get(model_alias, {})

def get_default_model_alias_for_provider(provider_key: str) -> str:
    provider_conf = PROVIDER_CONFIG.get(provider_key, {})
    return provider_conf.get("default_model_alias", "")

def get_llm_model_name(provider_key: str, model_alias: str) -> str:
    """Gets the full LiteLLM model name string from provider and alias."""
    model_details = get_model_details(provider_key, model_alias)
    return model_details.get("litellm_name", f"{provider_key}/{model_alias}") # Fallback slightly modified

def get_router_model_list() -> List[Dict[str, Any]]:
    router_model_list = []
    for provider_key, config in PROVIDER_CONFIG.items():
        for model_alias, model_data in config.get("models", {}).items():
            model_info = {
                "model_name": model_alias, # Alias used by router
                "litellm_params": {
                    "model": model_data["litellm_name"] # Actual LiteLLM model string
                    # API keys are expected to be set as environment variables
                }
                # Add other router-specific params like tpm, rpm if needed from model_data
            }
            router_model_list.append(model_info)
    return router_model_list
```

### 3.3. `utils/llm_client.py`

Includes pre-call cost estimation logic.

```python
import streamlit as st
import litellm
import os
import base64
from typing import Optional, Dict, Any, Union, List, Tuple
from dotenv import load_dotenv
from .provider_config import get_model_details # Adjusted imports

load_dotenv()

if "langfuse" not in litellm.success_callback:
    litellm.success_callback.append("langfuse")
if "langfuse" not in litellm.failure_callback:
    litellm.failure_callback.append("langfuse")

@st.cache_resource
def get_llm_router(): # Definition as before
    from .provider_config import get_router_model_list # Delayed import for st.cache_resource context
    router_model_list = get_router_model_list()
    print("Initializing LiteLLM Router...")
    return litellm.Router(
        model_list=router_model_list,
        routing_strategy="simple-shuffle"
    )

class LLMClient:
    def __init__(self, router: litellm.Router):
        self.router = router

    async def generate_response(self, model_alias: str, messages: List[Dict[str,str]], **kwargs) -> Any:
        # messages are now passed directly
        metadata = kwargs.pop("metadata", {})
        metadata.update({"requested_model_alias": model_alias})
        response = await self.router.acompletion(model=model_alias, messages=messages, metadata=metadata, **kwargs)
        return response

    async def process_pdf_native(self, model_alias: str, pdf_bytes: Union[bytes, str], prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Any:
        # ... (logic for PDF payload construction remains complex and provider-specific)
        # This method needs the actual provider to construct user_content for PDF
        # It would need to look up provider_key from model_alias via PROVIDER_CONFIG
        # For simplicity, this detail is omitted here but crucial for implementation.
        # Example: provider_key = find_provider_for_alias(model_alias) from provider_config
        # Then, actual_model_string = get_model_details(provider_key, model_alias).get("litellm_name")
        # And current_provider = actual_model_string.split('/')[0]

        # Placeholder for the complex PDF logic from previous versions
        if isinstance(pdf_bytes, bytes):
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        else:
            pdf_base64 = pdf_bytes

        # This section needs proper provider derivation from model_alias to build messages correctly
        # For now, assuming a generic structure and it needs refinement.
        messages = []
        if system_prompt: messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": [{"type":"text", "text":prompt}, {"type":"document_placeholder", "data": pdf_base64}]}) # Needs provider specific formatting

        metadata = kwargs.pop("metadata", {})
        metadata.update({"requested_model_alias": model_alias, "content_type": "pdf"})
        response = await self.router.acompletion(model=model_alias, messages=messages, metadata=metadata, **kwargs)
        return response

    def get_comprehensive_usage(self, response) -> Dict[str, Any]:
        # ... (implementation remains the same)
        cost = None
        if hasattr(response, 'cost') and response.cost is not None:
            cost = response.cost
        # ... rest of the logic ...
        usage_data = response.usage
        model_used = response.model
        provider_used = model_used.split('/')[0] if '/' in model_used else "unknown"
        result = {
            "prompt_tokens": getattr(usage_data, 'prompt_tokens', 0),
            "completion_tokens": getattr(usage_data, 'completion_tokens', 0),
            "total_tokens": getattr(usage_data, 'total_tokens', 0),
            "provider": provider_used,
            "model": model_used
        }
        if cost is not None:
            result["estimated_cost_usd"] = cost
        if hasattr(usage_data, 'reasoning_tokens'):
            result["reasoning_tokens"] = usage_data.reasoning_tokens
        elif hasattr(response, '_hidden_params') and 'reasoning_tokens' in response._hidden_params:
             result["reasoning_tokens"] = response._hidden_params['reasoning_tokens']
        return result

@st.cache_resource
def get_llm_client():
    print("Initializing LLMClient...")
    router_instance = get_llm_router()
    return LLMClient(router=router_instance)

def estimate_cost_before_call(
    provider_key: str,
    model_alias: str,
    messages: List[Dict[str, str]],
    max_completion_tokens_estimate: int = 1000 # Default estimate
) -> Optional[float]:
    """Estimates cost using litellm.token_counter and pricing from PROVIDER_CONFIG."""
    from .provider_config import PROVIDER_CONFIG # Delayed import

    model_config = PROVIDER_CONFIG.get(provider_key, {}).get("models", {}).get(model_alias)
    if not model_config or "input_cost_per_token" not in model_config or "output_cost_per_token" not in model_config:
        # Fallback or warning if pricing is not in our config
        # st.warning(f"Pricing for {model_alias} not defined in config. Cannot estimate cost precisely.")
        # Optionally, try litellm.cost_per_token if we want to hit their API as a fallback
        try:
            # This requires the full litellm model name, not alias
            litellm_model_name = model_config.get("litellm_name") if model_config else model_alias
            prompt_tokens_cost, completion_tokens_cost = litellm.cost_per_token(
                model=litellm_model_name,
                prompt_tokens=1, # Dummy values, we only need per-token cost
                completion_tokens=1
            )
            # This gives cost for 1 token. So, these are effectively per-token costs.
            input_cost = prompt_tokens_cost
            output_cost = completion_tokens_cost
        except Exception:
            return None # Cannot determine cost
    else:
        input_cost = model_config["input_cost_per_token"]
        output_cost = model_config["output_cost_per_token"]

    try:
        # Need full model name for token_counter if not using an alias LiteLLM recognizes for token counting
        litellm_model_name_for_count = model_config.get("litellm_name") if model_config else model_alias
        prompt_tokens = litellm.token_counter(model=litellm_model_name_for_count, messages=messages)

        estimated_total_cost = (prompt_tokens * input_cost) + (max_completion_tokens_estimate * output_cost)
        return estimated_total_cost
    except Exception as e:
        # st.error(f"Error estimating cost: {e}")
        return None

```

### 3.4. `utils/file_helpers.py`

(No changes from previous version for this section)

### 3.5. `pages/` (Streamlit Pages)

General approach for pages involving LLM interaction:

1. Obtain `llm_client = get_llm_client()`.
2. Fetch the required prompt template from Langfuse using `langfuse_client.get_prompt("my_prompt_name", label="production", fallback=local_fallback_string_if_any)`.
3. Use Streamlit UI elements (e.g., `st.text_input`, `st.selectbox`) to gather necessary variables for the prompt template.
4. Compile the prompt: `compiled_prompt_content = langfuse_prompt.compile(var1=st.session_state.var1_val, ...)`.
5. Construct the `messages` list for the `LLMClient` using the `compiled_prompt_content`.
6. Call the appropriate `llm_client` method (e.g., `await llm_client.generate_response(...)`).
7. Handle pre-call cost estimation and update total session cost as previously described.

#### 3.5.1. `1_📝_Prompt_Generation.py`

- UI:
  - Provider and model alias selection.
  - Inputs for variables required by the selected Langfuse prompt template for prompt generation tasks.
  - `max_tokens` input.
  - Display area for pre-call estimated cost.
- Logic:
  - Fetches a specific "prompt generation" template from Langfuse.
  - User provides inputs which are compiled into the fetched template.
  - On generate: `response = await llm_client.generate_response(...)` using the compiled prompt.
  - Update session cost.

#### 3.5.2. `2_📄_Document_Analysis.py`

- UI:
  - PDF uploader, provider and model alias selection.
  - Inputs for variables required by the selected Langfuse document analysis prompt template (e.g., "type of analysis", "specific questions to answer").
  - `max_tokens` input.
  - Display area for pre-call estimated cost.
- Logic:
  - Fetches the relevant "document analysis" prompt template from Langfuse.
  - User provides inputs for the template.
  - On analyze: `response = await llm_client.process_pdf_native(...)` using the compiled prompt.
  - Update session cost.

#### 3.5.3. `3_✨_Report_Refinement.py`

- UI:
  - Text area for initial report/text, provider and model alias selection.
  - Inputs for variables required by the Langfuse report refinement prompt template (e.g., "refinement goals", "target audience").
  - `max_tokens` input.
  - Display area for pre-call estimated cost.
- Logic:
  - Fetches the "report refinement" prompt template from Langfuse.
  - User provides inputs for the template.
  - On refine: `response = await llm_client.generate_response(...)` using the compiled prompt.
  - Update session cost.

#### 3.5.4. `4_📊_Batch_Processing.py`

- Similar to individual processing pages, but will fetch and compile prompts for each item in the batch. This ensures consistency with centrally managed prompts.

#### 3.5.5. `5_🔬_Evaluation.py`

- This page will configure and run `promptfoo`.
- The `promptfoo` configuration (either static or dynamically generated) will specify prompts using the `langfuse://<prompt-name>` syntax, ensuring that evaluations are run against the versioned prompts managed in Langfuse. This allows for consistent testing and comparison of prompt versions.

## 4. Data Management

### 4.1. File Handling

- **Uploads**: Streamlit's native file uploader (`st.file_uploader`) will be used for all document inputs (primarily PDFs).
  - Pre-upload checks for PDFs (using PyMuPDF) will validate if the PDF has a text layer, warn about image-only PDFs, and show page count/text length.
- **Storage of Uploaded Files**:
  - For immediate processing: Files can be handled in memory or temporarily written to disk within a session.
  - For batch processing: A clear strategy for managing multiple uploaded files is needed (e.g., a temporary session-based directory or a user-designated input folder if `promptfoo` is run on a local directory).
- **Outputs**:
  - Generated reports, analyses, and `promptfoo` evaluation results will be saved to the `outputs/` directory.
  - Timestamped sub-folders for batch processing outputs, including a manifest file summarizing the batch, will be created.
  - Users will be able to download generated files using `st.download_button`.
- **Templates & Prompts**:
  - Report templates will be stored in `templates/`.
  - Prompt templates (if not solely managed in Langfuse) or local backups will be in `prompt_templates/`. Langfuse will be the primary source for prompt content, and local files can serve as fallbacks.

### 4.2. Configuration Data

- `.env` file for sensitive API keys and core configurations.
- `utils/provider_config.py` for LLM provider details, model names, and capabilities (including pricing for estimation).

### 4.3. State Management

- Streamlit's session state (`st.session_state`) will be used to manage:
  - User inputs across pages or reruns.
  - Uploaded file references.
  - Selections for providers, models.
  - Accumulated session costs.
  - State of UI elements (e.g., expanded accordions).

### 4.4. Caching

- `st.cache_resource` will be used for global, expensive objects like the `litellm.Router` and the `LLMClient` instance.
- `st.cache_data` can be used for caching results of functions that return serializable data if appropriate (e.g., processed data from a static file that doesn't change often). Langfuse SDK handles its own prompt caching.

## 5. Analysis & Recommendations

### 5.1. Potential Feature Enhancements

- **Enhanced Error Feedback**: (Remains as a future enhancement)
- **Output Format Selection**: (Remains as a future enhancement)
- **"Bring Your Own Key" Option (Advanced)**: (Remains as a future enhancement)
