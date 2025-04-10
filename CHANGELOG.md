# Changelog

## 2025-04-09

### Added

- Added comprehensive error handling for file processing in LLM summarization
- Created new `test_diagnosis.py` script for debugging individual problematic files
- Added detailed logging throughout LLM client code
- Created `verify_llm_connection.py` script with comprehensive API diagnostics
- Added separate error handling for Anthropic and Gemini API calls
- Added exponential backoff retry mechanism for API calls

### Changed

- Refactored Analysis tab to process files one at a time sequentially
- Improved file reading with better encoding detection
- Added file validation before sending to LLM for summary
- Improved error reporting in UI with more specific error messages
- Enhanced token counting with fallback estimation
- Improved signal/slot connections in Qt frontend
- Enhanced temporary file handling to avoid partial writes
- Updated documentation with troubleshooting section for "Unknown error" issues

### Fixed

- Fixed issue with Qt thread management causing "Unknown error" messages
- Fixed error propagation between threads
- Fixed handling of special characters and unusual encodings
- Fixed binary-like content handling
- Fixed concurrency issues when processing multiple files
- Fixed API error message clarity
- Fixed signal disconnection issues on thread completion
