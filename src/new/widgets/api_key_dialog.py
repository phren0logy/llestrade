"""
API key configuration dialog for the new UI.
"""

import logging
from typing import Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QGroupBox,
    QDialogButtonBox, QMessageBox
)
from PySide6.QtCore import Qt


class APIKeyDialog(QDialog):
    """Dialog for configuring API keys."""
    
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        
        self.setWindowTitle("Configure API Keys")
        self.setModal(True)
        self.resize(500, 400)
        
        self.api_fields: Dict[str, QLineEdit] = {}
        
        self.setup_ui()
        self.load_keys()
    
    def setup_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Description
        desc = QLabel(
            "Enter your API keys for the LLM providers you want to use. "
            "Keys are stored securely in your system's keychain when available."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # API key fields
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
            
            layout.addWidget(group)
        
        # Additional settings for Azure
        azure_group = QGroupBox("Azure OpenAI Settings")
        azure_layout = QFormLayout(azure_group)
        
        self.azure_endpoint = QLineEdit()
        self.azure_endpoint.setPlaceholderText("https://your-resource.openai.azure.com/")
        azure_layout.addRow("Endpoint:", self.azure_endpoint)
        
        self.azure_deployment = QLineEdit()
        self.azure_deployment.setPlaceholderText("e.g., gpt-4")
        azure_layout.addRow("Deployment Name:", self.azure_deployment)
        
        layout.addWidget(azure_group)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.save_keys)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        layout.addStretch()
    
    def load_keys(self):
        """Load existing API keys (masked)."""
        for provider, field in self.api_fields.items():
            key = self.settings.get_api_key(provider)
            if key:
                # Show masked version
                field.setText("*" * 20)
                field.setProperty("has_saved_key", True)
            else:
                field.setProperty("has_saved_key", False)
        
        # Load Azure settings
        azure_settings = self.settings.get("azure_openai_settings", {})
        self.azure_endpoint.setText(azure_settings.get("endpoint", ""))
        self.azure_deployment.setText(azure_settings.get("deployment", ""))
    
    def save_keys(self):
        """Save API keys to secure storage."""
        saved_count = 0
        errors = []
        
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
        
        # Save Azure settings
        if self.api_fields["azure_openai"].text().strip():
            azure_settings = {
                "endpoint": self.azure_endpoint.text().strip(),
                "deployment": self.azure_deployment.text().strip()
            }
            self.settings.set("azure_openai_settings", azure_settings)
        
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
                    "Keys Saved",
                    f"Successfully saved {saved_count} API key(s)."
                )
            self.accept()
    
    @staticmethod
    def configure_api_keys(settings, parent=None):
        """Static method to show the dialog."""
        dialog = APIKeyDialog(settings, parent)
        return dialog.exec() == QDialog.Accepted