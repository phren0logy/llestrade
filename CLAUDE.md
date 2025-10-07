# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is Llestrade (formerly Forensic Psych Report Drafter) — a PySide6 (Qt) desktop application for analyzing and summarizing forensic psychological reports using multiple LLM providers (Anthropic Claude, Google Gemini, Azure OpenAI).

## Key Commands

### Running the Application

```bash
# Run current (legacy) UI
uv run main.py

# Run new simplified UI (under development)
uv run main.py --new-ui
# or
./run_new_ui.sh

# Run with debug mode
./run_debug.sh
```

### Running Tests

```bash
# Run tests from the tests directory
uv run pytest tests/

# Run specific test files
uv run python tests/test_api_keys.py

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
uv run scripts/setup_env.py
```

## Project Structure

```
forensic-report-drafter/
├── main.py                    # Smart launcher (NEW - routes to legacy or new UI)
├── main_legacy.py             # Current application (RENAMED from main.py)
├── main_new.py                # New simplified UI (UNDER DEVELOPMENT)
├── src/
│   ├── config/               # Configuration modules
│   │   ├── app_config.py    # LLM provider configuration
│   │   ├── config.py        # App constants
│   │   ├── logging_config.py # Centralized logging
│   │   └── startup_config.py # Startup configuration
│   └── core/                 # Core utilities
│       ├── exception_handler.py # Global exception handling
│       ├── file_utils.py    # File operations
│       ├── ingest_markdown.py # Markdown processing
│       ├── pdf_utils.py     # PDF processing
│       └── prompt_manager.py # Prompt template management
├── llm/                      # LLM provider package
│   ├── base.py              # Base provider class
│   ├── providers/           # Provider implementations
│   ├── chunking.py          # Document chunking
│   ├── tokens.py            # Token counting
│   ├── factory.py           # Provider factory
│   └── llm_utils_compat.py  # Compatibility layer
├── ui/                       # User interface
│   ├── workers/             # Worker threads
│   └── components/          # Reusable UI components
├── tests/                    # Test suite
├── scripts/                  # Utility scripts
│   └── setup_env.py         # Environment setup
└── src/app/resources/       # Bundled prompts/templates for packaging
```

## Architecture Overview

### Core Components

1. **Main Application** (`main.py`)

   - Entry point, handles Qt plugin paths for macOS
   - Creates the main window with tabbed interface

2. **LLM Integration** (`llm/` directory)

   **Modular Structure**:

   - `llm/base.py`: Abstract base provider class with Qt patterns (signals, properties)
   - `llm/providers/`:
     - `anthropic.py`: AnthropicProvider with native PDF and extended thinking support
     - `gemini.py`: GeminiProvider with extended thinking capabilities
     - `azure_openai.py`: AzureOpenAIProvider with deployment configuration
   - `llm/chunking.py`: Markdown-aware chunking using langchain-text-splitters
   - `llm/tokens.py`: Centralized token counting with LRU caching
   - `llm/factory.py`: Provider factory with Qt-style patterns

   **Key Features**:

   - Token counting with caching via `TokenCounter.count()` and `count_tokens_cached()`
   - Model-aware chunking via `ChunkingStrategy.markdown_headers()` with header preservation
   - `MODEL_CONTEXT_WINDOWS`: Dictionary of model token limits (using 65% for safety)
   - Extended thinking support for Anthropic and Gemini providers
   - Factory pattern via `create_provider()` for easy provider instantiation

3. **Configuration System** (`src/config/app_config.py`)

   - Manages LLM provider settings via `app_settings.json`
   - Azure deployment names read from `AZURE_OPENAI_DEPLOYMENT_NAME` env var
   - `get_configured_llm_provider()`: Main factory method for LLM providers (returns provider instance)

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

5. **Prompt Management** (`src/core/prompt_manager.py`)
   - Loads prompts from `src/app/resources/prompts/`
  - Key prompts: `document_bulk_analysis_prompt.md`, `document_analysis_system_prompt.md`, `integrated_analysis_prompt.md`
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

5. **macOS Tahoe (2025-07-03) - Thread Safety & Memory Issues** [UNDER INVESTIGATION]:
   - **NSWindow main thread error**: Fixed by using Qt signals for all UI operations in exception handler
   - **malloc double-free error**: Ongoing investigation - occurs with both Azure OpenAI and Anthropic providers
   - Debug tools added:
     - `faulthandler` enabled in main.py for crash stack traces
     - `run_debug.sh` script with memory debugging environment variables
     - Memory usage logging in `llm_summary_thread.py` 
     - `test_memory_crash.py` minimal reproduction script
   - Run with `./run_debug.sh` to enable full debugging
   - The issue appears to be Qt/PySide6 memory management, not provider-specific

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

- Reduces logging verbosity for LLM provider initialization
- Hides Qt plugin warnings unless debugging is enabled

To enable debug output, set these environment variables:

- `DEBUG=true` - General debug output
- `DEBUG_LLM=true` - LLM provider debug logging
- `DEBUG_QT=true` - Qt plugin debug output

Logs and crash reports are in `~/Documents/llestrade/` (previously `~/.forensic_report_drafter/`)

## LLM Module Architecture

### Current State (2025-07-03)

- All code now uses the new modular `llm/` package directly
- Migration from `llm_utils_compat.py` completed
- Clean, modular structure with Qt integration patterns

### LLM API Examples

