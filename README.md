# Forensic Psych Report Drafter

A tool for analyzing and summarizing forensic psychological reports using large language models.

## Installation

1. Clone this repository
2. Set up a Python environment using uv:
   ```
   uv venv .venv
   source .venv/bin/activate   # On Mac/Linux
   # or
   .\.venv\Scripts\activate    # On Windows
   ```
3. Install dependencies:
   ```
   uv pip install -r requirements.txt
   ```
4. Configure API keys:
   - Copy `config.template.env` to `.env`
   - Add your Anthropic API key (Claude) to `.env`
5. Run the application:
   ```
   python main.py
   ```

## Troubleshooting

### "Unknown error" with Batch File Processing

If you see "Unknown error" messages when processing multiple files in the Analysis tab, try these solutions:

1. **Process files one at a time**: The application has been updated to handle files sequentially to avoid thread issues.
2. **Check for problematic files**: Some files may contain content that causes issues:
   - Files with unusual character encodings
   - Files with binary-like content or corrupted text
   - Files that are extremely large (over 10MB)
3. **Use the diagnostic tool**: Run the diagnostic script on specific files:

   ```
   python test_diagnosis.py path/to/your/file.md
   ```

   This will help identify issues with specific files.

4. **Update the application**: Ensure you're running the latest version with the enhanced error handling.

### LLM API Issues

If you encounter "unknown error" issues with the LLM summarization, try these steps:

1. Run the verification script to check API connectivity:

   ```
   python verify_llm_connection.py
   ```

2. Run the direct test script to test the LLM API outside of the Qt framework:

   ```
   python direct_test.py
   ```

3. Common issues:

   - Missing API key in `.env` file
   - Network connectivity issues
   - Rate limiting (if you've done many API calls)
   - Signal/slot connection problems in Qt

4. If the direct test works but the application still has issues, try:
   - Restarting the application
   - Checking that your API key has sufficient quota
   - Using `setup_env.py` to reconfigure your API keys

### Signal/Slot Issues

The most common cause of "unknown error" is a problem with the Qt signal/slot connections when running the LLM operations in a separate thread. The application has been updated to handle these cases better, but if you still experience issues:

1. Check the application logs for detailed error messages
2. Try running the summarization operations through the direct test first to verify API functionality
3. Ensure that you have proper internet connectivity

## Usage

1. In the Analysis tab, select folders containing markdown documents
2. Enter subject information
3. Click "Generate Summaries with LLM" to create summaries
4. Use "Combine Summaries" to merge all summary documents
5. Generate an integrated analysis of all documents

## Diagnostic Tools

- `verify_llm_connection.py`: Tests API connectivity
- `test_summary.py`: Tests the summarization of a sample document
- `direct_test.py`: Comprehensive test of all LLM features
- `setup_env.py`: Interactive setup of API keys and environment
- `test_diagnosis.py`: Debug tool for testing specific files
