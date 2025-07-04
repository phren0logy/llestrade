# Forensic Psych Report Drafter

A professional PySide6 (Qt) desktop application for analyzing and summarizing forensic psychological reports using multiple LLM providers (Anthropic Claude, Google Gemini, Azure OpenAI).

## Features

- **Multiple LLM Providers**: Support for Anthropic Claude, Google Gemini, and Azure OpenAI GPT-4
- **Document Processing**: Convert PDFs to markdown and analyze forensic psychological reports
- **Smart Chunking**: Markdown-aware document chunking for large files
- **Batch Processing**: Process multiple documents with progress tracking
- **Integrated Analysis**: Combine multiple reports into comprehensive summaries
- **Extended Thinking**: Support for Claude and Gemini's advanced reasoning capabilities
- **Debug Dashboard**: Real-time monitoring and debugging tools (in debug mode)
- **Error Recovery**: Robust error handling with retry logic and crash recovery

## Installation

### Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) package manager (recommended) or pip

### Setup Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/forensic-report-drafter.git
   cd forensic-report-drafter
   ```

2. **Install dependencies using uv** (recommended)
   ```bash
   uv sync
   ```
   
   Or using pip:
   ```bash
   pip install -r pyproject.toml
   ```

3. **Configure API keys**
   ```bash
   # Copy the template
   cp config.template.env .env
   
   # Edit .env and add your API keys:
   # ANTHROPIC_API_KEY=sk-ant-...
   # GEMINI_API_KEY=AIza...
   # AZURE_OPENAI_API_KEY=...
   # AZURE_OPENAI_ENDPOINT=https://...
   # AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
   ```

4. **Run the application**
   ```bash
   uv run main.py
   
   # Or with debug mode enabled:
   uv run main.py --debug
   ```

## Quick Start

### Interactive Setup

For first-time users, run the interactive setup:
```bash
uv run scripts/setup_env.py
```

This will:
- Create your `.env` file
- Guide you through API key configuration
- Test your LLM connections
- Run a sample analysis

### Basic Workflow

1. **PDF Processing** (optional)
   - Use the PDF Processing tab to convert PDF reports to markdown
   - Select input PDFs and choose an output directory

2. **Document Analysis**
   - In the Analysis tab, select folders containing markdown documents
   - Enter subject information (name, DOB, case details)
   - Click "Generate Summaries with LLM" to create individual summaries
   - Use "Combine Summaries" to merge all summaries
   - Generate an integrated analysis of all documents

3. **Refinement**
   - Use the Refinement tab to edit and improve generated content
   - Apply custom prompts for specific refinements

4. **Report Generation**
   - Use the Prompts tab to generate final report sections
   - Apply templates for standardized formatting

## Project Structure

```
forensic-report-drafter/
├── main.py                    # Application entry point
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
│   └── factory.py           # Provider factory
├── ui/                       # User interface
│   ├── workers/             # Worker threads
│   └── components/          # Reusable UI components
├── tests/                    # Test suite
├── scripts/                  # Utility scripts
└── prompt_templates/         # LLM prompt templates
```

## Configuration

### Application Settings

The application stores settings in `app_settings.json`:
```json
{
  "selected_llm_provider_id": "anthropic",
  "llm_provider_configs": {
    "anthropic": {
      "enabled": true,
      "default_model": "claude-3-sonnet-20240229"
    },
    "gemini": {
      "enabled": true,
      "default_model": "gemini-1.5-pro"
    },
    "azure_openai": {
      "enabled": true,
      "default_deployment_name": "gpt-4"
    }
  }
}
```

### Debug Mode

Enable debug mode for enhanced logging and monitoring:
```bash
# Via command line
uv run main.py --debug

# Via environment variable
DEBUG=true uv run main.py
```

Debug mode features:
- Debug Dashboard with real-time monitoring
- Detailed logging to `~/.forensic_report_drafter/logs/`
- System resource tracking
- Operation timing and performance metrics

## Advanced Features

### Extended Thinking

For complex analysis requiring step-by-step reasoning:
- Anthropic Claude: Automatically uses thinking mode for integrated analysis
- Google Gemini: Uses extended thinking API when available

### Large Document Processing

The application handles large documents through:
- Smart chunking with configurable overlap
- Token counting with caching
- Progress tracking for long operations
- Memory-efficient processing

### Error Recovery

Built-in resilience features:
- Automatic retry with exponential backoff
- Crash recovery on startup
- Detailed error logging
- Transaction-safe file operations

## Troubleshooting

### Common Issues

1. **"Module not found" errors**
   ```bash
   # Ensure dependencies are installed
   uv sync
   ```

2. **API Connection Issues**
   ```bash
   # Test your API connections
   uv run scripts/setup_env.py
   ```

3. **Large Document Timeouts**
   - Increase timeout in settings
   - Check token limits for your model
   - Enable debug mode to see detailed progress

4. **Qt Plugin Issues (macOS)**
   - The application automatically handles Qt plugin paths
   - If issues persist, check `QT_PLUGIN_PATH` environment variable

### Diagnostic Tools

- `scripts/setup_env.py`: Interactive environment setup and testing
- `tests/test_api_keys.py`: Verify API key configuration
- `tests/test_large_document_processing.py`: Test large document handling

### Log Files

Logs are stored in:
- macOS/Linux: `~/.forensic_report_drafter/logs/`
- Windows: `%USERPROFILE%\.forensic_report_drafter\logs\`

Crash reports are saved to:
- `~/.forensic_report_drafter/crashes/`

## Development

### Running Tests

```bash
# Run all tests
uv run pytest tests/

# Run specific test file
uv run pytest tests/test_gemini.py -v

# Run with coverage
uv run pytest --cov=. tests/
```

### Code Style

The project uses:
- Type hints throughout
- Qt signal/slot patterns
- Async operations in worker threads
- Comprehensive error handling

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## Requirements

Key dependencies:
- PySide6 (Qt for Python)
- anthropic (Claude API)
- google-generativeai (Gemini API)
- openai (Azure OpenAI)
- pypdf (PDF processing)
- pdfplumber (PDF text extraction)
- psutil (System monitoring)
- python-dotenv (Environment management)

See `pyproject.toml` for complete dependency list.

## License

[Your License Here]

## Support

For issues and feature requests, please use the GitHub issue tracker.

For detailed documentation, see the `docs/` directory and `CLAUDE.md` for AI assistant guidance.

## Project Status

### Current Implementation
The application has two UIs running in parallel:

1. **Legacy UI** (default) - Fully functional tab-based interface
   - Run with: `uv run main.py`
   
2. **New UI** (in development) - Modern stage-based workflow
   - Run with: `uv run main.py --new-ui`
   - 5 of 6 stages complete:
     - ✅ Welcome & Project Management
     - ✅ Project Setup (case information)
     - ✅ Document Import (drag & drop)
     - ✅ Document Processing (PDF/Word/Text conversion)
     - ✅ Analysis (LLM summarization)
     - ❌ Report Generation (not implemented)
     - ❌ Refinement & Export (not implemented)

The new UI addresses memory issues through single-stage architecture and provides a project-based workflow with `.frpd` files.

## Documentation

- `CLAUDE.md` - AI assistant guidance and technical details
- `docs/progress.md` - Development changelog
- `docs/roadmap.md` - Future features and development priorities
- `docs/simplified_workflow.md` - New UI architecture reference