"""
Simple test script to verify PySide6 is working properly.
Especially useful for debugging platform plugin issues on macOS.
"""

import os
import sys

# macOS Qt plugin fix: must be done before importing PySide6
if sys.platform == "darwin":
    print("Running on macOS, checking for Qt plugins")
    possible_plugin_paths = []

    # Add potential PySide6 plugin paths from site-packages
    try:
        import site

        for site_dir in site.getsitepackages():
            qt_path = os.path.join(site_dir, "PySide6", "Qt", "plugins")
            if os.path.exists(qt_path):
                print(f"Found Qt plugins at: {qt_path}")
                possible_plugin_paths.append(qt_path)
    except ImportError:
        print("Couldn't import site module")

    # Check if we're in a virtual environment
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        venv_path = os.path.join(
            sys.prefix,
            "lib",
            "python" + sys.version[:3],
            "site-packages",
            "PySide6",
            "Qt",
            "plugins",
        )
        if os.path.exists(venv_path):
            print(f"Found venv Qt plugins at: {venv_path}")
            possible_plugin_paths.append(venv_path)

    # Set environment variables if we found valid paths
    if possible_plugin_paths:
        os.environ["QT_PLUGIN_PATH"] = os.pathsep.join(possible_plugin_paths)
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.pathsep.join(
            [
                os.path.join(p, "platforms")
                for p in possible_plugin_paths
                if os.path.exists(os.path.join(p, "platforms"))
            ]
        )
        print(f"Set QT_PLUGIN_PATH to: {os.environ.get('QT_PLUGIN_PATH')}")
        print(
            f"Set QT_QPA_PLATFORM_PLUGIN_PATH to: {os.environ.get('QT_QPA_PLATFORM_PLUGIN_PATH')}"
        )
    else:
        print("No Qt plugin paths found!")

print("Importing PySide6...")
from PySide6.QtWidgets import QApplication, QLabel, QWidget

# Additional plugin path setting using QCoreApplication
if (
    sys.platform == "darwin"
    and "possible_plugin_paths" in locals()
    and possible_plugin_paths
):
    from PySide6.QtCore import QCoreApplication

    QCoreApplication.setLibraryPaths(possible_plugin_paths)
    print(f"Set QCoreApplication library paths to: {QCoreApplication.libraryPaths()}")


def main():
    """Create a simple PySide6 window to test if everything works."""
    print("Creating QApplication...")
    app = QApplication(sys.argv)

    print("Creating window...")
    window = QWidget()
    window.setWindowTitle("PySide6 Test")
    window.setGeometry(100, 100, 300, 200)

    print("Creating label...")
    label = QLabel("PySide6 is working correctly!", window)
    label.setGeometry(50, 80, 200, 40)

    print("Showing window...")
    window.show()

    print("Running application...")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
