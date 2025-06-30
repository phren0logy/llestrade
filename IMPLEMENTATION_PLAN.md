# Implementation Plan for Forensic Psych Report Drafter

This document tracks the ongoing refactoring and cleanup of the codebase. It will be continuously updated as we discover more about the project structure and identify areas for improvement.

## 1. LLM Utils Refactoring

### Current State

- `llm_utils.py`: 2,467 lines containing all LLM provider logic
- Mixed responsibilities: providers, chunking, token counting, legacy code
- Contains unused extended thinking and PDF methods

### Target Structure

```
llm/
├── __init__.py              # Clean exports, no backward compatibility
├── base.py                  # Abstract base class following Qt patterns
├── providers/
│   ├── __init__.py
│   ├── anthropic.py         # AnthropicProvider (~400 lines)
│   ├── gemini.py            # GeminiProvider (~350 lines)
│   └── azure_openai.py      # AzureOpenAIProvider (~300 lines)
├── chunking.py              # Markdown-aware chunking with langchain-text-splitters
├── tokens.py                # Token counting utilities
└── factory.py               # Provider factory with Qt-style patterns
```

### Key Design Principles

1. **Follow Qt/PySide6 Patterns**

   - Use `Provider` naming instead of `Client`
   - Implement Qt signals for async operations
   - Use Qt property patterns where appropriate
   - Integrate properly with QThread workers

2. **Clean API Design**

   ```python
   # New clean API
   from llm import create_provider, ChunkingStrategy

   provider = create_provider("anthropic", api_key="...")
   response = provider.generate(prompt, model="claude-3")

   # Markdown-aware chunking
   chunks = ChunkingStrategy.markdown_headers(text, max_tokens=100000)
   ```

3. **Markdown-Aware Chunking**
   - Use langchain-text-splitters for markdown header splitting
   - Respect token limits while preserving document structure
   - Remove character-based estimation in favor of proper token counting

### Implementation Steps

- [x] Create new `llm/` directory structure
- [x] Extract base provider class with Qt patterns
- [x] Move provider-specific code to separate files
- [x] Implement markdown-aware chunking with langchain-text-splitters
- [x] Create unified token counting module
- [x] Create Gemini provider
- [x] Create Azure OpenAI provider
- [x] Create factory module
- [x] Create compatibility shim (llm_utils_compat.py)
- [ ] Update all imports throughout codebase
- [ ] Remove legacy `LLMClient` wrapper from llm_utils.py
- [ ] Update worker threads to use new API
- [ ] Update documentation

## 2. Dependencies Cleanup

### To Remove

- **langchain** - Not used, only langchain-text-splitters needed
- **click** - No CLI interface in this Qt application
- **tqdm** - No progress bars needed (using Qt progress dialogs)

### To Keep

- **langchain-text-splitters** - For markdown-aware text splitting
- All other dependencies are actively used

### Action Items

- [x] Update pyproject.toml to remove unused dependencies using uv remove
- [x] Verify no imports of these libraries remain
- [ ] Run full test suite after removal

**Completed**: Removed langchain, click, and tqdm dependencies on 2025-06-30. Note that sqlalchemy was also removed as it was a dependency of langchain.

## 3. Unused Code Removal

### Confirmed Unused

1. **`docs/sample_code/` directory**
   - Contains a halted Streamlit UI implementation
   - Files: app.py, various page implementations
   - **Action**: ~~Remove entire directory after confirmation~~
   - **Completed**: Removed on 2025-06-30

### Potentially Unused (Need Verification)

1. **Extended thinking methods** in llm_utils.py

   - `generate_response_with_extended_thinking`
   - `generate_response_with_pdf_and_thinking`
   - **Action**: ~~Check if any UI components use these~~
   - **Verified**: These are actively used in refinement_tab.py and pdf_prompt_thread.py - must be kept

2. **Legacy methods**

   - `combine_transcript_with_fragments` function
   - **Action**: ~~Verify no usage before removal~~
   - **Verified**: Used in prompts_tab.py - must be kept

3. **Test/Debug files**
   - Various test files in root directory
   - **Action**: Identify which are active tests vs. one-off debug scripts

### Investigation Needed

- [x] Search for imports from `docs/sample_code/` - None found, directory removed
- [x] Check for usage of extended thinking methods - Actively used, must keep
- [ ] Identify active vs. inactive test files
- [ ] Look for other halted UI attempts

## 4. Qt/PySide6 Best Practices

### Current Issues

1. **Inconsistent signal/slot patterns**

   - Some workers use direct connections
   - Others use queued connections
   - Need standardization

2. **Thread management**

   - Workers should properly clean up
   - Implement consistent error handling
   - Use Qt's thread pool where appropriate

3. **UI component patterns**
   - BaseTab provides good foundation
   - Some tabs don't fully utilize base functionality
   - Status handling could be more consistent

