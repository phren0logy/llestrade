"""
Configuration module for Llestrade (formerly Forensic Psych Report Drafter).
Centralizes all configuration settings and environment setup.
"""

import os
import platform
import site
import sys
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv


def load_env_file():
    """
    Load environment variables from .env file if it exists.
    """
    env_path = Path(".") / ".env"
    if not env_path.exists():
        # Try to use template if .env doesn't exist
        template_path = Path(".") / "config.template.env"
        if template_path.exists():
            print("INFO: .env file not found. Using config.template.env as reference.")
            print("Please create an .env file with your actual API keys.")
            # Load from template for demonstration purposes
            load_dotenv(template_path)
        return
    
    # Load variables from .env file using python-dotenv
    load_dotenv(env_path)
    print("Environment variables loaded from .env file")


def setup_qt_environment():
    """
    Set up the Qt environment variables for proper PyQt6 operation.
    Handles platform-specific configurations and debugging settings.
    """
    # Only enable Qt debugging if explicitly requested
    if os.environ.get('DEBUG_QT', '').lower() == 'true':
        os.environ["QT_DEBUG_PLUGINS"] = "1"
    
    # Find PyQt6 paths
    qt_dir = find_pyqt_paths()
    if qt_dir:
        # Set explicit paths before importing
        if platform.system() == "Darwin":
            os.environ["DYLD_LIBRARY_PATH"] = (
                f"{qt_dir}:{os.environ.get('DYLD_LIBRARY_PATH', '')}"
            )

        # Set plugin paths
        os.environ["QT_PLUGIN_PATH"] = os.path.join(qt_dir, "plugins")

        # Set platform plugin path
        platform_dir = os.path.join(qt_dir, "plugins", "platforms")
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platform_dir

        # Check for cocoa plugin on macOS (silent check)
        if platform.system() == "Darwin":
            cocoa_path = os.path.join(platform_dir, "libqcocoa.dylib")
            # Only print warnings if debug mode is enabled
            if not os.path.exists(cocoa_path) and os.environ.get('DEBUG_QT', '').lower() == 'true':
                print(f"WARNING: Cocoa plugin not found at {cocoa_path}")
                if os.path.exists(platform_dir):
                    print("Files in platforms directory:")
                    for f in os.listdir(platform_dir):
                        print(f"  - {f}")
    else:
        # This is not critical - PyQt6 can still work without explicit paths
        pass

    # Enable high DPI scaling
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"


def setup_environment_variables():
    """
    Set up environment variables required for the application.
    Includes checking for API key and other required settings.
    """
    # Load environment variables from .env file
    load_env_file()
    
    # Check for API keys (silent unless in debug mode)
    debug_mode = os.environ.get('DEBUG', '').lower() == 'true'
    
    if not os.environ.get("ANTHROPIC_API_KEY") and debug_mode:
        print("WARNING: ANTHROPIC_API_KEY environment variable not set")
        print("You will need to set this environment variable to use the LLM functionality")
    
    # Check for Azure Document Intelligence credentials
    if (not os.environ.get("AZURE_ENDPOINT") or not os.environ.get("AZURE_KEY")) and debug_mode:
        print("NOTE: Azure Document Intelligence credentials not found in environment variables")
        print("You can still use the Record Review tab but Azure processing will require credentials")
    
    # Set up Qt environment for PyQt6
    setup_qt_environment()


def find_pyqt_paths() -> Optional[str]:
    """
    Find the PyQt6 paths in site-packages.
    
    Returns:
        Path to Qt6 directory or None if not found
    """
    # Check all site-packages
    for site_dir in site.getsitepackages():
        qt_dir = os.path.join(site_dir, "PyQt6", "Qt6")
        if os.path.exists(qt_dir):
            return qt_dir
    return None


# Application constants
APP_NAME = "Llestrade"
APP_TITLE = "Llestrade"  # Application title
APP_VERSION = "1.1.0"
DEFAULT_WINDOW_SIZE = (1000, 800)
DEFAULT_FONT_FAMILY = "Arial"
DEFAULT_FONT_SIZE = 11
DEFAULT_TIMEOUT = 60.0  # seconds

# Default prompts
DEFAULT_REFINEMENT_PROMPT = """This draft report, wrapped in <draft> tags, is a rough draft of a forensic psychiatric report. Perform the following steps to improve the report:
1. Check the report against the provided transcript, wrapped in <transcript> tags, for accuracy. Minor changes to punctuation and capitalization are OK and do not need to be changed.
2. Check each section for information that is repeated in other sections. Put this information in the most appropriate section, and reference that section in other parts of the report where that information was repeated.
3. Some information may not appear in the transcript, such as quotes from other documents or psychometric testing. Do not make changes to this information that does not appear in the transcript.
4. After making those changes, revise the document for readability. Preserve details that are important for accurate diagnosis and formulation.
5. Output only the final revised report."""
