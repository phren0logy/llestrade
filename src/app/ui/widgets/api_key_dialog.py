"""
API key configuration dialog for the new UI.
"""

import logging
from typing import Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QGroupBox,
    QDialogButtonBox, QMessageBox, QScrollArea,
    QWidget, QTabWidget, QCheckBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl


class APIKeyDialog(QDialog):
    """Dialog for configuring API keys and service endpoints."""
    
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        
        self.setWindowTitle("Configure API Keys & Services")
        self.setModal(True)
        self.resize(600, 700)
        
        self.api_fields: Dict[str, QLineEdit] = {}
        self.config_fields: Dict[str, QLineEdit] = {}
        
        self.setup_ui()
        self.load_keys()
    
    def setup_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Description
        desc = QLabel(
            "Configure your API keys and service endpoints. "
            "Keys are stored securely in your system's keychain when available."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Create tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # LLM Providers tab
        llm_tab = self._create_llm_tab()
        tabs.addTab(llm_tab, "LLM Providers")
        
        # Azure Services tab
        azure_tab = self._create_azure_tab()
        tabs.addTab(azure_tab, "Azure Services")
        
        # Phoenix Observability tab
        phoenix_tab = self._create_phoenix_tab()
        tabs.addTab(phoenix_tab, "Phoenix (Observability)")
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.save_keys)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _create_llm_tab(self) -> QWidget:
        """Create the LLM providers tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Scroll area for providers
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # LLM Providers
        providers = [
            ("Anthropic (Claude)", "anthropic", "https://console.anthropic.com/"),
            ("Google Gemini", "gemini", "https://makersuite.google.com/app/apikey"),
            ("Azure OpenAI", "azure_openai", "https://portal.azure.com/")
        ]
        
        for display_name, key, url in providers:
            group = QGroupBox(display_name)
            group_layout = QVBoxLayout(group)
            
            # API key input
            key_layout = QHBoxLayout()
            
            field = QLineEdit()
            field.setEchoMode(QLineEdit.Password)
            field.setPlaceholderText(f"Enter {display_name} API key...")
            self.api_fields[key] = field
            key_layout.addWidget(field)
            
            # Show/hide button
            show_btn = QPushButton("Show")
            show_btn.setCheckable(True)
            show_btn.setMaximumWidth(60)
            show_btn.toggled.connect(
                lambda checked, f=field: f.setEchoMode(
                    QLineEdit.Normal if checked else QLineEdit.Password
                )
            )
            key_layout.addWidget(show_btn)
            
            group_layout.addLayout(key_layout)
            
            # Help text with URL
            help_text = QLabel(f'<a href="{url}">Get API key →</a>')
            help_text.setOpenExternalLinks(True)
            help_text.setStyleSheet("color: #1976d2;")
            group_layout.addWidget(help_text)
            
            scroll_layout.addWidget(group)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        
        return widget
    
    def _create_azure_tab(self) -> QWidget:
        """Create the Azure services tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Azure OpenAI Settings
        openai_group = QGroupBox("Azure OpenAI Configuration")
        openai_layout = QFormLayout(openai_group)
        
        self.azure_endpoint = QLineEdit()
        self.azure_endpoint.setPlaceholderText("https://your-resource.openai.azure.com/")
        openai_layout.addRow("Endpoint:", self.azure_endpoint)
        self.config_fields["azure_endpoint"] = self.azure_endpoint
        
        self.azure_deployment = QLineEdit()
        self.azure_deployment.setPlaceholderText("e.g., gpt-4.1")
        openai_layout.addRow("Deployment Name:", self.azure_deployment)
        self.config_fields["azure_deployment"] = self.azure_deployment
        
        self.azure_api_version = QLineEdit()
        self.azure_api_version.setPlaceholderText("e.g., 2025-01-01-preview")
        openai_layout.addRow("API Version:", self.azure_api_version)
        self.config_fields["azure_api_version"] = self.azure_api_version
        
        layout.addWidget(openai_group)
        
        # Azure Document Intelligence Settings
        di_group = QGroupBox("Azure Document Intelligence")
        di_layout = QVBoxLayout(di_group)
        
        # API key input
        key_layout = QHBoxLayout()
        
        self.azure_di_key = QLineEdit()
        self.azure_di_key.setEchoMode(QLineEdit.Password)
        self.azure_di_key.setPlaceholderText("Enter Azure Document Intelligence API key...")
        self.api_fields["azure_di"] = self.azure_di_key
        key_layout.addWidget(self.azure_di_key)
        
        # Show/hide button
        show_btn = QPushButton("Show")
        show_btn.setCheckable(True)
        show_btn.setMaximumWidth(60)
        show_btn.toggled.connect(
            lambda checked: self.azure_di_key.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        key_layout.addWidget(show_btn)
        
        di_layout.addLayout(key_layout)
        
        # Endpoint
        endpoint_layout = QFormLayout()
        self.azure_di_endpoint = QLineEdit()
        self.azure_di_endpoint.setPlaceholderText("https://your-resource.cognitiveservices.azure.com/")
        endpoint_layout.addRow("Endpoint:", self.azure_di_endpoint)
        self.config_fields["azure_di_endpoint"] = self.azure_di_endpoint
        
        di_layout.addLayout(endpoint_layout)
        
        # Help text
        help_text = QLabel('<a href="https://portal.azure.com/">Configure in Azure Portal →</a>')
        help_text.setOpenExternalLinks(True)
        help_text.setStyleSheet("color: #1976d2;")
        di_layout.addWidget(help_text)
        
        layout.addWidget(di_group)
        
        layout.addStretch()
        return widget
    
    def _open_phoenix_ui(self):
        """Open Phoenix UI in browser."""
        port = self.phoenix_port.text() or "6006"
        QDesktopServices.openUrl(QUrl(f"http://localhost:{port}"))
    
    def _create_phoenix_tab(self) -> QWidget:
        """Create the Phoenix observability tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Phoenix info
        info = QLabel(
            "Arize Phoenix provides local LLM observability and debugging. "
            "Enable Phoenix to trace LLM calls, capture costs, and debug issues. "
            "Phoenix runs locally on your machine for complete data privacy."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        
        # Phoenix Settings
        phoenix_group = QGroupBox("Phoenix Configuration")
        phoenix_layout = QVBoxLayout(phoenix_group)
        
        # Enable/Disable Phoenix
        self.phoenix_enabled = QCheckBox("Enable Phoenix Observability")
        self.phoenix_enabled.setToolTip(
            "When enabled, Phoenix will trace all LLM calls locally"
        )
        phoenix_layout.addWidget(self.phoenix_enabled)
        
        # Phoenix Port
        port_layout = QFormLayout()
        self.phoenix_port = QLineEdit()
        self.phoenix_port.setText("6006")  # Default port
        self.phoenix_port.setPlaceholderText("Default: 6006")
        port_layout.addRow("Local Port:", self.phoenix_port)
        phoenix_layout.addLayout(port_layout)
        
        # Project Name
        project_layout = QFormLayout()
        self.phoenix_project = QLineEdit()
        self.phoenix_project.setText("forensic-report-drafter")
        self.phoenix_project.setPlaceholderText("Project name for organizing traces")
        project_layout.addRow("Project Name:", self.phoenix_project)
        phoenix_layout.addLayout(project_layout)
        
        # Export Fixtures Option
        self.phoenix_export_fixtures = QCheckBox("Export traces as test fixtures")
        self.phoenix_export_fixtures.setToolTip(
            "Automatically save LLM responses as test fixtures for mocking"
        )
        phoenix_layout.addWidget(self.phoenix_export_fixtures)
        
        # Store config fields
        self.config_fields["phoenix_enabled"] = self.phoenix_enabled
        self.config_fields["phoenix_port"] = self.phoenix_port
        self.config_fields["phoenix_project"] = self.phoenix_project
        self.config_fields["phoenix_export_fixtures"] = self.phoenix_export_fixtures
        
        # Help text
        help_text = QLabel('<a href="https://phoenix.arize.com/">Learn more about Phoenix →</a>')
        help_text.setOpenExternalLinks(True)
        help_text.setStyleSheet("color: #1976d2;")
        phoenix_layout.addWidget(help_text)
        
        # View Phoenix UI Button
        view_button = QPushButton("Open Phoenix UI")
        view_button.clicked.connect(self._open_phoenix_ui)
        phoenix_layout.addWidget(view_button)
        
        layout.addWidget(phoenix_group)
        
        layout.addStretch()
        return widget
    
    def load_keys(self):
        """Load existing API keys and settings."""
        # Load API keys (masked)
        for provider, field in self.api_fields.items():
            key = self.settings.get_api_key(provider)
            if key:
                # Show masked version
                field.setText("*" * 20)
                field.setProperty("has_saved_key", True)
            else:
                field.setProperty("has_saved_key", False)
        
        # Load Azure OpenAI settings
        azure_settings = self.settings.get("azure_openai_settings", {})
        if "endpoint" in azure_settings:
            self.azure_endpoint.setText(azure_settings["endpoint"])
        if "deployment" in azure_settings:
            self.azure_deployment.setText(azure_settings["deployment"])
        if "api_version" in azure_settings:
            self.azure_api_version.setText(azure_settings["api_version"])
        
        # Load Azure DI settings
        azure_di_settings = self.settings.get("azure_di_settings", {})
        if "endpoint" in azure_di_settings:
            self.azure_di_endpoint.setText(azure_di_settings["endpoint"])
        
        # Load Phoenix settings
        phoenix_settings = self.settings.get("phoenix_settings", {})
        self.phoenix_enabled.setChecked(phoenix_settings.get("enabled", False))
        if "port" in phoenix_settings:
            self.phoenix_port.setText(str(phoenix_settings["port"]))
        if "project" in phoenix_settings:
            self.phoenix_project.setText(phoenix_settings["project"])
        self.phoenix_export_fixtures.setChecked(
            phoenix_settings.get("export_fixtures", False)
        )
    
    def save_keys(self):
        """Save API keys and settings to secure storage."""
        saved_count = 0
        errors = []
        
        # Save API keys
        for provider, field in self.api_fields.items():
            text = field.text().strip()
            
            # Skip if field shows masked placeholder
            if text == "*" * 20 and field.property("has_saved_key"):
                continue
            
            # Save or remove key
            if text and not text.startswith("*"):
                try:
                    if self.settings.set_api_key(provider, text):
                        saved_count += 1
                    else:
                        errors.append(f"Failed to save {provider} key")
                except Exception as e:
                    errors.append(f"Error saving {provider}: {str(e)}")
            elif not text and field.property("has_saved_key"):
                # Remove key if field was cleared
                self.settings.remove_api_key(provider)
        
        # Save Azure OpenAI settings
        azure_endpoint = self.azure_endpoint.text().strip()
        azure_deployment = self.azure_deployment.text().strip()
        azure_api_version = self.azure_api_version.text().strip()
        
        if any([azure_endpoint, azure_deployment, azure_api_version]):
            azure_settings = {}
            if azure_endpoint:
                azure_settings["endpoint"] = azure_endpoint
            if azure_deployment:
                azure_settings["deployment"] = azure_deployment
            if azure_api_version:
                azure_settings["api_version"] = azure_api_version
            self.settings.set("azure_openai_settings", azure_settings)
        
        # Save Azure DI settings
        azure_di_endpoint = self.azure_di_endpoint.text().strip()
        if azure_di_endpoint:
            azure_di_settings = {"endpoint": azure_di_endpoint}
            self.settings.set("azure_di_settings", azure_di_settings)
        
        # Save Phoenix settings
        phoenix_settings = {
            "enabled": self.phoenix_enabled.isChecked(),
            "port": int(self.phoenix_port.text() or 6006),
            "project": self.phoenix_project.text().strip() or "forensic-report-drafter",
            "export_fixtures": self.phoenix_export_fixtures.isChecked()
        }
        self.settings.set("phoenix_settings", phoenix_settings)
        
        # Show result
        if errors:
            QMessageBox.warning(
                self,
                "Save Errors",
                "Some keys could not be saved:\n" + "\n".join(errors)
            )
        else:
            if saved_count > 0:
                QMessageBox.information(
                    self,
                    "Settings Saved",
                    f"Successfully saved {saved_count} API key(s) and settings."
                )
            self.accept()
    
    @staticmethod
    def configure_api_keys(settings, parent=None):
        """Static method to show the dialog."""
        dialog = APIKeyDialog(settings, parent)
        return dialog.exec() == QDialog.Accepted