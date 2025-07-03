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
    "evaluator": "Dr. Jane Doe"
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

### Stage 1: Project Setup
**UI Component**: Project Wizard

1. **New Project**
   - Select project directory
   - Enter case metadata
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

## Next Steps

1. Review and refine this workflow design
2. Create mockups for each stage
3. Implement proof-of-concept for Stage 1 (Project Setup)
4. Test memory usage patterns with simplified architecture