### Target Patterns

1. **Standardized Worker Pattern**

   ```python
   class StandardWorker(QThread):
       # Consistent signals
       started = Signal()
       progress = Signal(int, str)
       result = Signal(object)
       error = Signal(str)
       finished = Signal()
   ```

2. **Consistent Status Management**

   - Use StatusPanel component consistently
   - Implement proper error state handling
   - Clear status on new operations

3. **Property-based State**
   - Use Qt properties for state that affects UI
   - Implement proper change notifications
   - Avoid direct UI manipulation from workers

## 5. Code Quality Improvements

### Naming Conventions

- [ ] Rename "Client" classes to "Provider"
- [ ] Use Qt-style camelCase for Qt methods
- [ ] Use Python snake_case for non-Qt methods

### Error Handling

- [ ] Implement consistent error types
- [ ] Use Qt's logging framework
- [ ] Proper exception propagation in workers

### Documentation

- [ ] Update CLAUDE.md with new structure
- [ ] Add docstrings to all public methods
- [ ] Create architecture diagram

## 6. Testing Strategy

### Unit Tests

- [ ] Test each provider independently
- [ ] Test chunking strategies
- [ ] Test token counting accuracy

### Integration Tests

- [ ] Test worker thread integration
- [ ] Test signal/slot connections
- [ ] Test error propagation

### UI Tests

- [ ] Test tab switching and state
- [ ] Test file selection workflows
- [ ] Test progress indication

## 7. Migration Path

### Phase 1: Preparation

1. Create new directory structure
2. Write comprehensive tests for current functionality
3. Document all current API usage

### Phase 2: Implementation

1. Implement new modules with tests
2. Create compatibility shim if needed
3. Update one component at a time

### Phase 3: Cleanup

1. Remove old code
2. Remove unused dependencies
3. Update all documentation

## 8. Open Questions

### For Investigation

1. Is the Azure Document Intelligence integration (`azure_processing_thread.py`) actively used?
2. Are there any external tools depending on the current API?
3. Which test files are part of the test suite vs. one-off experiments?
4. Is the "testing_tab.py" a development tool or unused code?

### Design Decisions Needed

1. Should we implement a plugin system for providers?
2. How should we handle provider-specific features (e.g., Anthropic's PDF support)?
3. Should chunking strategies be pluggable?

## 9. Current Issues

### Critical Bug: Memory Corruption in llm_summary_thread.py

**Error**: `malloc: *** error for object 0x811e86130: pointer being freed was not allocated`

**Location**: ui/workers/llm_summary_thread.py, lines 704-705

```python
del chunk_content
del chunk_prompt
```

**Problem**: The code is explicitly deleting variables that may still be referenced by Python's memory management system. This causes a double-free error when Python's garbage collector tries to free the same memory.

**Solution**: Remove the explicit `del` statements. Python's garbage collection will handle memory management automatically. The `gc.collect()` call is sufficient to encourage garbage collection.

**Action Items**:

- [x] Remove `del chunk_content` and `del chunk_prompt` statements
- [x] Keep only `gc.collect()` if memory management is a concern
- [ ] Test thoroughly with Azure OpenAI to ensure fix works

**Fix Applied**: Removed explicit `del` statements on 2025-06-30. The code now relies on Python's automatic garbage collection with an explicit `gc.collect()` call to encourage memory cleanup between chunks.

## 10. Progress Tracking

### Completed

- [x] Initial codebase analysis
- [x] Identified unused dependencies
- [x] Created refactoring plan
- [x] Created IMPLEMENTATION_PLAN.md
- [x] Fixed memory corruption bug
- [x] Removed unused dependencies (langchain, click, tqdm)
- [x] Removed unused docs/sample_code directory
- [x] Created new llm/ directory structure
- [x] Created base provider class with Qt patterns
- [x] Created chunking module with langchain-text-splitters
- [x] Created token counting module
- [x] Created Anthropic provider
- [x] Created Gemini provider  
- [x] Created Azure OpenAI provider
- [x] Created factory module
- [x] Created compatibility shim for migration
- [x] Updated critical imports to use compatibility module (app_config.py, llm_summary_thread.py, integrated_analysis_thread.py, prompt_runner_thread.py, pdf_prompt_thread.py, refinement_tab.py, analysis_tab.py, prompts_tab.py)

### In Progress

- [ ] Updating remaining imports (tests, debug scripts)
- [ ] Investigating remaining unused code

### Not Started

- [ ] Update all imports throughout codebase
- [ ] Remove legacy LLMClient wrapper
- [ ] Update worker threads to use new API
- [ ] Testing updates
- [ ] Documentation updates

---

_Last Updated: 2025-06-30_
_Next Review: After completing import updates_
