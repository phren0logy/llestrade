# Migration Plan: Removing the Compatibility Module

This document provides the complete plan and guide for migrating from `llm_utils_compat.py` to direct usage of the new `llm/` package.

## Table of Contents
1. [Overview](#overview)
2. [Current State](#current-state)
3. [Migration Strategy](#migration-strategy)
4. [API Changes Reference](#api-changes-reference)
5. [Component-by-Component Migration](#component-by-component-migration)
6. [Testing Strategy](#testing-strategy)
7. [Common Pitfalls](#common-pitfalls)
8. [Implementation Steps](#implementation-steps)
9. [Timeline and Success Criteria](#timeline-and-success-criteria)

## Overview

The compatibility module (`llm_utils_compat.py`) was created as a temporary bridge to allow gradual migration from the monolithic `llm_utils.py` to the new modular `llm/` package. Now that all imports have been updated to use the compatibility module, we can plan the final migration.

### What's Changing
- Moving from `llm_utils_compat` imports to direct `llm/` package imports
- Changing from "client" terminology to "provider" terminology
- Updating method names to match the new API
- Leveraging Qt integration features

### Migration Principles
1. **One component at a time** - Don't try to migrate everything at once
2. **Test before and after** - Ensure functionality remains the same
3. **Use the compatibility layer** - Keep it available until all migrations complete
4. **Document changes** - Update docstrings and comments

## Current State

- All imports use `llm_utils_compat` 
- The compatibility module wraps the new `llm/` package with the old API
- No code directly imports from `llm_utils.py`
- The new `llm/` package is fully functional

## Migration Strategy

### Phase 1: Update Critical Components (High Priority)

These components are central to the application and should be migrated first:

1. **app_config.py**
   - Current: `from llm_utils_compat import LLMClientFactory`
   - Target: `from llm.factory import create_provider`
   - Changes needed:
     - Update `get_configured_llm_client()` to use `create_provider()`
     - Return provider instance instead of wrapped client

2. **Worker Threads** (ui/workers/)
   - **llm_summary_thread.py**
     - Current: Uses `LLMClientFactory.create_client()`
     - Target: Use `create_provider()` directly
     - Benefit: Can use Qt signals from providers
   
   - **integrated_analysis_thread.py**
     - Current: Uses compatibility layer
     - Target: Direct provider usage with native extended thinking
   
   - **prompt_runner_thread.py**
     - Current: Simple usage pattern
     - Target: Straightforward migration

### Phase 2: Update UI Components (Medium Priority)

3. **analysis_tab.py**
   - Uses `cached_count_tokens` - migrate to `from llm.tokens import count_tokens_cached`
   
4. **refinement_tab.py**
   - Uses extended thinking features
   - Migrate to direct provider methods

5. **prompts_tab.py**
   - Uses `combine_transcript_with_fragments`
   - This function needs to be moved to a utilities module

### Phase 3: Update Utility Scripts (Low Priority)

6. **main.py**
   - Minimal usage, easy migration
   
7. **setup_env.py**
   - Test scripts that verify connectivity

### Phase 4: Update Tests

8. All test files in `tests/` directory
   - Update imports and API usage
   - Ensure tests still pass

## API Changes Reference

### Import Changes

```python
# OLD
from llm_utils_compat import (
    LLMClientFactory,
    BaseLLMClient,
    AnthropicClient,
    GeminiClient,
    AzureOpenAIClient,
    cached_count_tokens,
    chunk_document_with_overlap,
    combine_transcript_with_fragments
)

# NEW
from llm.factory import create_provider
from llm.base import BaseLLMProvider
from llm.providers import AnthropicProvider, GeminiProvider, AzureOpenAIProvider
from llm.tokens import count_tokens_cached
from llm.chunking import chunk_document
# combine_transcript_with_fragments should be moved to a utilities module
```

### Factory Pattern Changes

```python
# OLD
client = LLMClientFactory.create_client(
    provider="anthropic",
    api_key="...",
    timeout=60.0,
    max_retries=3
)

# NEW
provider = create_provider(
    provider="anthropic",
    api_key="...",
    timeout=60.0,
    max_retries=3
)
```

### Property Changes

```python
# OLD
if client.is_initialized:
    # do something

# NEW
if provider.initialized:
    # do something
```

### Method Name Changes

#### Basic Generation
```python
# OLD
response = client.generate_response(
    prompt_text="...",
    system_prompt="...",
    model="claude-3",
    temperature=0.7,
    max_tokens=1000
)

# NEW
response = provider.generate(
    prompt="...",  # Note: renamed from prompt_text
    system_prompt="...",
    model="claude-3",
    temperature=0.7,
    max_tokens=1000
)
```

#### Extended Thinking
```python
# OLD
response = client.generate_response_with_extended_thinking(
    prompt_text="...",
    thinking_budget_tokens=32000,
    model="..."
)

# NEW
response = provider.generate_with_extended_thinking(
    prompt="...",  # Note: renamed from prompt_text
    thinking_budget_tokens=32000,
    model="..."
)
```

#### PDF Processing (Anthropic only)
```python
# OLD
response = client.generate_response_with_pdf_and_thinking(
    prompt_text="...",
    pdf_file_path="...",
    thinking_budget_tokens=32000
)

# NEW
response = provider.generate_with_pdf_and_thinking(
    prompt="...",  # Note: renamed from prompt_text
    pdf_file_path="...",
    thinking_budget_tokens=32000
)
```

#### Token Counting
```python
# OLD
from llm_utils_compat import cached_count_tokens
result = cached_count_tokens(client, text="...")
token_count = result["token_count"]

# NEW
from llm.tokens import count_tokens_cached
result = count_tokens_cached(provider, text="...")
token_count = result["token_count"]
```

#### Document Chunking
```python
# OLD
from llm_utils_compat import chunk_document_with_overlap
chunks = chunk_document_with_overlap(
    document=text,
    max_tokens_per_chunk=100000,
    overlap_tokens=2000
)

# NEW
from llm.chunking import chunk_document
chunks = chunk_document(
    text=text,  # Note: renamed from document
    max_tokens=100000,  # Note: renamed from max_tokens_per_chunk
    overlap_tokens=2000
)
```

### Response Format
The response format remains the same:
```python
{
    "success": bool,
    "content": str,  # The generated content
    "error": str,    # Error message if success=False
    "usage": {       # Token usage information
        "input_tokens": int,
        "output_tokens": int,
        "total_tokens": int
    },
    "model": str,    # Model used
    "provider": str  # Provider name
}
```

## Component-by-Component Migration

### Phase 1: Critical Components

#### 1. app_config.py
**Status**: ✅ Completed (see app_config_migrated.py)

**Key Changes**:
```python
# Import changes
from llm.factory import create_provider
from llm.base import BaseLLMProvider

# Function rename
get_configured_llm_client() → get_configured_llm_provider()

# Return value change
return {"client": client, ...} → return {"provider": provider, ...}

# Property check
if client.is_initialized → if provider.initialized
```

**Backward Compatibility**:
- Keep alias: `get_configured_llm_client = get_configured_llm_provider`

#### 2. llm_summary_thread.py (ui/workers/)

**Current Usage**:
- Creates client with `LLMClientFactory.create_client()`
- Uses `generate_response()` for summarization
- Uses `cached_count_tokens()` for token counting
- Chunks documents for processing

**Migration Steps**:
```python
# 1. Update imports
from llm.factory import create_provider
from llm.tokens import count_tokens_cached
from llm.chunking import chunk_document

# 2. Update client creation
# OLD
self.llm_client = LLMClientFactory.create_client(provider="auto")

# NEW
self.llm_provider = create_provider(provider="auto")

# 3. Update method calls
# OLD
response = self.llm_client.generate_response(
    prompt_text=prompt,
    system_prompt=system_prompt,
    temperature=0.1
)

# NEW
response = self.llm_provider.generate(
    prompt=prompt,
    system_prompt=system_prompt,
    temperature=0.1
)

# 4. Update token counting
# OLD
token_result = cached_count_tokens(self.llm_client, text=document_content)

# NEW
token_result = count_tokens_cached(self.llm_provider, text=document_content)

# 5. Update chunking
# OLD
chunks = chunk_document_with_overlap(
    document=document_content,
    max_tokens_per_chunk=max_tokens,
    overlap_tokens=2000
)

# NEW
chunks = chunk_document(
    text=document_content,
    max_tokens=max_tokens,
    overlap_tokens=2000
)
```

#### 3. integrated_analysis_thread.py (ui/workers/)

**Special Considerations**:
- Uses Gemini's extended thinking feature
- Must preserve the extended thinking functionality

**Migration Steps**:
```python
# 1. Update imports
from llm.factory import create_provider
from llm.tokens import count_tokens_cached

# 2. Ensure Gemini provider for extended thinking
# OLD
self.llm_client = LLMClientFactory.create_client(provider="gemini")

# NEW
self.llm_provider = create_provider(provider="gemini")

# 3. Update extended thinking call
# OLD
response = self.llm_client.generate_response_with_extended_thinking(
    prompt_text=prompt,
    model="gemini-2.0-flash-thinking-exp-1219",
    thinking_budget_tokens=8192
)

# NEW
response = self.llm_provider.generate_with_extended_thinking(
    prompt=prompt,
    model="gemini-2.0-flash-thinking-exp-1219",
    thinking_budget_tokens=8192
)
```

#### 4. prompt_runner_thread.py (ui/workers/)

**Current Usage**:
- Simple usage pattern
- Only uses basic generation

**Migration Steps**:
```python
# 1. Update imports
from llm.factory import create_provider

# 2. Update client creation
# OLD
self.llm_client = LLMClientFactory.create_client(provider="auto")

# NEW
self.llm_provider = create_provider(provider="auto")

# 3. Update generation call
# OLD
response = self.llm_client.generate_response(
    prompt_text=prompt["content"],
    temperature=0.1
)

# NEW
response = self.llm_provider.generate(
    prompt=prompt["content"],
    temperature=0.1
)
```

### Phase 2: UI Components

#### 5. analysis_tab.py

**Current Usage**:
- Uses `cached_count_tokens` for token counting
- Uses `LLMClientFactory` indirectly through app_config

**Migration Steps**:
```python
# 1. Update imports
from llm.tokens import count_tokens_cached

# 2. Update any direct token counting
# OLD
from llm_utils_compat import cached_count_tokens
count = cached_count_tokens(client, text=content)

# NEW
from llm.tokens import count_tokens_cached
count = count_tokens_cached(provider, text=content)

# 3. Update app_config usage
# The app_config module should already be migrated
# Just ensure you're using the new get_configured_llm_provider()
```

#### 6. refinement_tab.py

**Current Usage**:
- Uses extended thinking features
- Creates refinement thread that uses LLM

**Migration Steps**:
```python
# 1. Update refinement thread creation
# The RefinementThread class needs to be updated similarly to other workers

# 2. In RefinementThread class:
from llm.factory import create_provider

# OLD
llm_client = LLMClientFactory.create_client(
    provider="auto",
    timeout=DEFAULT_TIMEOUT * 10,
    max_retries=3,
    thinking_budget_tokens=32000
)

# NEW
llm_provider = create_provider(
    provider="auto",
    timeout=DEFAULT_TIMEOUT * 10,
    max_retries=3
)

# 3. Update extended thinking call
# OLD
response = llm_client.generate_response_with_extended_thinking(
    prompt_text=prompt,
    model="claude-3-7-sonnet-20250219",
    max_tokens=64000,
    thinking_budget_tokens=32000
)

# NEW
response = llm_provider.generate_with_extended_thinking(
    prompt=prompt,
    model="claude-3-7-sonnet-20250219",
    max_tokens=64000,
    thinking_budget_tokens=32000
)
```

#### 7. prompts_tab.py

**Current Usage**:
- Uses `combine_transcript_with_fragments` function
- May use LLM for prompt testing

**Migration Steps**:
```python
# 1. Move combine_transcript_with_fragments to a utility module
# Create utils/prompt_utils.py:
def combine_transcript_with_fragments(transcript_text: str, fragment: str) -> str:
    """Combine transcript text with a template fragment."""
    combined = f"{fragment}\n\n<transcript>\n{transcript_text}\n</transcript>"
    return combined

# 2. Update import
from utils.prompt_utils import combine_transcript_with_fragments
```

### Phase 3: Utility Scripts

#### 8. main.py

**Current Usage**:
- Uses `LLMClientFactory` and `cached_count_tokens` for API key checking

**Migration Steps**:
```python
# 1. Update imports (with deprecation suppression)
import warnings
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from llm.factory import create_provider
    from llm.tokens import count_tokens_cached

# 2. Update check_api_key method
def check_api_key(self, provider="auto"):
    """Check if the API key is valid by making a test request."""
    try:
        # Create provider
        provider_instance = create_provider(provider=provider)
        
        # Simple test with token counting
        response = count_tokens_cached(provider_instance, text="Test connection")
        
        if response.get("success", False):
            provider_name = provider_instance.__class__.__name__.replace("Provider", "")
            self.status_bar.showMessage(
                f"{provider_name} API key found. Ready to use.", 5000
            )
```

#### 9. setup_env.py

**Current Usage**:
- Tests API connectivity
- Uses `LLMClientFactory` for testing

**Migration Steps**:
```python
# 1. Update imports
from llm.factory import create_provider

# 2. Update test_api_connectivity
# OLD
client = LLMClientFactory.create_client(provider="auto")

# NEW  
provider = create_provider(provider="auto")

# 3. Update API calls
# OLD
response = client.count_tokens(text="Test message")

# NEW
response = provider.count_tokens(text="Test message")
```

### Phase 4: Test Files

#### General Test File Updates

All test files follow the same pattern:

```python
# 1. Update imports
# OLD
from llm_utils_compat import LLMClientFactory, GeminiClient, AnthropicClient

# NEW
from llm.factory import create_provider
from llm.providers import GeminiProvider, AnthropicProvider

# 2. Update client creation
# OLD
client = LLMClientFactory.create_client(provider="gemini")

# NEW
provider = create_provider(provider="gemini")

# 3. Update assertions
# OLD
assert isinstance(client, GeminiClient)
assert client.is_initialized

# NEW
assert isinstance(provider, GeminiProvider)
assert provider.initialized

# 4. Update method calls
# OLD
response = client.generate_response(prompt_text="test")

# NEW
response = provider.generate(prompt="test")
```

## Testing Strategy

### 1. Pre-Migration Testing
Before migrating each component:
```bash
# Run existing tests to ensure they pass
uv run pytest tests/

# Create a baseline output for comparison
uv run python component_to_migrate.py > baseline_output.txt
```

### 2. Create Migration Test
For each component, create a test that verifies both old and new versions work:

```python
# test_migration_component.py
def test_component_migration():
    # Test old version
    old_result = old_component_function()
    
    # Test new version
    new_result = new_component_function()
    
    # Compare results
    assert old_result == new_result
```

### 3. Post-Migration Testing
After migration:
```bash
# Run the migration test
uv run python test_migration_component.py

# Run full test suite
uv run pytest tests/

# Compare output with baseline
uv run python component_migrated.py > new_output.txt
diff baseline_output.txt new_output.txt
```

### 4. Integration Testing
Test the full application flow:
```bash
# Start the application
uv run main.py

# Test each major workflow:
# 1. Document summarization
# 2. PDF processing
# 3. Report refinement
# 4. Integrated analysis
```

## Common Pitfalls

### 1. Attribute Name Differences
```python
# WRONG
if provider.is_initialized:  # This will fail!

# CORRECT
if provider.initialized:
```

### 2. Method Parameter Names
```python
# WRONG
provider.generate(prompt_text="...")  # This will fail!

# CORRECT
provider.generate(prompt="...")
```

### 3. Missing Imports
```python
# Don't forget to update ALL imports in a file
# Check for:
- Direct imports at the top
- Imports inside functions
- Conditional imports
- Type hint imports
```

### 4. Thread Safety
```python
# The new providers are QObject-based and thread-safe
# But still create providers in the thread that will use them
class WorkerThread(QThread):
    def run(self):
        # Create provider in the thread
        self.provider = create_provider(provider="auto")
```

### 5. Error Handling
```python
# The response format is the same, but check for provider-specific errors
response = provider.generate(prompt="...")
if not response["success"]:
    # Handle error - check response["error"] for details
    # Provider-specific errors may have different messages
```

## Implementation Steps

1. **Create feature branch** for migration
2. **Update one component at a time**
3. **Test thoroughly** after each component
4. **Update tests** to match new API
5. **Remove compatibility module**
6. **Remove old llm_utils.py**
7. **Update documentation**

### Risk Mitigation

- Keep compatibility module until all components migrated
- Test each component thoroughly
- Can rollback individual components if issues arise
- Maintain backward compatibility in `llm/` package during migration

### Rollback Plan

If issues arise during migration:

#### 1. Individual Component Rollback
```bash
# Restore original file
git checkout -- path/to/component.py

# Or use backup
cp component_backup.py component.py
```

#### 2. Full Rollback
```bash
# Revert to compatibility module usage
git checkout migration-start-commit -- .

# Ensure compatibility module is still available
ls llm_utils_compat.py
```

#### 3. Partial Rollback
You can run with mixed usage:
- Some components using new `llm/` package
- Others still using `llm_utils_compat`

This is possible because the compatibility module wraps the new package.

## Timeline and Success Criteria

### Timeline Estimate

- Phase 1: 2-3 hours (critical components)
- Phase 2: 2-3 hours (UI components)
- Phase 3: 1 hour (utility scripts)
- Phase 4: 2 hours (tests)
- Total: ~8-10 hours of focused work

### Success Criteria

The migration is successful when:
1. All tests pass with new API
2. Application runs without compatibility module
3. No imports from `llm_utils` or `llm_utils_compat`
4. Documentation updated
5. Clean codebase with single LLM implementation

### Benefits of Direct Migration

1. **Better Qt Integration**
   - Providers emit Qt signals directly
   - No wrapper overhead
   - Better thread safety

2. **Cleaner API**
   - More pythonic naming
   - Async support where needed
   - Type hints throughout

3. **Performance**
   - Remove wrapper layer
   - Direct method calls
   - Less memory usage

4. **Maintainability**
   - Single source of truth
   - Easier debugging
   - Clear architecture

## Migration Checklist

### Pre-Migration
- [ ] Create feature branch: `git checkout -b feature/remove-compatibility-module`
- [ ] Run full test suite and save results
- [ ] Create backups of files to be modified
- [ ] Review this guide completely

### Phase 1: Critical Components
- [ ] Migrate app_config.py
- [ ] Test app_config migration
- [ ] Migrate llm_summary_thread.py
- [ ] Test summarization workflow
- [ ] Migrate integrated_analysis_thread.py
- [ ] Test integrated analysis workflow
- [ ] Migrate prompt_runner_thread.py
- [ ] Test prompt runner workflow

### Phase 2: UI Components
- [ ] Migrate analysis_tab.py
- [ ] Migrate refinement_tab.py
- [ ] Migrate prompts_tab.py
- [ ] Create prompt_utils.py for shared functions
- [ ] Test all UI workflows

### Phase 3: Utility Scripts
- [ ] Migrate main.py
- [ ] Migrate setup_env.py
- [ ] Test application startup
- [ ] Test environment setup

### Phase 4: Test Files
- [ ] Update all test files
- [ ] Run full test suite
- [ ] Fix any failing tests

### Post-Migration
- [ ] Remove llm_utils_compat.py
- [ ] Remove llm_utils.py
- [ ] Update all documentation
- [ ] Create PR with detailed changelog
- [ ] Merge after review

## Notes for Future Maintenance

### Adding New Providers
With the new structure, adding providers is easier:
1. Create new provider in `llm/providers/`
2. Inherit from `BaseLLMProvider`
3. Implement required methods
4. Add to factory in `llm/factory.py`

### Extending Functionality
The new structure supports:
- Async methods (use `generate_async`)
- Qt signals for progress updates
- Provider-specific features
- Easy testing and mocking

### Performance Considerations
The new structure has:
- Less overhead (no wrapper layer)
- Better memory usage
- Cleaner thread handling
- More efficient token counting cache