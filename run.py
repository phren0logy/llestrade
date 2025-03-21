#!/usr/bin/env python3
"""
Launcher script for the Forensic Psych Report Drafter application.
Handles dependencies installation and application startup.
"""

import os
import sys
import subprocess
import argparse


def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        # Check for uv, which is the required dependency manager
        subprocess.run(
            ["uv", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        print("Error: uv not found. Please install uv first.")
        print("Visit https://github.com/astral-sh/uv for installation instructions.")
        return False


def install_dependencies():
    """Install required dependencies using uv."""
    print("Installing dependencies...")
    try:
        subprocess.run(
            ["uv", "pip", "install", "-r", "requirements.txt"],
            check=True
        )
        print("Dependencies installed successfully.")
        return True
    except subprocess.SubprocessError as e:
        print(f"Error installing dependencies: {e}")
        return False


def run_application():
    """Run the main application."""
    try:
        subprocess.run(
            ["uv", "run", "main.py"],
            check=True
        )
        return True
    except subprocess.SubprocessError as e:
        print(f"Error running application: {e}")
        return False


def main():
    """Main function to parse arguments and run the application."""
    parser = argparse.ArgumentParser(description="Forensic Psych Report Drafter")
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip dependency installation"
    )
    args = parser.parse_args()

    # Check uv is available
    if not check_dependencies():
        return 1

    # Install dependencies unless skipped
    if not args.skip_deps:
        if not install_dependencies():
            return 1

    # Run the application
    if not run_application():
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