```python
# Create a provider
from src.common.llm import create_provider
provider = create_provider("anthropic")  # or "gemini", "azure_openai", "auto"

# Generate a response
response = provider.generate(
    prompt="What is the capital of France?",
    model="claude-3-sonnet",
    temperature=0.7
)

# Count tokens
from src.common.llm.tokens import TokenCounter
result = TokenCounter.count(text="Hello world", provider="anthropic")

# Markdown-aware chunking
from src.common.llm.chunking import ChunkingStrategy
chunks = ChunkingStrategy.markdown_headers(text, max_tokens=100000, overlap_tokens=2000)

# Combine transcript with fragments (utility function)
from src.core.prompt_manager import combine_transcript_with_fragments
combined = combine_transcript_with_fragments(transcript, fragment)
```

### Qt Integration Patterns

- All providers inherit from `BaseProvider(QObject)`
- Providers emit Qt signals for async operations
- Factory uses Qt-style naming conventions
- Thread-safe operations with proper signal/slot connections

## New Simplified UI Development

A new memory-safe, stage-based UI is being developed in parallel with the current tab-based UI:

### Running the New UI

```bash
# Run new UI
uv run main.py --new-ui
# or
./run_new_ui.sh
```

### Completed Stages

1. **Welcome Stage** (`src/new/stages/welcome_stage.py`)
   - Recent projects grid with metadata display
   - API key status indicators
   - Quick actions (New Project, Open Project)

2. **Project Setup Stage** (`src/new/stages/setup_stage.py`)
   - Case information form
   - Subject details
   - Output directory selection
   - API key configuration

3. **Document Import Stage** (`src/new/stages/import_stage.py`)
   - Drag-and-drop file interface
   - Multiple file selection
   - File type validation (PDF, DOC, DOCX, TXT, MD)
   - Live preview for text files

4. **Document Processing Stage** (`src/new/stages/process_stage.py`)
   - PDF conversion via Azure Document Intelligence
   - Word document conversion
   - Text file to markdown conversion
   - Thread-safe processing with progress tracking

5. **Analysis Stage** (`src/new/stages/analysis_stage.py`)
   - LLM provider selection (Anthropic, Gemini, Azure OpenAI)
   - Document summarization with chunking for large files
   - Progress tracking and status updates
   - Skip already summarized files option

6. **Report Generation Stage** (`src/new/stages/report_stage.py`)
   - Integrated analysis from all summaries
   - Choice between comprehensive and template-based reports
   - LLM provider selection
   - Report preview and export

### Architecture

- **Project-based workflow**: All work organized in `.frpd` project files
- **Stage-based navigation**: Linear workflow with back/next navigation
- **Memory-safe design**: Single worker thread per stage, proper cleanup
- **Auto-save**: Project state saved every 60 seconds
- **Secure API storage**: Uses OS keychain with encrypted fallback

### Status

The new UI is functional through the Report Generation stage (6 of 7 stages complete). Users can create projects, import documents, process them, generate summaries, and create integrated reports. Only the Refinement stage remains to be implemented.

## PySide6 UI Best Practices

### UI Patterns to Avoid
1. **Dynamic widget replacement**: Don't repeatedly create/destroy widgets. Use QStackedWidget instead.
2. **Manual layout cleanup**: Avoid complex layout deletion logic with processEvents().
3. **Direct widget reparenting**: Let Qt manage parent-child relationships.
4. **Excessive deleteLater() calls**: Can lead to memory management issues.
5. **Complex initialization chains**: Keep widget initialization simple and predictable.

### Recommended Patterns
1. **QStackedWidget**: For switching between different views/stages
2. **Pre-create widgets**: Create all widgets at startup, switch visibility
3. **Signal/slot connections**: Use Qt's built-in patterns for communication
4. **Parent widget management**: Set parent in constructor, let Qt handle cleanup
5. **Simple state management**: Use reset() methods instead of recreating widgets

### Example: Stage-based UI with QStackedWidget
```python
# Good pattern - pre-create widgets and switch between them
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.stage_stack = QStackedWidget()
        self.setCentralWidget(self.stage_stack)
        
        # Pre-create all stages
        self.stages = {
            'welcome': WelcomeStage(),
            'setup': SetupStage(),
            'process': ProcessStage()
        }
        
        # Add all stages to stack
        for stage in self.stages.values():
            self.stage_stack.addWidget(stage)
    
    def switch_stage(self, stage_name):
        if stage_name in self.stages:
            self.stage_stack.setCurrentWidget(self.stages[stage_name])

# Bad pattern - dynamic widget replacement
# DON'T DO THIS:
def set_stage_widget(self, widget):
    if self.content_area.layout():
        # Complex cleanup logic
        old_layout = self.content_area.layout()
        while old_layout.count():
            item = old_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        QApplication.processEvents()  # Force deletion
        old_layout.deleteLater()
```

## Documentation

### Documentation Structure
- `README.md` - Main project documentation and status
- `CLAUDE.md` - Technical reference for AI assistants
- `docs/progress.md` - Changelog of completed work
- `docs/roadmap.md` - Future development plans and feature ideas
- `docs/simplified_workflow.md` - New UI architectural design

### Documentation Guidelines
- Keep the main README.md updated with current project status
- Log completed work in docs/progress.md with dates
- Add feature ideas and plans to docs/roadmap.md
- Avoid specific dates in forward-looking documentation
- Technical implementation details belong in CLAUDE.md
