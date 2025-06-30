# Migration Plan: Removing the Compatibility Module

This document outlines the plan to migrate from `llm_utils_compat.py` to direct usage of the new `llm/` package.

## Overview

The compatibility module (`llm_utils_compat.py`) was created as a temporary bridge to allow gradual migration from the monolithic `llm_utils.py` to the new modular `llm/` package. Now that all imports have been updated to use the compatibility module, we can plan the final migration.

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

## API Mapping

### Factory Pattern
```python
# Old API (compatibility)
from llm_utils_compat import LLMClientFactory
client = LLMClientFactory.create_client(provider="anthropic")

# New API
from llm.factory import create_provider
provider = create_provider("anthropic", api_key="...")
```

### Response Generation
```python
# Old API
response = client.generate_response(
    prompt_text="...",
    temperature=0.7
)

# New API
response = provider.generate(
    prompt="...",
    temperature=0.7
)
# or async
response = await provider.generate_async(...)
```

### Token Counting
```python
# Old API
from llm_utils_compat import cached_count_tokens
count = cached_count_tokens(client, text="...")

# New API
from llm.tokens import count_tokens_cached
count = count_tokens_cached(provider, text="...")
```

### Chunking
```python
# Old API
from llm_utils_compat import chunk_document_with_overlap
chunks = chunk_document_with_overlap(doc, max_tokens, overlap)

# New API
from llm.chunking import chunk_document
chunks = chunk_document(doc, max_tokens=..., overlap_tokens=...)
```

## Benefits of Direct Migration

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

## Implementation Steps

1. **Create feature branch** for migration
2. **Update one component at a time**
3. **Test thoroughly** after each component
4. **Update tests** to match new API
5. **Remove compatibility module**
6. **Remove old llm_utils.py**
7. **Update documentation**

## Risk Mitigation

- Keep compatibility module until all components migrated
- Test each component thoroughly
- Can rollback individual components if issues arise
- Maintain backward compatibility in `llm/` package during migration

## Timeline Estimate

- Phase 1: 2-3 hours (critical components)
- Phase 2: 2-3 hours (UI components)
- Phase 3: 1 hour (utility scripts)
- Phase 4: 2 hours (tests)
- Total: ~8-10 hours of focused work

## Success Criteria

- All tests pass with new API
- Application runs without compatibility module
- No imports from `llm_utils` or `llm_utils_compat`
- Documentation updated
- Clean codebase with single LLM implementation