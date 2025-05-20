#!/usr/bin/env python3
"""
Script to fix PyQt6 to PySide6 signal differences.
In PyQt6, signals are created using Signal.
In PySide6, signals are created using Signal.
"""

import os
import re
from pathlib import Path


def find_files_with_pyqtsignal(directory, extensions=(".py",)):
    """Find all Python files with Signal imports or usages."""
    signal_files = []

    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(extensions):
                file_path = os.path.join(root, file)
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if "Signal" in content:
                        signal_files.append(file_path)

    return signal_files


def fix_file(file_path):
    """Fix PyQt6 signal differences in a file."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Fix imports
    content = re.sub(
        r"from PySide6\.QtCore import (.*?)Signal(.*?)",
        r"from PySide6.QtCore import \1Signal\2",
        content,
    )

    # Fix class attributes/declarations
    content = content.replace("Signal", "Signal")

    # Write modified content back to file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return True


def main():
    """Main function to find and fix PyQt6 signal differences."""
    # Use the current directory as the base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Searching for Signal in: {base_dir}")

    # Find files with Signal
    signal_files = find_files_with_pyqtsignal(base_dir)

    if not signal_files:
        print("No files with Signal found.")
        return

    print(f"Found {len(signal_files)} files with Signal:")
    for file in signal_files:
        print(f"  - {file}")

    # Ask for confirmation
    confirmation = input("\nDo you want to fix these files? (y/n): ")
    if confirmation.lower() != "y":
        print("Fix cancelled.")
        return

    # Fix files
    fixed_count = 0
    for file in signal_files:
        print(f"Fixing {file}...", end="")
        if fix_file(file):
            print(" Done!")
            fixed_count += 1
        else:
            print(" Failed!")

    print(f"\nFixed {fixed_count} out of {len(signal_files)} files.")


if __name__ == "__main__":
    main()
