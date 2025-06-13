#!/usr/bin/env python3
"""
Debug script for monitoring LLM summarization with timeout and detailed logging.
"""

import logging
import signal
import sys
import threading
import time
from pathlib import Path


def setup_debug_logging():
    """Set up enhanced logging for debugging."""
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Configure logging with more detail
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(logs_dir / f"summarization_debug_{int(time.time())}.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set specific loggers to debug level
    loggers_to_debug = [
        'ui.workers.llm_summary_thread',
        'llm_utils',
        'app_config',
        'httpx'  # For API request monitoring
    ]
    
    for logger_name in loggers_to_debug:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
    
    logging.info("🔧 Debug logging configured")

def timeout_handler(signum, frame):
    """Handle timeout signal."""
    print("\n⏰ TIMEOUT: Process has been running too long, terminating...")
    logging.error("Process terminated due to timeout")
    sys.exit(1)

def progress_monitor():
    """Monitor progress and log periodically."""
    start_time = time.time()
    last_log_time = start_time
    
    while True:
        time.sleep(30)  # Log every 30 seconds
        current_time = time.time()
        elapsed = current_time - start_time
        since_last = current_time - last_log_time
        
        logging.info(f"⏱️ PROGRESS MONITOR: {elapsed:.1f}s elapsed, still running...")
        logging.info(f"📊 Memory and process status check (last update: {since_last:.1f}s ago)")
        last_log_time = current_time

def run_with_timeout(timeout_minutes=15):
    """Run the application with timeout monitoring."""
    print(f"🚀 Starting LLM summarization debug session with {timeout_minutes} minute timeout")
    
    # Set up timeout signal
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_minutes * 60)  # Convert to seconds
    
    # Start progress monitoring in background
    monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
    monitor_thread.start()
    
    try:
        # Import and run the main application
        import os
        import subprocess
        
        # Change to the correct directory
        os.chdir(Path(__file__).parent)
        
        # Run the main application
        print("🏃 Launching main application...")
        result = subprocess.run([
            "uv", "run", "python", "main.py"
        ], capture_output=False, text=True, timeout=timeout_minutes * 60)
        
        if result.returncode == 0:
            print("✅ Application completed successfully")
        else:
            print(f"❌ Application failed with return code: {result.returncode}")
            
    except subprocess.TimeoutExpired:
        print(f"⏰ Application timed out after {timeout_minutes} minutes")
        logging.error(f"Application timed out after {timeout_minutes} minutes")
    except KeyboardInterrupt:
        print("\n⌨️ Interrupted by user")
        logging.info("Application interrupted by user")
    except Exception as e:
        print(f"❌ Error running application: {e}")
        logging.error(f"Error running application: {e}")
    finally:
        # Cancel the alarm
        signal.alarm(0)
        print("🏁 Debug session completed")

if __name__ == "__main__":
    setup_debug_logging()
    
    # Get timeout from command line or use default
    timeout_minutes = 15
    if len(sys.argv) > 1:
        try:
            timeout_minutes = int(sys.argv[1])
        except ValueError:
            print("Invalid timeout value, using default of 15 minutes")
    
    print(f"🔍 Debug mode: Enhanced logging enabled")
    print(f"⏰ Timeout: {timeout_minutes} minutes")
    print(f"📝 Logs will be saved to: logs/summarization_debug_*.log")
    
    run_with_timeout(timeout_minutes) 
