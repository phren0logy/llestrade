# Llestrade

Llestrade is a PySide6 (Qt) desktop application for analyzing and summarizing forensic psychological reports using multiple LLM providers (Anthropic Claude, Anthropic Claude via AWS Bedrock, Google Gemini, Azure OpenAI).
Note: The application was previously named “Forensic Psych Report Drafter.”

## Features

- **Multiple LLM Providers**: Support for Anthropic Claude (cloud & AWS Bedrock), Google Gemini, and Azure OpenAI GPT-4
- **Document Processing**: Convert PDFs to markdown and analyze forensic psychological reports
- **Smart Chunking**: Markdown-aware document chunking for large files
- **Batch Processing**: Process multiple documents with progress tracking
- **Integrated Analysis**: Combine multiple reports into comprehensive bulk analysis outputs
- **Extended Thinking**: Support for Claude and Gemini's advanced reasoning capabilities
- **Debug Dashboard**: Real-time monitoring and debugging tools (in debug mode)
- **Error Recovery**: Robust error handling with retry logic and crash recovery

## Installation

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager (recommended) or pip

### Setup Steps

1. **Clone the repository**

   ```bash
   git clone https://github.com/phren0logy/llestrade.git
   cd llestrade
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

  Use the Settings panel to add Azure DI, Azure OpenAI, and Anthropic credentials.

4. **Run the application**

   ```bash
   uv run main.py

   # Or with debug mode enabled:
   uv run main.py --debug
   ``

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

2. **Project Placeholders & Document Analysis**

   - The new project wizard lets you pick or author placeholder lists (e.g., client name, case number). These values surface on the Bulk Analysis and Reports tabs and are substituted into prompts at runtime.
   - In the Analysis tab, select folders containing markdown documents
   - Enter subject information / adjust placeholders in Project Settings as needed
   - Click "Run Pending" to create per-document bulk analysis outputs
   - Use "Run Combined" to merge bulk analysis outputs
   - Placeholder status chips help you spot missing values before running jobs

3. **Refinement**

   - Use the Refinement tab to edit and improve generated content
   - Apply custom prompts for specific refinements

4. **Report Generation**
   - Use the Prompts tab to generate final report sections
   - Apply templates for standardized formatting

## Project Structure

```
llestrade/
├── main.py                    # Application entry point (launches src.app)
├── src/
│   ├── app/
│   │   ├── __init__.py        # Re-exports project entry points (run, ProjectManager, etc.)
│   │   ├── core/              # Dashboard domain logic (project manager, file tracker, metrics)
│   │   ├── ui/
│   │   │   ├── dialogs/       # Qt dialogs
│   │   │   ├── stages/        # Top-level Qt widgets (main window, workspace shell)
│   │   │   ├── workspace/     # Decomposed workspace tabs
│   │   │   │   ├── controllers/
│   │   │   │   ├── services/
│   │   │   │   ├── bulk_tab.py / highlights_tab.py / reports_tab.py
│   │   │   └── widgets/       # Shared UI components
│   │   ├── workers/           # QRunnable-based background jobs
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
- Bulk analysis and report prompts now substitute project placeholders (client, case, project name) along with per-document metadata. Ensure required placeholders are filled in Project Settings before running jobs.

## YAML Front Matter

All markdown artefacts generated by Llestrade include a YAML front-matter block that captures provenance and runtime metadata. This is handled centrally by `src/common/markdown/frontmatter_utils.py` using the `python-frontmatter` library, so every worker shares the same structure.

Each document records:

- `project_path`: Absolute path to the project workspace that produced the file.
- `created_at`: ISO 8601 timestamp (UTC) for when the markdown was written.
- `generator`: Identifier for the component that generated the file (`conversion_worker`, `highlight_extraction`, `bulk_analysis_worker`, `bulk_reduce_worker`, `report_worker`, etc.).
- `sources`: List of inputs (absolute path, project-relative path, file kind, role, and checksum).
- `prompts`: Prompt files or template IDs that influenced the output (role-labelled).
- Additional keys specific to the workflow (for example `converter`, `pages_detected`, `highlight_count`, `prompt_hash`, `document_type`, or `refinement_tokens`).

Example front matter from a converted PDF:

```yaml
---
project_path: /Users/me/Documents/cases/case-a
created_at: 2025-01-04T19:22:18.304218+00:00
generator: conversion_worker
sources:
  - path: /Users/me/Documents/cases/case-a/sources/report.pdf
    relative: sources/report.pdf
    kind: pdf
    role: primary
    checksum: 2d5df4…
