# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Forensic Psych Report Drafter - a PySide6 (Qt) desktop application for analyzing and summarizing forensic psychological reports using multiple LLM providers (Anthropic Claude, Google Gemini, Azure OpenAI).

## Key Commands

### Running the Application

```bash
uv run main.py
```

### Running Tests

```bash
# Test API connectivity
uv run verify_llm_connection.py

# Test LLM summarization functionality
uv run direct_test.py

# Test problematic files
uv run test_diagnosis.py path/to/file.md

# Run individual test files
uv run tests/test_llm_utils.py
uv run tests/test_analysis_integration.py
uv run tests/test_gemini.py
uv run tests/test_extended_thinking.py
uv run tests/test_api_keys.py
```

### Environment Setup

```bash
# Create virtual environment with uv
uv init

# Install dependencies
uv sync

or

uv add
uv remove


# Interactive environment setup
uv run setup_env.py
```

## Architecture Overview

### Core Components

1. **Main Application** (`main.py`)

   - Entry point, handles Qt plugin paths for macOS
   - Creates the main window with tabbed interface

2. **LLM Integration** (`llm/` directory and `llm_utils_compat.py`)

   **New Modular Structure** (`llm/` directory):
   - `llm/base.py`: Abstract base provider class with Qt patterns (signals, properties)
   - `llm/providers/`:
     - `anthropic.py`: AnthropicProvider with native PDF and extended thinking support
     - `gemini.py`: GeminiProvider with extended thinking capabilities
     - `azure_openai.py`: AzureOpenAIProvider with deployment configuration
   - `llm/chunking.py`: Markdown-aware chunking using langchain-text-splitters
   - `llm/tokens.py`: Centralized token counting with LRU caching
   - `llm/factory.py`: Provider factory with Qt-style patterns
   
   **Compatibility Layer** (`llm_utils_compat.py`):
   - Temporary shim for backward compatibility during migration
   - Maps old API (`LLMClient`, `LLMClientFactory`) to new structure
   - Provides deprecation warnings for smooth transition
   - Will be removed once full migration is complete
   
   **Key Features**:
   - Token counting with caching via `cached_count_tokens()`
   - Model-aware chunking via `chunk_document()` with markdown header preservation
   - `MODEL_CONTEXT_WINDOWS`: Dictionary of model token limits (using 65% for safety)
   - Extended thinking support for Anthropic and Gemini providers

3. **Configuration System** (`app_config.py`)

   - Manages LLM provider settings via `app_settings.json`
   - Azure deployment names read from `AZURE_OPENAI_DEPLOYMENT_NAME` env var
   - `get_configured_llm_client()`: Main factory method for LLM providers (currently using compatibility layer)

4. **UI Structure** (in `ui/` directory)

   - **Base**: `BaseTab` provides common functionality for all tabs
   - **Main Tabs**:
     - `analysis_tab.py`: Document summarization and integration
     - `pdf_processing_tab.py`: PDF to markdown conversion
     - `refinement_tab.py`: Refine and revise generated content
     - `record_review_tab.py`: Review and edit records
     - `prompts_tab.py`: Manage prompt templates
   - **Worker Threads** (in `ui/workers/`):
     - `llm_summary_thread.py`: Handles document summarization
     - `integrated_analysis_thread.py`: Creates integrated analysis
     - `pdf_processing_thread.py`: Converts PDFs to markdown
     - All inherit from `QThread` for non-blocking operations

5. **Prompt Management** (`prompt_manager.py`)
   - Loads prompts from `prompt_templates/` directory
   - Key prompts: `document_summary_prompt.md`, `document_analysis_system_prompt.md`, `integrated_analysis_prompt.md`
   - `get_template()`: Returns single prompt string with variable substitution
   - `get_prompt_template()`: Returns dict with separate system/user prompts for complex templates

### Data Flow

1. User selects markdown files in Analysis tab
2. Files are processed sequentially (one at a time) to avoid thread issues
3. Each file is sent to LLM with subject info and case background
4. Summaries are saved to `{output_dir}/summaries/`
5. Summaries can be combined and analyzed for integrated report

### Thread Safety

- UI operations use Qt signals/slots with `Qt.ConnectionType.QueuedConnection`
- File processing is sequential to avoid concurrency issues
- Worker threads emit progress via signals: `progress_signal`, `finished_signal`, `error_signal`

## Important Configuration

### Environment Variables (.env)

```
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://...
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1
OPENAI_API_VERSION=2025-01-01-preview
```

### LLM Settings (app_settings.json)

- Selected provider stored in `selected_llm_provider_id`
- Azure deployment names should match exactly (e.g., "gpt-4.1" not "gpt-41")
- Provider configs include model names and enablement status

## Common Issues & Solutions

1. **"Unknown error" in Analysis tab**: Usually thread/signal issues. Files are now processed sequentially.

2. **Azure OpenAI deployment name mismatch**: Ensure deployment name in settings matches exactly what's in Azure (dots included).

3. **Tiktoken errors with Azure**: The `count_tokens` method properly handles tiktoken imports to avoid "local variable not associated" errors.

4. **macOS Qt plugin issues**: `main.py` sets `QT_PLUGIN_PATH` before importing PySide6.

## Development Notes

- Temperature settings are configured per task (0.1 for summaries, 0.7 for refinements)
- Document chunking is model-aware - uses 65% of the model's context window for safety
  - GPT-4.1: ~650,000 tokens per chunk
  - Claude Sonnet 4: ~130,000 tokens per chunk  
  - Gemini 2.5 Pro: ~1,300,000 tokens per chunk
- Chunking with 2,000 token overlap for continuity
- Integrated analysis now supports chunking for large document sets
- Default model is now `claude-sonnet-4-20250514`
- Temporary files use `_temp` suffix during write operations
- All file paths should be absolute, not relative
- Signal/slot connections must be properly disconnected to avoid memory leaks

### Startup Configuration

The application uses `startup_config.py` to provide a clean startup experience:
- Suppresses deprecation warnings from the compatibility layer
- Reduces logging verbosity for LLM provider initialization
- Hides Qt plugin warnings unless debugging is enabled

To enable debug output, set these environment variables:
- `DEBUG=true` - General debug output
- `DEBUG_LLM=true` - LLM provider debug logging
- `DEBUG_QT=true` - Qt plugin debug output

## LLM Module Migration Status

### Current State (2025-06-30)
- All code currently uses `llm_utils_compat.py` as a compatibility layer
- The old monolithic `llm_utils.py` (2,467 lines) is still present but not imported
- New modular `llm/` package is fully implemented and functional

### Migration Path
1. **Phase 1 (COMPLETED)**: Create new modular structure and compatibility layer
2. **Phase 2 (CURRENT)**: Update all imports to use compatibility layer
3. **Phase 3 (TODO)**: Gradually migrate from compatibility layer to direct `llm/` imports
4. **Phase 4 (TODO)**: Remove `llm_utils.py` and `llm_utils_compat.py`

### New LLM API Examples

```python
# Current (using compatibility layer)
from llm_utils_compat import LLMClientFactory
client = LLMClientFactory.create_client(provider="auto")

# Future (direct usage)
from llm import create_provider
provider = create_provider("anthropic", api_key="...")
response = await provider.generate_async(prompt, model="claude-3")

# Markdown-aware chunking
from llm.chunking import chunk_document
chunks = chunk_document(text, max_tokens=100000, overlap_tokens=2000)
```

### Qt Integration Patterns
- All providers inherit from `BaseProvider(QObject)`
- Providers emit Qt signals for async operations
- Factory uses Qt-style naming conventions
- Thread-safe operations with proper signal/slot connections
