#!/usr/bin/env python3
"""
Test script for debugging summarization with a small file (no chunking).
"""

import logging
import os
import sys
import tempfile
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

def create_small_test_file():
    """Create a small test file that won't trigger chunking."""
    content = """# Test Document

## Patient Information
- Name: Test Patient
- DOB: 1990-01-01
- Case Number: TEST-001

## Summary
This is a small test document to verify summarization works without chunking.
The document contains basic patient information and a simple summary section.

## Medical History
- No significant medical history
- Regular checkups completed
- Patient reports feeling well

## Conclusion
This is a test document for debugging purposes.
"""
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(content)
        return f.name

def test_small_file():
    """Test summarization of a small file."""
    app = QCoreApplication(sys.argv)
    
    try:
        # Create test file
        test_file = create_small_test_file()
        output_dir = tempfile.mkdtemp()
        
        print(f"🔬 Small File Summarization Test")
        print("=" * 50)
        print(f"📄 File: {test_file}")
        print(f"📂 Output: {output_dir}")
        print("=" * 50)
        
        print(f"🧪 Testing summarization of small file...")
        print(f"📂 Output directory: {output_dir}")
        
        # Create and configure thread
        thread = LLMSummaryThread(
            parent=None,
            markdown_files=[test_file],
            output_dir=output_dir,
            subject_name="Test Subject",
            subject_dob="1990-01-01",
            case_info="Test case for debugging",
            status_panel=None,  # Test without status panel
            llm_provider_id="anthropic",
            llm_model_name="claude-3-7-sonnet-latest"
        )
        
        # Connect signals to track progress
        results = {"finished": False, "error": None, "results": None}
        
        def on_finished(res):
            results["finished"] = True
            results["results"] = res
            print(f"✅ Finished! Results: {res}")
            app.quit()
        
        def on_error(error):
            results["finished"] = True
            results["error"] = error
            print(f"❌ Error: {error}")
            app.quit()
        
        def on_progress(percent, message):
            print(f"📊 Progress: {percent}% - {message}")
        
        def on_file_progress(percent, message):
            print(f"📄 File Progress: {percent}% - {message}")
        
        thread.finished_signal.connect(on_finished)
        thread.error_signal.connect(on_error)
        thread.progress_signal.connect(on_progress)
        thread.file_progress.connect(on_file_progress)
        
        print("🚀 Starting summarization thread...")
        thread.start()
        
        # Run the event loop with a timeout
        start_time = time.time()
        while not results["finished"] and (time.time() - start_time) < 300:  # 5 minute timeout
            app.processEvents()
            time.sleep(0.1)
        
        if not results["finished"]:
            print("⏰ Test timed out")
            thread.cleanup()
            return False
        
        if results["error"]:
            print(f"❌ Test failed with error: {results['error']}")
            return False
        
        print("🏁 Test completed successfully")
        return True
        
    except Exception as e:
        print(f"💥 Exception in test: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        try:
            if 'test_file' in locals():
                os.unlink(test_file)
            if 'output_dir' in locals():
                import shutil
                shutil.rmtree(output_dir, ignore_errors=True)
        except Exception:
            pass

if __name__ == "__main__":
    setup_logging()
    success = test_small_file()
    sys.exit(0 if success else 1) 
