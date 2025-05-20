#!/usr/bin/env python3
"""
Script to convert PyQt6 imports to PySide6 imports in the codebase.
This helps migrate the application from PyQt6 to PySide6.
"""

import os
import re
import sys
from pathlib import Path


def find_files_with_pyqt6(directory, extensions=(".py",)):
    """Find all Python files with PyQt6 imports."""
    pyqt6_files = []

    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(extensions):
                file_path = os.path.join(root, file)
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if "PyQt6" in content:
                        pyqt6_files.append(file_path)

    return pyqt6_files


def convert_file(file_path):
    """Convert PyQt6 imports to PySide6 in a file."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace imports
    content = content.replace("from PySide6.", "from PySide6.")
    content = content.replace("import PySide6", "import PySide6")

    # Replace "Qt6" directory references in plugin paths
    content = re.sub(r'([\'"])PyQt6/Qt6/([\'"])', r"\1PySide6/Qt/\2", content)
    content = re.sub(
        r'([\'"])PyQt6\\\\Qt6\\\\([\'"])', r"\1PySide6\\\\Qt\\\\2", content
    )

    # Write modified content back to file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return True


def main():
    """Main function to find and convert files from PyQt6 to PySide6."""
    # Use the current directory as the base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Searching for PyQt6 imports in: {base_dir}")

    # Find files with PyQt6 imports
    pyqt6_files = find_files_with_pyqt6(base_dir)

    if not pyqt6_files:
        print("No files with PyQt6 imports found.")
        return

    print(f"Found {len(pyqt6_files)} files with PyQt6 imports:")
    for file in pyqt6_files:
        print(f"  - {file}")

    # Ask for confirmation
    confirmation = input("\nDo you want to convert these files to PySide6? (y/n): ")
    if confirmation.lower() != "y":
        print("Conversion cancelled.")
        return

    # Convert files
    converted_count = 0
    for file in pyqt6_files:
        print(f"Converting {file}...", end="")
        if convert_file(file):
            print(" Done!")
            converted_count += 1
        else:
            print(" Failed!")

    print(f"\nConverted {converted_count} out of {len(pyqt6_files)} files.")


if __name__ == "__main__":
    main()
