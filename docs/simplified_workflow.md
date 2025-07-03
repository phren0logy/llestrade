# Simplified Forensic Report Drafter Workflow

## Overview

This document outlines a simplified, project-based workflow for the Forensic Report Drafter application. The new design addresses memory management issues, reduces UI complexity, and provides a more intuitive user experience through a linear, wizard-style interface.

## Core Principles

1. **Project-Based Organization**: All work happens within isolated project contexts
2. **Linear Workflow**: Guide users through a clear sequence of steps
3. **Single Active View**: Only one major UI component active at a time
4. **Lazy Resource Loading**: Load resources only when needed
5. **Clear State Management**: Explicit project state with automatic saves

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
    "evaluation_date": "2025-06-15",
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
      "processed_documents/MMPI-2.md",
      "processed_documents/WAIS-IV.md"
    ]
  }
}
```

### Directory Structure

```
case_project/
├── project.frpd                    # Project file
├── source_documents/               # Original PDFs and documents
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
   - Professional title
   - License number (optional)
   - Contact information (optional)

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
       - Evaluator name (**pre-populated from settings**)
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
   - Drag-and-drop or browse for PDFs
   - Automatic categorization suggestions
   - Special document identification (transcript, test results)

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

2. **Quality Check**
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
   - Extract dates and events
   - Generate unified timeline
   - Edit/refine timeline

3. **Integrated Analysis**
   - Combine all summaries
   - Generate comprehensive overview
   - Link back to source documents

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

### Memory Management

1. **Single Active Worker**
   - Only one QThread active at a time
   - Proper cleanup between operations
   - Clear parent-child relationships

2. **Resource Cleanup**
   ```python
   def cleanup_stage(self):
       # Stop any active threads
       if self.active_thread:
           self.active_thread.quit()
           self.active_thread.wait()
           self.active_thread.deleteLater()
           self.active_thread = None
       
       # Clear UI components
       self.clear_content_area()
       
       # Force garbage collection
       import gc
       gc.collect()
   ```

3. **Lazy Loading**
   ```python
   def load_stage(self, stage_name):
       # Cleanup previous stage
       self.cleanup_stage()
       
       # Load only required components
       if stage_name == "document_processing":
           self.content_widget = DocumentProcessingWidget()
       elif stage_name == "analysis":
           self.content_widget = AnalysisWidget()
       # etc...
   ```

### Thread Management

1. **Sequential Processing**
   - Process documents one at a time
   - Clear feedback on progress
   - Ability to pause/resume

2. **Signal Management**
   ```python
   class StageWorker(QThread):
       progress = Signal(int, str)  # percent, message
       finished = Signal(dict)      # results
       error = Signal(str)          # error message
       
       def __init__(self, project_data):
           super().__init__()
           self.project_data = project_data
           self._is_running = True
       
       def stop(self):
           self._is_running = False
   ```

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
       "evaluator_name": "Dr. Jane Doe",
       "professional_title": "Licensed Forensic Psychologist",
       "license_number": "PSY-12345",
       "contact_email": "jane.doe@example.com"
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
   ```python
   class ProjectManager:
       def __init__(self, project_path):
           self.project_path = project_path
           self.load_or_create_project()
       
       def save_state(self):
           # Atomic write with temporary file
           temp_path = self.project_path + ".tmp"
           with open(temp_path, 'w') as f:
               json.dump(self.project_data, f, indent=2)
           os.replace(temp_path, self.project_path)
       
       def update_stage_progress(self, stage, data):
           self.project_data['workflow_state']['stage_data'][stage] = data
           self.save_state()
   ```

## Migration Path

### Phase 1: Core Infrastructure
1. Implement project file format and manager
2. Create base UI framework with stage navigation
3. Implement memory cleanup patterns
4. Add secure settings storage:
   - Install `python-keyring` dependency
   - Implement SecureSettings class
   - Create settings UI dialog
   - First-time setup flow

### Phase 2: Feature Migration
1. Migrate PDF processing functionality
2. Migrate document analysis features
3. Migrate report generation

### Phase 3: UI Polish
1. Add progress indicators and time estimates
2. Implement pause/resume functionality
3. Add keyboard shortcuts and accessibility

### Phase 4: Testing and Optimization
1. Memory leak testing
2. Performance profiling
3. User acceptance testing

## Professional Deployment Considerations

### Enterprise Features

1. **Network Deployment**
   - MSI installer for Group Policy deployment
   - Silent install options
   - Centralized configuration management
   - Proxy support for API calls

2. **Compliance Features**
   - Audit logging for all operations
   - HIPAA compliance considerations
   - Data retention policies
   - Encrypted local storage option

3. **Multi-User Support**
   - User profiles with separate settings
   - Shared prompt template library
   - Role-based access (future)
   - Collaborative review features (future)

### Support Infrastructure

1. **Error Reporting**
   - Automatic crash reports (opt-in)
   - Diagnostic data collection
   - Remote debugging capability
   - Support ticket integration

2. **Documentation**
   - Built-in help system
   - Video tutorials
   - PDF user manual
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

## Benefits of This Approach

1. **Reduced Memory Footprint**
   - Only one major component active at a time
   - Clear resource cleanup between stages
   - No complex widget hierarchies

2. **Improved User Experience**
   - Clear, linear workflow
   - Obvious progress tracking
   - Easy to understand where you are

3. **Better Error Recovery**
   - Project state saved frequently
   - Can resume from any stage
   - Failed operations don't affect other stages

4. **Simplified Maintenance**
   - Each stage is independent
   - Easier to test individual components
   - Clear separation of concerns

