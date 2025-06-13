#!/usr/bin/env python3
"""
Test script for debugging summarization of a single file.
"""

import logging
import os
import sys
import time
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtCore import QCoreApplication

from ui.workers.llm_summary_thread import LLMSummaryThread


def setup_logging():
    """Set up detailed logging."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def test_single_file(file_path, output_dir):
    """Test summarization of a single file."""
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False
    
    print(f"🧪 Testing summarization of: {file_path}")
    print(f"📂 Output directory: {output_dir}")
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Create a minimal Qt application
    app = QCoreApplication(sys.argv)
    
    # Create the summarization thread
    thread = LLMSummaryThread(
        parent=None,
        markdown_files=[file_path],
        output_dir=output_dir,
        subject_name="Test Subject",
        subject_dob="1990-01-01",
        case_info="Test case for debugging summarization",
        status_panel=None,  # No status panel for testing
        llm_provider_id="anthropic",
        llm_model_name="claude-3-7-sonnet-latest"
    )
    
    # Connect signals for monitoring
    def on_progress(percent, message):
        print(f"📊 Progress: {percent}% - {message}")
    
    def on_file_progress(percent, message):
        print(f"📄 File Progress: {percent}% - {message}")
    
    def on_finished(results):
        print(f"✅ Finished! Results: {results}")
        app.quit()
    
    def on_error(error_msg):
        print(f"❌ Error: {error_msg}")
        app.quit()
    
    def on_file_error(error_msg):
        print(f"❌ File Error: {error_msg}")
    
    thread.progress_signal.connect(on_progress)
    thread.file_progress.connect(on_file_progress)
    thread.finished_signal.connect(on_finished)
    thread.error_signal.connect(on_error)
    thread.file_error.connect(on_file_error)
    
    # Start the thread
    print("🚀 Starting summarization thread...")
    thread.start()
    
    # Set a timeout
    import signal
    def timeout_handler(signum, frame):
        print("⏰ Test timed out after 20 minutes")
        thread.terminate()
        app.quit()
    
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(20 * 60)  # 20 minutes timeout
    
    # Run the Qt event loop
    app.exec()
    
    # Cancel timeout
    signal.alarm(0)
    
    return True

if __name__ == "__main__":
    setup_logging()
    
    # Default test file (the one that was hanging)
    test_file = "/Users/andy/Library/CloudStorage/OneDrive-TagInc/Active/AI-experiments/2025-06-06-Conklin/markdown/20250602_104949_Users_andy_Library_CloudStorage_OneDrive-TagInc_Active_AI-experiments_2025-05-31-AC-test-case_source_documents_AC_07040001_387_DOC.md"
    test_output = "/Users/andy/Library/CloudStorage/OneDrive-TagInc/Active/AI-experiments/2025-06-06-Conklin/summaries"
    
    # Allow command line override
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
    if len(sys.argv) > 2:
        test_output = sys.argv[2]
    
    print("🔬 Single File Summarization Test")
    print("=" * 50)
    print(f"📄 File: {test_file}")
    print(f"📂 Output: {test_output}")
    print("=" * 50)
    
    success = test_single_file(test_file, test_output)
    
    if success:
        print("🏁 Test completed")
    else:
        print("❌ Test failed")
        sys.exit(1) 
