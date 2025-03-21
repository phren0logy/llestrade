# Forensic Report Drafter

This experimental project seeks to write a rough first draft based on supplied sources of information. This is not intended for real-world use.

## Project Overview

The Forensic Psych Report Drafter is an application that helps with:

1. Breaking down markdown templates into sections
2. Generating clean LLM prompts from these sections
3. Combining these prompts with transcript text
4. Processing them through Claude AI
5. Analyzing PDF documents
6. Processing PDFs with Azure Document Intelligence
7. Summarizing and analyzing documents with timeline generation
8. Creating integrated multi-document analyses
9. Refining draft reports 

## Refactored Application Structure

The application has been refactored into a modular structure for better maintainability:

```
forensic-psych-report-drafter/
├── config.py                # Configuration settings
├── file_utils.py            # File operations utilities
├── ingest_markdown.py       # Markdown processing utilities
├── llm_utils.py             # LLM interaction utilities
├── main.py                  # Main application entry point
├── pdf_utils.py             # PDF processing utilities
├── requirements.txt         # Dependencies
├── run.py                   # Launcher script
├── ui/                      # UI components
│   ├── __init__.py
│   ├── base_tab.py          # Base class for tabs
│   ├── prompts_tab.py       # Template generation tab
│   ├── record_review_tab.py # PDF processing tab
│   ├── refinement_tab.py    # Report refinement tab
│   └── testing_tab.py       # PDF analysis tab
└── (original files preserved)
```

## Features

- **Template Generation**: Process markdown files into LLM-ready prompts with transcripts
- **PDF Analysis**: Analyze PDF documents with Claude AI
- **PDF Processing**: Process PDF files with Azure Document Intelligence to extract content in JSON and Markdown formats
- **Document Summarization**: Generate comprehensive document summaries with timelines from extracted content
- **Integrated Analysis**: Combine multiple document summaries into a unified analysis with comprehensive timeline
- **Report Refinement**: Refine draft reports with extended thinking capabilities
- **Improved UI**: Larger, more readable interface with tabbed organization
- **Better Error Handling**: Robust error handling and recovery

## Usage

### Prerequisites

- Python 3.8+
- [uv](https://github.com/astral-sh/uv) - Fast Python package manager (installation: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Anthropic API key (set as ANTHROPIC_API_KEY environment variable)
- Azure Document Intelligence API credentials (set as AZURE_ENDPOINT and AZURE_KEY environment variables)

### Installing and Running the Application

The application includes a launcher script (`run.py`) that handles dependency management with uv and starts the application:

```bash
# Install dependencies and run application
python run.py

# Skip dependency installation
python run.py --skip-deps
```

### Manual Setup with uv

If you prefer to manage dependencies manually:

```bash
# Install dependencies with uv
uv pip install -r requirements.txt

# Run the application with uv
uv run main.py
```

### Application Workflow

1. **Template Generation**:
   - Select a markdown file structured with Header 1 sections
   - Select a transcript file
   - Process with Claude AI
   - View and save results

2. **PDF Analysis**:
   - Select a prompt file with questions for the PDF
   - Select a PDF file
   - Process with Claude AI
   - View and save analysis

3. **Record Review** (PDF Processing):
   - Select a directory containing PDF files
   - Choose an output directory
   - Optionally enter Azure Document Intelligence credentials
   - Process PDFs (split large files automatically)
   - Extract content using Azure Document Intelligence
   - Summarize extracted content with Claude AI
   - Generate structured analyses with timelines
   - Combine individual summaries into a single document
   - Generate an integrated analysis with a comprehensive timeline
   - View and access JSON, Markdown, and Analysis outputs

4. **Report Refinement**:
   - Select a draft report
   - Select a transcript file
   - Customize the refinement prompt
   - Process with extended thinking
   - View and save refined report

## Development Notes

### Managing Dependencies with uv

This project uses [uv](https://github.com/astral-sh/uv) for managing dependencies:

```bash
# Adding new dependencies
uv pip install <package-name>

# Adding and updating requirements.txt
uv pip freeze > requirements.txt

# Compiling requirements (alternative approach)
uv pip compile requirements.in -o requirements.txt
```

### Why uv?

- 10-20x faster than traditional pip
- Automatic virtual environment management
- Seamless replacement for pip, pip-tools, and virtualenv
- Better dependency resolution
- Drop-in compatibility with existing workflows

## Notes on Implementation

- API interactions use Anthropic's latest Claude 3 models
- Document summarization includes timeline generation in table format
- Integrated analysis combines multiple document summaries with chronological timelines
- Extended thinking capabilities for complex reasoning tasks
- Error handling with graceful fallbacks
