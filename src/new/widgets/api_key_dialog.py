"""
API key configuration dialog for the new UI.
"""

import logging
from typing import Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QGroupBox,
    QDialogButtonBox, QMessageBox, QScrollArea,
    QWidget, QTabWidget
)
from PySide6.QtCore import Qt


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
        
        # Langfuse tab
        langfuse_tab = self._create_langfuse_tab()
        tabs.addTab(langfuse_tab, "Langfuse (Observability)")
        
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
    
    def _create_langfuse_tab(self) -> QWidget:
        """Create the Langfuse tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Langfuse info
        info = QLabel(
            "Langfuse provides observability and cost tracking for LLM applications. "
            "Optional but recommended for monitoring usage and costs."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        
        # Langfuse Settings
        langfuse_group = QGroupBox("Langfuse Configuration")
        langfuse_layout = QVBoxLayout(langfuse_group)
        
        # Public key
        public_layout = QHBoxLayout()
        self.langfuse_public_key = QLineEdit()
        self.langfuse_public_key.setPlaceholderText("Enter Langfuse public key...")
        self.config_fields["langfuse_public_key"] = self.langfuse_public_key
        public_layout.addWidget(QLabel("Public Key:"))
        public_layout.addWidget(self.langfuse_public_key)
        langfuse_layout.addLayout(public_layout)
        
        # Private key
        private_layout = QHBoxLayout()
        self.langfuse_private_key = QLineEdit()
        self.langfuse_private_key.setEchoMode(QLineEdit.Password)
        self.langfuse_private_key.setPlaceholderText("Enter Langfuse private key...")
        self.api_fields["langfuse_private"] = self.langfuse_private_key
        private_layout.addWidget(QLabel("Private Key:"))
        private_layout.addWidget(self.langfuse_private_key)
        
        # Show/hide button for private key
        show_btn = QPushButton("Show")
        show_btn.setCheckable(True)
        show_btn.setMaximumWidth(60)
        show_btn.toggled.connect(
            lambda checked: self.langfuse_private_key.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        private_layout.addWidget(show_btn)
        langfuse_layout.addLayout(private_layout)
        
        # URL
        url_layout = QFormLayout()
        self.langfuse_url = QLineEdit()
        self.langfuse_url.setPlaceholderText("https://cloud.langfuse.com or self-hosted URL")
        url_layout.addRow("URL:", self.langfuse_url)
        self.config_fields["langfuse_url"] = self.langfuse_url
        langfuse_layout.addLayout(url_layout)
        
        # Help text
        help_text = QLabel('<a href="https://langfuse.com/">Learn more about Langfuse →</a>')
        help_text.setOpenExternalLinks(True)
        help_text.setStyleSheet("color: #1976d2;")
        langfuse_layout.addWidget(help_text)
        
        layout.addWidget(langfuse_group)
        
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
        
        # Load Langfuse settings
        langfuse_settings = self.settings.get("langfuse_settings", {})
        if "public_key" in langfuse_settings:
            self.langfuse_public_key.setText(langfuse_settings["public_key"])
        if "url" in langfuse_settings:
            self.langfuse_url.setText(langfuse_settings["url"])
    
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
        
        # Save Langfuse settings
        langfuse_public = self.langfuse_public_key.text().strip()
        langfuse_url = self.langfuse_url.text().strip()
        
        if any([langfuse_public, langfuse_url]):
            langfuse_settings = {}
            if langfuse_public:
                langfuse_settings["public_key"] = langfuse_public
            if langfuse_url:
                langfuse_settings["url"] = langfuse_url
            self.settings.set("langfuse_settings", langfuse_settings)
        
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