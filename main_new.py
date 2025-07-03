#!/usr/bin/env python3
"""
New simplified UI for Forensic Report Drafter.
This is a placeholder that will be replaced with the full implementation.
"""

import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PySide6.QtCore import Qt


class SimplifiedMainWindow(QMainWindow):
    """Placeholder for the new simplified UI."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Forensic Report Drafter - New UI (Under Development)")
        self.setMinimumSize(800, 600)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Layout
        layout = QVBoxLayout(central)
        
        # Placeholder content
        label = QLabel(
            "New Simplified UI\n\n"
            "This interface is currently under development.\n\n"
            "Features coming soon:\n"
            "• Project-based workflow\n"
            "• Simplified stage progression\n"
            "• Better memory management\n"
            "• Integrated cost tracking\n"
            "• Template gallery\n\n"
            "Run without --new-ui flag to use the current interface."
        )
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                padding: 20px;
                color: #333;
            }
        """)
        layout.addWidget(label)


def main():
    """Main entry point for new UI."""
    app = QApplication(sys.argv)
    window = SimplifiedMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    main()