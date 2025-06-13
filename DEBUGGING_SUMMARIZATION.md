# Debugging LLM Summarization Issues

## The Problem

The LLM summarization process was appearing to "hang" on the first file, with no visible progress or output. In reality, the process was working but taking an extremely long time due to:

1. **Large documents** (700k+ characters)
2. **Multiple chunks** requiring separate API calls
3. **Slow API responses** (2-4 minutes per chunk)
4. **No progress feedback** during long API calls

## Debugging Tools Added

### 1. Enhanced Logging

The `ui/workers/llm_summary_thread.py` now includes detailed logging:

- Token counting and chunking decisions
- API call timing and progress
- Chunk processing with estimates
- Progress reporting with time remaining

### 2. Debug Scripts

#### `debug_summarization.py`

Runs the full application with timeout monitoring:

```bash
uv run python debug_summarization.py [timeout_minutes]
```

#### `test_single_file_summarization.py`

Tests a single file in isolation:

```bash
uv run python test_single_file_summarization.py [file_path] [output_dir]
```

### 3. Progress Improvements

- **Chunk estimation**: Shows estimated processing time
- **Real-time progress**: Updates during chunk processing
- **Time remaining**: Calculates ETA based on actual performance
- **API timing**: Shows how long each API call takes

## Running with Enhanced Debugging

### Option 1: Debug Script (Recommended)

```bash
# Run with 20-minute timeout and enhanced logging
uv run python debug_summarization.py 20
```

This will:

- Enable detailed logging to console and file
- Monitor progress every 30 seconds
- Terminate if it takes longer than specified timeout
- Save logs to `logs/summarization_debug_*.log`

### Option 2: Single File Test

```bash
# Test just the problematic file
uv run python test_single_file_summarization.py
```

### Option 3: Regular Application with Logs

```bash
# Run normally but check logs for progress
uv run python main.py

# In another terminal, monitor logs:
tail -f logs/summarization_debug_*.log
```

## What the Logs Tell You

### Normal Operation

```
📊 Document requires chunking - Token count: 179656
✂️ Starting document chunking...
✅ Document split into 3 chunks
⏱️ Estimated processing time: 7.5 minutes for 3 chunks
🎯 Starting processing of chunk 1/3
🚀 Calling llm_client.generate_response...
✅ API response received after 142.3 seconds
✅ Chunk 1/3 processed successfully
```

### Problem Indicators

```
❌ API response indicates failure: rate limit exceeded
🔄 Retryable error detected, tenacity will retry...
⏰ Test timed out after 20 minutes
❌ LLM client not initialized
```

## Performance Expectations

For a 700k character document (~175k tokens):

- **Chunks**: 2-3 chunks
- **Time per chunk**: 2-4 minutes
- **Total time**: 6-12 minutes
- **API calls**: 4-6 calls (token counting + chunks + meta-analysis)

## Troubleshooting

### If Still Hanging

1. Check API key and rate limits
2. Verify network connectivity
3. Try smaller test files first
4. Check Anthropic API status

### If Getting Errors

1. Review the enhanced logs
2. Check API quotas and billing
3. Verify environment configuration
4. Test with `test_single_file_summarization.py`

### If Too Slow

1. Consider smaller chunk sizes
2. Use different model (faster but potentially lower quality)
3. Process smaller files first
4. Check if rate limiting is the issue

## Configuration Options

You can adjust chunk processing in `ui/workers/llm_summary_thread.py`:

```python
# Larger chunks = fewer API calls but longer per call
max_chunk_size=80000  # Current setting

# Smaller chunks = more API calls but faster per call
max_chunk_size=40000  # Alternative for faster feedback
```

## Next Steps

1. **Run the debug script** to get detailed logs
2. **Monitor progress** - it should show chunk processing
3. **Check timing** - each chunk should complete in 2-4 minutes
4. **Verify completion** - summary files should be created

The process is no longer "hanging" - it's just taking time and now provides clear feedback about what it's doing and how long it will take.
