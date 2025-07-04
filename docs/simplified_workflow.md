# Simplified Forensic Report Drafter Workflow

## Overview

This document outlines a project-based workflow for the Forensic Report Drafter application. The design emphasizes a modern, intuitive UI.

## Key Technologies

- Backend written in FastAPI (this is a git submodule)
- Frontend in Electron, using the playwright MCP for testing.

## Core Principles

1. **Project-Based Organization**: All work happens within isolated project contexts
2. **Intuitive Workflow**: Guide users through a clear sequence of steps
3. **Clear State Management**: Explicit project state with automatic saves

## Project Structure

### Project File Format (.frpd - Forensic Report Project Data)

```json
{
  "version": "1.0",
  "project_id": "uuid-string",
  "created_date": "2025-07-03T10:00:00Z",
  "last_modified": "2025-07-03T14:30:00Z",
  "metadata": {
    "case_name": "Smith v. Jones",
    "case_number": "2025-CV-1234",
    "subject_name": "John Smith",
    "date_of_birth": "1985-03-15",
    "evaluator": "Dr. Jane Doe",
    "case_description": "Competency to stand trial evaluation for Mr. John Smith, charged with aggravated assault. The court has requested an assessment of his current mental state, ability to understand the charges against him, and capacity to assist in his own defense. Key areas of concern include reported history of bipolar disorder and recent medication non-compliance."
  },
  "settings": {
    "llm_provider": "anthropic",
    "llm_model": "claude-sonnet-4-20250514",
    "output_format": "markdown"
  },
  "paths": {
    "source_documents": "./source_documents/",
    "processed_documents": "./processed_documents/",
    "summaries": "./summaries/",
    "reports": "./reports/"
  },
  "workflow_state": {
    "current_stage": "document_processing",
    "completed_stages": ["project_setup", "document_import"],
    "stage_data": {
      "document_processing": {
        "total_documents": 15,
        "processed_documents": 10,
        "failed_documents": []
      }
    }
  },
  "special_documents": {
    "transcript": "processed_documents/transcript.md",
    "test_results": [
      "processed_documents/MMPI-3.md",
      "processed_documents/TSI-2.md"
    ]
  }
}
```

### Directory Structure

```
case_project/
├── project.frpd                    # Project file
├── source_documents/               # Original PDFs and documents imported from source folder
├── processed_documents/            # Converted markdown files
│   ├── document1.md
│   ├── document1.json             # Metadata for each document
│   └── ...
├── summaries/                      # LLM-generated summaries
│   ├── document1_summary.md
│   ├── integrated_summary.md
│   └── timeline.md
├── reports/                        # Generated reports
│   ├── draft_report.md
│   ├── refined_report.md
│   └── final_report.md
└── logs/                          # Processing logs
    └── processing_log.txt
```

## Workflow Stages

### Stage 0: Settings & Configuration

**UI Component**: Settings Dialog (accessible via menu/toolbar)

1. **User Profile**

   - Evaluator name (auto-populated in new projects)

2. **API Configuration**

   - Secure API key storage using OS keychain:
     - Anthropic API Key
     - Google Gemini API Key
     - Azure OpenAI API Key + Endpoint
   - Test connection button for each provider
   - Visual indicator for configured/unconfigured providers

3. **Default Settings**
   - Default LLM provider and model
   - Default output directory
   - Auto-save interval
   - UI preferences (theme, font size)

### Stage 1: Project Setup

**UI Component**: Project Wizard

1. **New Project**

   - Select project directory
   - Enter case metadata:
     - Case name and number
     - Subject information (name, DOB)
     - Evaluation details:
       - Evaluation date
       - Evaluator name (**pre-populated from settings**, used for transcript interpretation)
     - **Case description** (multiline text field for detailed case background)
   - Choose LLM provider and model
   - Create project structure

2. **Open Existing Project**
   - Browse for .frpd file
   - Load project state
   - Resume from last stage

### Stage 2: Document Import

**UI Component**: Document Manager

1. **Import Documents**

   - Browse for PDF source folder
   - Special document identification (transcript, test results, opposing expert reports)

2. **Document Preview**
   - Simple list view with document info
   - Mark special documents
   - Remove or re-categorize as needed

### Stage 3: Document Processing

**UI Component**: Processing View

1. **Convert to Markdown**

   - Progress bar for batch conversion
   - Error handling with retry options
   - Preview converted documents

2. **Quality Check** (possible future enhancement)cs
   - Side-by-side view of PDF and markdown
   - Edit markdown if needed
   - Mark documents as verified

### Stage 4: Document Analysis

**UI Component**: Analysis View

1. **Generate Summaries**

   - Process documents sequentially
   - Show progress with time estimates
   - Allow pause/resume
   - **Uses case description** from project metadata to provide context to LLM

2. **Create Timeline**

   - Extract dates and events; estimate
   - Generate unified timeline
   - Edit/refine timeline

3. **Integrated Analysis**
   - Combine all summaries
   - Generate comprehensive overview
   - Link back to source documents (PDF and page number)

### Stage 5: Report Generation

**UI Component**: Report Builder

1. **Template Selection**

   - Choose report template
   - Customize sections if needed

