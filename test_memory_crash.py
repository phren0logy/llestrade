#!/usr/bin/env python3
"""
Minimal test script to isolate memory crash issue.
This script tests Qt signal/slot mechanism with LLM API calls.
"""

import sys
import os
import time
import faulthandler
import gc
from pathlib import Path

# Enable faulthandler
faulthandler.enable()

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from PySide6.QtCore import QObject, Signal, QThread, QCoreApplication
from PySide6.QtWidgets import QApplication

# Import LLM providers
from llm import create_provider

class TestWorker(QThread):
    """Test worker thread that makes API calls."""
    
    progress = Signal(str)
    finished = Signal()
    
    def __init__(self, provider_name="anthropic"):
        super().__init__()
        self.provider_name = provider_name
        self.iteration = 0
        
    def run(self):
        """Run API calls in a loop."""
        try:
            # Create provider
            provider = create_provider(self.provider_name)
            self.progress.emit(f"Created {self.provider_name} provider")
            
            # Test prompt
            prompt = "What is 2+2? Answer in one word."
            
            # Make multiple API calls
            for i in range(10):
                self.iteration = i + 1
                self.progress.emit(f"Iteration {self.iteration}/10: Making API call...")
                
                try:
                    response = provider.generate(
                        prompt=prompt,
                        temperature=0.1,
                        max_tokens=100
                    )
                    
                    if response.get("success"):
                        content = response.get("content", "")
                        self.progress.emit(f"Iteration {self.iteration}: Got response - {len(content)} chars")
                    else:
                        self.progress.emit(f"Iteration {self.iteration}: API error - {response.get('error')}")
                        
                except Exception as e:
                    self.progress.emit(f"Iteration {self.iteration}: Exception - {str(e)}")
                    
                # Force garbage collection
                gc.collect()
                time.sleep(1)  # Brief pause between calls
                
        except Exception as e:
            self.progress.emit(f"Worker error: {str(e)}")
        finally:
            self.finished.emit()

class TestApp(QObject):
    """Test application with signal handling."""
    
    def __init__(self):
        super().__init__()
        self.worker = None
        
    def start_test(self, provider_name):
        """Start the test worker."""
        print(f"\n{'='*60}")
        print(f"Starting test with {provider_name} provider")
        print(f"{'='*60}\n")
        
        self.worker = TestWorker(provider_name)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()
        
    def on_progress(self, message):
        """Handle progress updates."""
        print(f"[Progress] {message}")
        
    def on_finished(self):
        """Handle worker completion."""
        print("\n[Finished] Worker completed")
        QCoreApplication.quit()

def main():
    """Main test function."""
    print("Memory Crash Test Script")
    print("========================")
    print("This script tests Qt signal/slot with LLM API calls")
    print("Watch for crashes after API responses\n")
    
    # Get provider from command line or default
    provider = sys.argv[1] if len(sys.argv) > 1 else "anthropic"
    
    # Create Qt application
    app = QApplication(sys.argv)
    
    # Create and start test
    test = TestApp()
    test.start_test(provider)
    
    # Run event loop
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())