converter: pdf-local
pages_detected: 14
pages_pdf: 14
---
```

This metadata is consumed by downstream tooling (dashboards, manifests, audits) and provides a consistent way to trace where every markdown document came from. When extending the app, prefer augmenting the front matter via the helper rather than writing YAML by hand.

## Prompt Placeholders

Prompt templates use `{placeholder}` tokens that the workers populate at runtime. Placeholder requirements are defined in `src/app/core/prompt_placeholders.py` and validated whenever a prompt is loaded, so missing required tokens fail fast instead of producing malformed requests. The same registry powers the UI tooltips on prompt selectors.

| Prompt                        | Template file                                | Required placeholders                                          | Optional placeholders                                                                                 |
| ----------------------------- | -------------------------------------------- | -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Document analysis (system)    | `prompts/document_analysis_system_prompt.md` | None                                                           | `{subject_name}`, `{subject_dob}`, `{case_info}`                                                      |
| Document bulk analysis (user) | `prompts/document_bulk_analysis_prompt.md`   | `{document_content}`                                           | `{subject_name}`, `{subject_dob}`, `{case_info}`, `{document_name}`, `{chunk_index}`, `{chunk_total}` |
| Integrated analysis           | `prompts/integrated_analysis_prompt.md`      | `{document_content}`                                           | `{subject_name}`, `{subject_dob}`, `{case_info}`                                                      |
| Report generation (user)      | `prompts/report_generation_user_prompt.md`   | `{template_section}`, `{transcript}`, `{additional_documents}` | `{section_title}`, `{document_content}`                                                               |
| Report refinement (user)      | `prompts/refinement_prompt.md`               | `{draft_report}`, `{template}`                                 | `{transcript}`                                                                                        |
| Report instructions           | `prompts/report_generation_instructions.md`  | `{template_section}`, `{transcript}`                           | None                                                                                                  |
| Report generation (system)    | `prompts/report_generation_system_prompt.md` | None                                                           | None                                                                                                  |
| Report refinement (system)    | `prompts/report_refinement_system_prompt.md` | None                                                           | None                                                                                                  |

Bulk and report workers automatically inject additional runtime placeholders:

- `{source_pdf_filename}`, `{source_pdf_relative_path}`, `{source_pdf_absolute_path}`, `{source_pdf_absolute_url}` for each document derived from a PDF
- Combined runs expose `{reduce_source_list}`, `{reduce_source_table}`, `{reduce_source_count}` summarising aggregated inputs
- `{project_name}` and `{timestamp}` resolve at execution time

When building custom prompts, include every required placeholder shown above. Optional placeholders are always supplied (with an empty string if the value is unavailable), so they can be added or removed without breaking validation. If you introduce a new prompt template, add its specification to the registry so documentation and tooltips stay aligned.

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
    "anthropic_bedrock": {
      "enabled": true,
      "default_model": "anthropic.claude-sonnet-4-5-20250929-v1:0"
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

### AWS Bedrock Credentials

Claude models delivered through AWS Bedrock rely on the AWS CLI credential chain. Run `aws configure` (for long-term access keys) or `aws configure sso` (for IAM Identity Center) so credentials are written to `~/.aws/credentials` and `~/.aws/config`. Llestrade reads those settings automatically; no AWS secrets are stored in the application. Optional overrides for profile, region, and the default Bedrock Claude model can be set under **Settings → Configure API Keys → AWS Bedrock (Claude)**.

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
- Detailed logging to `~/Documents/llestrade/logs/`
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

- macOS/Linux: `~/Documents/llestrade/logs/`
- Windows: `%USERPROFILE%\\Documents\\llestrade\\logs\\`

Crash reports are saved to:

- `~/Documents/llestrade/crashes/`

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

The MIT License (MIT)

Copyright © 2025 Andrew Nanton


Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the “Software”), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

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
