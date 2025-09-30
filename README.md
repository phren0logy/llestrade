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

## Legacy UI Reference

The original tabbed UI has been removed from the repository as of commit 6401a40cd1c4fead93e72b4e7dbfda916bf1cb99. If you need to inspect that implementation for historical reference, check out that revision (or any earlier one) and review the `src/legacy/` package in that commit.

## Project Structure

```
forensic-report-drafter/
├── main.py                    # Application entry point (launches src.app)
├── src/
│   ├── app/
│   │   ├── __init__.py      # Re-exports ProjectManager, SecureSettings, etc.
│   │   ├── core/            # Dashboard-specific domain logic
│   │   ├── ui/
│   │   │   ├── dialogs/
│   │   │   ├── stages/
│   │   │   └── widgets/
│   │   ├── workers/         # QRunnable-based background jobs
│   │   └── resources/
│   │       ├── prompts/
│   │       └── templates/
│   ├── config/               # Application configuration modules
│   │   ├── app_config.py
│   │   ├── config.py
│   │   ├── logging_config.py
│   │   └── startup_config.py
│   ├── core/                 # Shared utilities reused by the dashboard
│   │   ├── exception_handler.py
│   │   ├── file_utils.py
│   │   ├── ingest_markdown.py
│   │   ├── pdf_utils.py
│   │   └── prompt_manager.py
│   └── common/llm/           # LLM provider abstractions and helpers
│       ├── base.py
│       ├── providers/
│       ├── chunking.py
│       ├── tokens.py
│       └── factory.py
├── tests/                    # Test suite
├── scripts/                  # Utility scripts
├── var/                      # Runtime artefacts (gitignored contents)
│   ├── logs/
│   └── test_output/
```

## Workspace Output Layout

When you create a project, the application maintains a self-contained workspace with derived outputs. The key folders are:

```
<project>/
├── project.frpd                # Project metadata (source config, helper, UI state)
├── sources.json                # Included folders (+ warnings for root files)
├── converted_documents/        # Markdown outputs mirroring selected folder structure
│   ├── medical_records/
│   │   ├── report1.md
│   │   └── report2.md
│   └── legal_docs/
│       └── case_summary.md
├── highlights/                 # Highlight outputs for PDFs (mirrors converted_documents)
│   ├── medical_records/
│   │   ├── report1.highlights.md
│   │   └── report2.highlights.md
│   └── legal_docs/
│       └── case_summary.highlights.md
├── bulk_analysis/
│   ├── clinical_records/
│   │   ├── config.json         # Prompts, model, folder subset
│   │   └── outputs/
│   │       ├── medical_records/
│   │       │   ├── report1.md
│   │       │   └── report2.md
│   │       └── legal_docs/
│   │           └── case_summary.md
│   └── legal_documents/
│       ├── config.json
│       └── outputs/
│           └── legal_docs/
│               └── case_summary.md
└── backups/
    └── 2025-01-01T120000Z/    # Snapshot copies created by the app
```

Notes:
- Highlights are extracted only for PDFs. If a PDF has no highlights, a placeholder `.highlights.md` file is created with a processed timestamp.
- Dashboard highlight counts use a PDF-only denominator (e.g., `Highlights: X of Y` where `Y` is the number of PDF-converted documents), so DOCX and other non-PDF sources are excluded from the “pending highlights” count.

## Configuration

### Application Settings

The application stores settings in `var/app_settings.json` (created on first run):
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
   - 6 of 7 stages complete:
     - ✅ Welcome & Project Management
     - ✅ Project Setup (case information)
     - ✅ Document Import (drag & drop)
     - ✅ Document Processing (PDF/Word/Text conversion)
     - ✅ Analysis (LLM summarization)
     - ✅ Report Generation (integrated analysis)
     - ❌ Refinement & Export (not implemented)

The new UI addresses memory issues through single-stage architecture and provides a project-based workflow with `.frpd` files.

## Documentation

- `CLAUDE.md` - AI assistant guidance and technical details
- `docs/progress.md` - Development changelog
- `docs/roadmap.md` - Future features and development priorities
- `docs/simplified_workflow.md` - New UI architecture reference