2. **Section Generation**

   - Generate each section with LLM
   - Show progress for each section
   - Allow regeneration of specific sections
   - **Case description provides context** for report generation

3. **Special Document Integration**
   - Process test results with specific prompts
   - Integrate transcript quotations
   - Verify accuracy of citations

### Stage 6: Report Refinement

**UI Component**: Report Editor

1. **Initial Refinement**

   - Remove redundancies
   - Verify quotation accuracy
   - Check consistency

2. **Manual Editing**

   - Rich text editor for final adjustments
   - Track changes functionality
   - Comment system for notes

3. **Export Options**
   - Export as markdown
   - Export as PDF
   - Export as Word document

## UI Design Patterns

### Main Window Structure

```
┌─────────────────────────────────────────────────────────┐
│ Forensic Report Drafter - [Project Name]                │
├─────────────────────────────────────────────────────────┤
│ ┌─────────────┬─────────────────────────────────────┐  │
│ │ Progress    │ Main Content Area                   │  │
│ │ Sidebar     │                                     │  │
│ │             │ [Active stage content]              │  │
│ │ ✓ Setup     │                                     │  │
│ │ ✓ Import    │                                     │  │
│ │ ● Process   │                                     │  │
│ │ ○ Analyze   │                                     │  │
│ │ ○ Generate  │                                     │  │
│ │ ○ Refine    │                                     │  │
│ │             │                                     │  │
│ └─────────────┴─────────────────────────────────────┘  │
│ [Previous] [Next] [Save Progress]        Status: Ready  │
└─────────────────────────────────────────────────────────┘
```

### Key UI Components

1. **Progress Sidebar**

   - Visual workflow indicator
   - Click to review completed stages
   - Clear indication of current stage

2. **Main Content Area**

   - Single view at a time
   - Consistent layout across stages
   - Minimal nested components

3. **Navigation Bar**
   - Linear progression with Previous/Next
   - Auto-save on navigation
   - Validation before proceeding

## Technical Implementation

### Secure Storage

1. **OS Keychain Integration**

   ```python
   # Using python-keyring for cross-platform keychain access
   import keyring

   class SecureSettings:
       SERVICE_NAME = "ForensicReportDrafter"

       def set_api_key(self, provider: str, api_key: str):
           """Store API key securely in OS keychain"""
           keyring.set_password(
               self.SERVICE_NAME,
               f"api_key_{provider}",
               api_key
           )

       def get_api_key(self, provider: str) -> str:
           """Retrieve API key from OS keychain"""
           return keyring.get_password(
               self.SERVICE_NAME,
               f"api_key_{provider}"
           )

       def delete_api_key(self, provider: str):
           """Remove API key from keychain"""
           keyring.delete_password(
               self.SERVICE_NAME,
               f"api_key_{provider}"
           )
   ```

2. **Settings File (Non-Sensitive)**
   ```json
   {
     "user_profile": {
       "evaluator_name": "Dr. Jane Doe"
     },
     "defaults": {
       "llm_provider": "anthropic",
       "llm_model": "claude-sonnet-4-20250514",
       "output_directory": "~/Documents/Forensic_Reports",
       "auto_save_interval": 300,
       "ui_theme": "light",
       "font_size": 12
     },
     "provider_config": {
       "azure_openai": {
         "endpoint": "https://myorg.openai.azure.com",
         "deployment_name": "gpt-4.1",
         "api_version": "2025-01-01-preview"
       }
     }
   }
   ```

### State Persistence

1. **Auto-save Project**

   - Save project file on each stage completion
   - Save progress within stages periodically
   - Crash recovery from last save point

2. **Project Manager**

- Create new project
- Open existing projects

### Support Infrastructure

1. **Error Reporting**

   - Automatic crash reports
   - Diagnostic data collection

2. **Documentation**

   - Built-in help system
   - Context-sensitive help

3. **Professional Branding**
   - Custom icon set
   - Splash screen
   - About dialog with license info
   - Professional installer graphics

## First-Time Setup Experience

When users launch the application for the first time:

1. **Welcome Screen**

   - Brief introduction to the application
   - "Get Started" button leading to settings

2. **Initial Configuration**

   - Prompt to enter evaluator information
   - Guide through API key setup with provider selection
   - Test each configured provider
   - Save settings before proceeding

3. **Ready to Use**
   - Settings stored securely
   - No need for .env files
   - API keys in OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service)
   - User profile ready for all new projects

## Packaging and Distribution

### Application Structure for Distribution

1. **Single Executable Package**

   - Use PyInstaller or py2app/py2exe for platform-specific builds
   - Bundle all dependencies including PySide6
   - Include prompt templates as embedded resources
   - Sign executables for trusted distribution

2. **App Preferences Data Locations**

   ```
   # macOS
   ~/Library/Application Support/ForensicReportDrafter/
   ~/Library/Preferences/com.forensicreportdrafter.plist

   # Windows
   %APPDATA%\ForensicReportDrafter\
   %LOCALAPPDATA%\ForensicReportDrafter\

   # Linux
   ~/.config/forensicreportdrafter/
   ~/.local/share/forensicreportdrafter/
   ```
