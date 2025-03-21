#!/usr/bin/env python3
"""
PyQt6 test for macOS with explicit plugin paths
"""

import sys
import os
import platform
import site
from pathlib import Path

# Turn on debugging for Qt plugins
os.environ["QT_DEBUG_PLUGINS"] = "1"

# Try to find PyQt6 paths before importing
pyqt6_paths = []

# Add site-packages paths
for site_path in site.getsitepackages():
    pyqt6_paths.append(Path(site_path) / "PyQt6")

# Add user site-packages if it exists
if site.USER_SITE:
    pyqt6_paths.append(Path(site.USER_SITE) / "PyQt6")

# Look for PyQt6 installation
for pyqt_path in pyqt6_paths:
    qt_plugins_path = pyqt_path / "Qt6" / "plugins"
    platforms_path = qt_plugins_path / "platforms"
    
    if platforms_path.exists():
        print(f"Found platforms directory: {platforms_path}")
        
        # Set required environment variables
        os.environ["QT_PLUGIN_PATH"] = str(qt_plugins_path)
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms_path)
        
        # Also set library path
        lib_path = qt_plugins_path.parent
        if platform.system() == "Darwin":
            if "DYLD_LIBRARY_PATH" in os.environ:
                os.environ["DYLD_LIBRARY_PATH"] = f"{str(lib_path)}:{os.environ['DYLD_LIBRARY_PATH']}"
            else:
                os.environ["DYLD_LIBRARY_PATH"] = str(lib_path)
                
        print(f"Set QT_PLUGIN_PATH: {os.environ['QT_PLUGIN_PATH']}")
        print(f"Set QT_QPA_PLATFORM_PLUGIN_PATH: {os.environ['QT_QPA_PLATFORM_PLUGIN_PATH']}")
        if platform.system() == "Darwin":
            print(f"Set DYLD_LIBRARY_PATH: {os.environ.get('DYLD_LIBRARY_PATH', 'Not set')}")
        break
else:
    print("Could not find PyQt6 plugins directory!")

# Now try importing PyQt6
try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QWidget
    from PyQt6.QtCore import Qt
    print("Successfully imported PyQt6 modules")
except ImportError as e:
    print(f"Failed to import PyQt6: {e}")
    sys.exit(1)

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt6 Test on macOS")
        self.setGeometry(100, 100, 400, 200)
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create layout
        layout = QVBoxLayout(central_widget)
        
        # Add label
        label = QLabel("PyQt6 Test Application on macOS")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        
        # Add button
        button = QPushButton("Click Me")
        button.clicked.connect(self.on_button_click)
        layout.addWidget(button)
    
    def on_button_click(self):
        print("Button clicked!")

def main():
    # Print diagnostic information
    print(f"Python version: {sys.version}")
    print(f"Platform: {platform.platform()}")
    
    # Create application
    app = QApplication(sys.argv)
    
    # Create and show window
    window = TestWindow()
    window.show()
    
    # Run event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
