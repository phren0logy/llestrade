#!/usr/bin/env python3
"""
Smart launcher for Forensic Report Drafter.
Routes to legacy or new UI based on environment/flags.
"""

import os
import sys


def main():
    """Determine which UI to launch and run it."""
    # Check for new UI flag or environment variable
    use_new_ui = (
        "--new-ui" in sys.argv 
        or os.getenv("USE_NEW_UI", "").lower() in ("true", "1", "yes")
    )
    
    if use_new_ui:
        # Remove the flag from argv if present
        if "--new-ui" in sys.argv:
            sys.argv.remove("--new-ui")
        
        # Check if new UI exists
        try:
            from main_new import main as new_main
            print("Starting Forensic Report Drafter (New UI)...")
            return new_main()
        except ImportError:
            print("Warning: New UI not yet implemented, falling back to legacy UI")
            use_new_ui = False
    
    if not use_new_ui:
        # Use the legacy UI
        from main_legacy import main as legacy_main
        print("Starting Forensic Report Drafter (Legacy UI)...")
        return legacy_main()


if __name__ == "__main__":
    main()