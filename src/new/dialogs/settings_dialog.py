"""
Settings dialog for the new UI.
Manages application-level settings like evaluator name and default preferences.
"""

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QPushButton, QLabel, QDialogButtonBox,
    QTabWidget, QWidget, QSpinBox, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon

from src.new.core import SecureSettings


class SettingsDialog(QDialog):
    """Application settings dialog."""
    
    # Signal emitted when settings are saved
    settings_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.settings = SecureSettings()
        
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(500)
        
        self._create_ui()
        self._load_settings()
        
    def _create_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Defaults tab
        defaults_tab = self._create_defaults_tab()
        self.tab_widget.addTab(defaults_tab, "Defaults")
        
        # API Keys tab (still needed for app-level API configuration)
        api_tab = self._create_api_tab()
        self.tab_widget.addTab(api_tab, "API Keys")
        
        layout.addWidget(self.tab_widget)
        
        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal
        )
        buttons.accepted.connect(self._save_settings)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        
    def _create_defaults_tab(self) -> QWidget:
        """Create the defaults tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # User Information
        user_group = QGroupBox("User Information")
        user_layout = QFormLayout(user_group)
        
        # Evaluator name
        self.evaluator_name_edit = QLineEdit()
        self.evaluator_name_edit.setPlaceholderText("e.g., Dr. Jane Smith")
        user_layout.addRow("Evaluator Name:", self.evaluator_name_edit)
        
        layout.addWidget(user_group)
        
        # Note about evaluator name
        note = QLabel(
            "ℹ️ Your evaluator name will be automatically used in all new projects."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666; padding: 10px;")
        layout.addWidget(note)
        
        # Project Defaults
        defaults_group = QGroupBox("Project Defaults")
        defaults_layout = QFormLayout(defaults_group)
        
        # Default output directory
        dir_layout = QHBoxLayout()
        self.default_dir_edit = QLineEdit()
        self.default_dir_edit.setPlaceholderText("Default: ~/Documents/Forensic Reports")
        dir_layout.addWidget(self.default_dir_edit)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_default_dir)
        dir_layout.addWidget(browse_btn)
        
        defaults_layout.addRow("Default Output Directory:", dir_layout)
        
        # Default template
        self.default_template_combo = QComboBox()
        self.default_template_combo.addItems([
            "Standard Competency Evaluation",
            "Criminal Responsibility",
            "Risk Assessment",
            "Juvenile Evaluation",
            "Custom Template"
        ])
        defaults_layout.addRow("Default Template:", self.default_template_combo)
        
        # Auto-save interval
        self.autosave_spin = QSpinBox()
        self.autosave_spin.setRange(30, 600)  # 30 seconds to 10 minutes
        self.autosave_spin.setSuffix(" seconds")
        self.autosave_spin.setValue(60)
        defaults_layout.addRow("Auto-save Interval:", self.autosave_spin)
        
        layout.addWidget(defaults_group)
        
        # UI Preferences
        ui_group = QGroupBox("UI Preferences")
        ui_layout = QFormLayout(ui_group)
        
        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "Auto"])
        ui_layout.addRow("Theme:", self.theme_combo)
        
        layout.addWidget(ui_group)
        
        layout.addStretch()
        return widget
        
    def _create_api_tab(self) -> QWidget:
        """Create the API keys tab."""
        from src.new.widgets.api_key_dialog import APIKeyDialog
        
        # Create a wrapper widget to hold the API key dialog content
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        
        # Create the API key dialog
        self.api_widget = APIKeyDialog(self.settings, self)
        
        # Find and hide the dialog buttons since we're embedding it
        for i in range(self.api_widget.layout().count()):
            item = self.api_widget.layout().itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QDialogButtonBox):
                item.widget().hide()
                break
        
        # Add the dialog content to the wrapper
        wrapper_layout.addWidget(self.api_widget)
        
        return wrapper
        
    def _browse_default_dir(self):
        """Browse for default output directory."""
        from PySide6.QtWidgets import QFileDialog
        
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Default Output Directory",
            str(Path.home() / "Documents"),
            QFileDialog.ShowDirsOnly
        )
        
        if directory:
            self.default_dir_edit.setText(directory)
            
    def _load_settings(self):
        """Load current settings into the dialog."""
        # User settings
        self.evaluator_name_edit.setText(
            self.settings.get_setting("evaluator_name", "")
        )
        
        # Default settings
        self.default_dir_edit.setText(
            self.settings.get_setting("default_output_directory", "")
        )
        
        default_template = self.settings.get_setting("default_template", "")
        if default_template:
            index = self.default_template_combo.findText(default_template)
            if index >= 0:
                self.default_template_combo.setCurrentIndex(index)
                
        self.autosave_spin.setValue(
            self.settings.get_setting("autosave_interval", 60)
        )
        
        # UI preferences
        theme = self.settings.get_setting("ui_theme", "Light")
        index = self.theme_combo.findText(theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
            
    def _save_settings(self):
        """Save all settings and close dialog."""
        # Save user settings
        self.settings.set_setting(
            "evaluator_name", 
            self.evaluator_name_edit.text().strip()
        )
        
        # Save default settings
        self.settings.set_setting(
            "default_output_directory",
            self.default_dir_edit.text().strip()
        )
        self.settings.set_setting(
            "default_template",
            self.default_template_combo.currentText()
        )
        self.settings.set_setting(
            "autosave_interval",
            self.autosave_spin.value()
        )
        
        # Save UI preferences
        self.settings.set_setting(
            "ui_theme",
            self.theme_combo.currentText()
        )
        
        # Save API keys if the widget exists
        if hasattr(self, 'api_widget'):
            # Call save_keys but prevent the dialog from closing
            accept_backup = self.api_widget.accept
            self.api_widget.accept = lambda: None  # No-op to prevent dialog close
            self.api_widget.save_keys()
            self.api_widget.accept = accept_backup
        
        # Emit signal that settings have changed
        self.settings_changed.emit()
        
        # Accept the dialog
        self.accept()