## Packaging and Distribution

### Application Structure for Distribution

1. **Single Executable Package**
   - Use PyInstaller or py2app/py2exe for platform-specific builds
   - Bundle all dependencies including PySide6
   - Include prompt templates as embedded resources
   - Sign executables for trusted distribution

2. **Directory Layout (Installed)**
   ```
   ForensicReportDrafter.app/ (macOS) or ForensicReportDrafter/ (Windows/Linux)
   ├── executable
   ├── resources/
   │   ├── prompt_templates/
   │   ├── icons/
   │   └── default_settings.json
   ├── lib/ (bundled Python libraries)
   └── README.txt
   ```

3. **User Data Locations**
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

### Build Configuration

1. **PyInstaller Spec File**
   ```python
   # forensic_report_drafter.spec
   a = Analysis(
       ['main.py'],
       pathex=[],
       binaries=[],
       datas=[
           ('prompt_templates', 'prompt_templates'),
           ('resources', 'resources'),
       ],
       hiddenimports=[
           'tiktoken',
           'keyring.backends',
           'llm.providers.anthropic',
           'llm.providers.gemini',
           'llm.providers.azure_openai',
       ],
       hookspath=[],
       hooksconfig={},
       runtime_hooks=[],
       excludes=['tkinter'],
       win_no_prefer_redirects=False,
       win_private_assemblies=False,
       cipher=None,
       noarchive=False,
   )
   ```

2. **Platform-Specific Considerations**
   - **macOS**: 
     - Code signing with Developer ID
     - Notarization for Gatekeeper
     - DMG installer with drag-to-Applications
   - **Windows**:
     - Code signing certificate
     - NSIS or WiX installer
     - Auto-update capability
   - **Linux**:
     - AppImage for universal compatibility
     - Snap or Flatpak packages
     - .deb/.rpm for specific distributions

### Installation Experience

1. **First Launch**
   ```
   ┌─────────────────────────────────────────┐
   │   Welcome to Forensic Report Drafter    │
   │                                         │
   │   Version 1.0.0                         │
   │                                         │
   │   This appears to be your first time    │
   │   using the application.                │
   │                                         │
   │   [Get Started]  [Import Settings]      │
   └─────────────────────────────────────────┘
   ```

2. **Auto-Update System**
   - Check for updates on startup (configurable)
   - Download updates in background
   - Apply updates on next restart
   - Rollback capability for failed updates

### Development Workflow for Distribution

1. **Version Management**
   ```python
   # src/version.py
   VERSION = "1.0.0"
   BUILD_DATE = "2025-07-03"
   UPDATE_URL = "https://api.forensicreportdrafter.com/updates"
   ```

2. **Resource Management**
   ```python
   # src/resources.py
   import sys
   from pathlib import Path
   
   def get_resource_path(relative_path):
       """Get absolute path to resource, works for dev and PyInstaller"""
       if hasattr(sys, '_MEIPASS'):
           # PyInstaller creates a temp folder and stores path in _MEIPASS
           return Path(sys._MEIPASS) / relative_path
       return Path(__file__).parent.parent / relative_path
   ```

3. **Settings Migration**
   ```python
   # src/settings_migrator.py
   class SettingsMigrator:
       def migrate_from_env(self):
           """One-time migration from .env to secure storage"""
           if os.path.exists('.env'):
               # Read old settings
               # Transfer to keychain
               # Archive .env file
   ```

### Testing Distribution Builds

1. **Build Matrix**
   - macOS: 12.0+ (Universal binary for Intel/Apple Silicon)
   - Windows: 10/11 (64-bit)
   - Linux: Ubuntu 20.04+ (AppImage)

2. **Test Scenarios**
   - Fresh install
   - Upgrade from previous version
   - Settings migration
   - Offline operation
   - Antivirus compatibility

### Dependencies and Licensing

1. **Dependency Management**
   ```toml
   # pyproject.toml
   [project]
   name = "forensic-report-drafter"
   version = "1.0.0"
   dependencies = [
       "PySide6>=6.5.0",
       "anthropic>=0.20.0",
       "google-generativeai>=0.3.0",
       "openai>=1.0.0",
       "python-keyring>=24.0.0",
       "pypdf>=3.0.0",
       "python-docx>=0.8.0",
       "psutil>=5.9.0",
   ]
   
   [project.optional-dependencies]
   dev = ["pytest", "black", "ruff", "pyinstaller"]
   ```

2. **License Compliance**
   - PySide6: LGPL (dynamic linking OK)
   - All dependencies: MIT/Apache/BSD compatible
   - Application license: TBD (proprietary or open source)
   - Include licenses.txt in distribution

3. **Binary Size Optimization**
   - Exclude unnecessary modules
   - Compress with UPX (optional)
   - Lazy load heavy dependencies
   - Target size: <150MB per platform

### Release Process

1. **Continuous Integration**
   ```yaml
   # .github/workflows/build.yml
   - Build executables for each platform
   - Run integration tests
   - Sign binaries
   - Create installers
   - Upload to release server
   ```

2. **Release Checklist**
   - [ ] Version bump in all files
   - [ ] Update changelog
   - [ ] Build all platforms
   - [ ] Test installers
   - [ ] Sign and notarize
   - [ ] Update documentation
   - [ ] Publish release

## Next Steps

1. Review and refine this workflow design
2. Create mockups for each stage
3. Implement proof-of-concept for Stage 1 (Project Setup)
4. Test memory usage patterns with simplified architecture
5. Set up build automation for distribution