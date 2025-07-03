"""
Project setup stage for the new UI.
Collects case information and validates configuration.
"""

import logging
from pathlib import Path
from typing import Tuple, Dict, Any

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QPushButton, QLabel, QDateEdit,
    QTextEdit, QFileDialog, QMessageBox, QComboBox,
    QWidget, QSizePolicy, QProgressDialog
)
from PySide6.QtCore import Qt, QDate, Signal
from PySide6.QtGui import QIcon, QPalette

from src.new.core import BaseStage, ProjectMetadata


class ProjectSetupStage(BaseStage):
    """Initial project setup and metadata collection."""
    
    # Additional signal for API key configuration
    configure_api_keys = Signal()
    
    def __init__(self, project=None):
        # Track if this is a new project or editing existing
        self.is_new_project = project is None
        
        # Call parent init after setting our attributes
        super().__init__(project)
        self.logger = logging.getLogger(__name__)
        
    def setup_ui(self):
        """Create the UI for project setup."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # Title
        title = QLabel("Project Setup")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        
        # Description
        desc = QLabel("Enter the case information to create a new forensic report project.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666;")
        layout.addWidget(desc)
        
        # API Key Status
        self.api_status_widget = self._create_api_status_widget()
        layout.addWidget(self.api_status_widget)
        
        # Main form
        form_widget = self._create_form_widget()
        layout.addWidget(form_widget)
        
        # Action buttons
        button_widget = self._create_button_widget()
        layout.addWidget(button_widget)
        
        # Add stretch to push everything to the top
        layout.addStretch()
        
        # Update API status
        self._update_api_status()
        
    def _create_api_status_widget(self) -> QWidget:
        """Create widget showing API key status."""
        group = QGroupBox("API Configuration")
        layout = QHBoxLayout(group)
        
        # Status indicators for each provider
        self.api_indicators = {}
        providers = [
            ("Anthropic", "anthropic"),
            ("Google Gemini", "gemini"),
            ("Azure OpenAI", "azure_openai")
        ]
        
        for display_name, key in providers:
            indicator = QLabel(f"● {display_name}")
            indicator.setToolTip(f"{display_name} API key status")
            self.api_indicators[key] = indicator
            layout.addWidget(indicator)
        
        layout.addStretch()
        
        # Configure button
        configure_btn = QPushButton("Configure API Keys")
        configure_btn.clicked.connect(self._on_configure_api_keys)
        layout.addWidget(configure_btn)
        
        return group
    
    def _create_form_widget(self) -> QWidget:
        """Create the main form widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Case Information
        case_group = QGroupBox("Case Information")
        case_layout = QFormLayout(case_group)
        
        self.case_name_edit = QLineEdit()
        self.case_name_edit.setPlaceholderText("e.g., Smith v. Jones")
        self.case_name_edit.textChanged.connect(self._validate)
        case_layout.addRow("Case Name:*", self.case_name_edit)
        
        self.case_number_edit = QLineEdit()
        self.case_number_edit.setPlaceholderText("e.g., 2025-CV-1234")
        case_layout.addRow("Case Number:", self.case_number_edit)
        
        self.evaluator_edit = QLineEdit()
        self.evaluator_edit.setPlaceholderText("e.g., Dr. Jane Smith")
        case_layout.addRow("Evaluator:", self.evaluator_edit)
        
        layout.addWidget(case_group)
        
        # Subject Information
        subject_group = QGroupBox("Subject Information")
        subject_layout = QFormLayout(subject_group)
        
        self.subject_name_edit = QLineEdit()
        self.subject_name_edit.setPlaceholderText("e.g., John Doe")
        self.subject_name_edit.textChanged.connect(self._validate)
        subject_layout.addRow("Subject Name:*", self.subject_name_edit)
        
        self.dob_edit = QDateEdit()
        self.dob_edit.setCalendarPopup(True)
        self.dob_edit.setDate(QDate.currentDate().addYears(-30))
        self.dob_edit.setDisplayFormat("MM/dd/yyyy")
        subject_layout.addRow("Date of Birth:", self.dob_edit)
        
        self.eval_date_edit = QDateEdit()
        self.eval_date_edit.setCalendarPopup(True)
        self.eval_date_edit.setDate(QDate.currentDate())
        self.eval_date_edit.setDisplayFormat("MM/dd/yyyy")
        subject_layout.addRow("Evaluation Date:", self.eval_date_edit)
        
        layout.addWidget(subject_group)
        
        # Case Description
        desc_group = QGroupBox("Case Description")
        desc_layout = QVBoxLayout(desc_group)
        
        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText(
            "Enter case background, referral reason, and any other relevant information..."
        )
        self.description_edit.setMaximumHeight(120)
        desc_layout.addWidget(self.description_edit)
        
        layout.addWidget(desc_group)
        
        # Project Settings
        settings_group = QGroupBox("Project Settings")
        settings_layout = QFormLayout(settings_group)
        
        # Output directory
        dir_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("Select output directory...")
        self.output_dir_edit.textChanged.connect(self._validate)
        dir_layout.addWidget(self.output_dir_edit)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_output_dir)
        dir_layout.addWidget(browse_btn)
        
        settings_layout.addRow("Output Directory:*", dir_layout)
        
        # Template selection
        self.template_combo = QComboBox()
        self.template_combo.addItems([
            "Standard Competency Evaluation",
            "Criminal Responsibility",
            "Risk Assessment",
            "Juvenile Evaluation",
            "Custom Template"
        ])
        settings_layout.addRow("Report Template:", self.template_combo)
        
        layout.addWidget(settings_group)
        
        return widget
    
    def _create_button_widget(self) -> QWidget:
        """Create the action buttons."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Validation message
        self.validation_label = QLabel()
        self.validation_label.setStyleSheet("color: #d32f2f;")
        layout.addWidget(self.validation_label)
        
        layout.addStretch()
        
        # Cancel button (only for new projects)
        if self.is_new_project:
            cancel_btn = QPushButton("Cancel")
            cancel_btn.clicked.connect(self._on_cancel)
            layout.addWidget(cancel_btn)
        
        # Create/Save button
        self.create_btn = QPushButton("Create Project" if self.is_new_project else "Save Changes")
        self.create_btn.setObjectName("primary")
        self.create_btn.setStyleSheet("""
            QPushButton#primary {
                background-color: #1976d2;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 4px;
            }
            QPushButton#primary:hover {
                background-color: #1565c0;
            }
            QPushButton#primary:disabled {
                background-color: #ccc;
            }
        """)
        self.create_btn.clicked.connect(self._on_create_project)
        layout.addWidget(self.create_btn)
        
        return widget
    
    def _update_api_status(self):
        """Update API key status indicators."""
        # Get settings from parent window
        main_window = self.window()
        if not hasattr(main_window, 'settings'):
            return
        
        for provider, indicator in self.api_indicators.items():
            has_key = main_window.settings.has_api_key(provider)
            
            # Extract base label text (remove existing ✓/✗)
            text = indicator.text()
            if text.startswith(('✓ ', '✗ ')):
                text = text[2:]
            
            if has_key:
                indicator.setStyleSheet("color: #4caf50;")  # Green
                indicator.setText(f"✓ {text}")
            else:
                indicator.setStyleSheet("color: #f44336;")  # Red
                indicator.setText(f"✗ {text}")
    
    def _browse_output_dir(self):
        """Browse for output directory."""
        current = self.output_dir_edit.text() or str(Path.home() / "Documents")
        
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            current,
            QFileDialog.ShowDirsOnly
        )
        
        if dir_path:
            self.output_dir_edit.setText(dir_path)
    
    def _on_configure_api_keys(self):
        """Open API key configuration dialog."""
        from src.new.widgets import APIKeyDialog
        
        # Get settings from parent window
        main_window = self.window()
        if hasattr(main_window, 'settings'):
            if APIKeyDialog.configure_api_keys(main_window.settings, self):
                # After configuration, update status
                self._update_api_status()
        else:
            QMessageBox.warning(
                self,
                "Configuration Error",
                "Unable to access application settings."
            )
    
    def _on_cancel(self):
        """Handle cancel button."""
        reply = QMessageBox.question(
            self,
            "Cancel Project Setup",
            "Are you sure you want to cancel? No project will be created.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # TODO: Signal to main window to go back to welcome screen
            pass
    
    def _on_create_project(self):
        """Handle create/save project."""
        # Validate first
        is_valid, message = self.validate()
        if not is_valid:
            QMessageBox.warning(self, "Validation Error", message)
            return
        
        # Show progress dialog
        progress = QProgressDialog(
            "Creating project...",
            None,  # No cancel button
            0, 0,  # Indeterminate progress
            self
        )
        progress.setWindowTitle("Creating Project")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)  # Show immediately
        progress.show()
        
        # Process events to ensure dialog shows
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()
        
        # Collect metadata
        metadata = ProjectMetadata(
            case_name=self.case_name_edit.text().strip(),
            case_number=self.case_number_edit.text().strip(),
            subject_name=self.subject_name_edit.text().strip(),
            date_of_birth=self.dob_edit.date().toString("yyyy-MM-dd"),
            evaluation_date=self.eval_date_edit.date().toString("yyyy-MM-dd"),
            evaluator=self.evaluator_edit.text().strip(),
            case_description=self.description_edit.toPlainText().strip()
        )
        
        # Prepare results
        results = {
            "metadata": metadata,
            "output_directory": self.output_dir_edit.text(),
            "template": self.template_combo.currentText()
        }
        
        # Save state
        self.save_state()
        
        # Close progress dialog
        progress.close()
        
        # Emit completion signal
        self.completed.emit(results)
    
    def validate(self) -> Tuple[bool, str]:
        """Validate the form data."""
        # Check required fields
        if not self.case_name_edit.text().strip():
            return False, "Case name is required"
        
        if not self.subject_name_edit.text().strip():
            return False, "Subject name is required"
        
        if not self.output_dir_edit.text().strip():
            return False, "Output directory is required"
        
        # Check if output directory exists
        output_path = Path(self.output_dir_edit.text())
        if not output_path.exists():
            return False, "Output directory does not exist"
        
        if not output_path.is_dir():
            return False, "Output path must be a directory"
        
        # Check if we can write to the directory
        try:
            test_file = output_path / ".test_write"
            test_file.touch()
            test_file.unlink()
        except:
            return False, "Cannot write to output directory"
        
        # Check for at least one API key
        # TODO: Implement actual API key checking
        # For now, just warn
        
        return True, ""
    
    def _validate(self):
        """Internal validation that updates UI."""
        is_valid, message = self.validate()
        
        self.validation_label.setText(message)
        self.create_btn.setEnabled(is_valid)
        
        # Emit validation signal
        self.validation_changed.emit(is_valid)
    
    def save_state(self):
        """Save current state to project."""
        if not self.project:
            return
        
        state = {
            "case_name": self.case_name_edit.text(),
            "case_number": self.case_number_edit.text(),
            "evaluator": self.evaluator_edit.text(),
            "subject_name": self.subject_name_edit.text(),
            "date_of_birth": self.dob_edit.date().toString("yyyy-MM-dd"),
            "evaluation_date": self.eval_date_edit.date().toString("yyyy-MM-dd"),
            "case_description": self.description_edit.toPlainText(),
            "output_directory": self.output_dir_edit.text(),
            "template": self.template_combo.currentText()
        }
        
        self.project.save_stage_data("setup", state)
    
    def load_state(self):
        """Load state from project."""
        if not self.project:
            # Set defaults for new project
            self.output_dir_edit.setText(str(Path.home() / "Documents" / "ForensicReports"))
            return
        
        state = self.project.get_stage_data("setup")
        if not state:
            return
        
        # Restore form data
        self.case_name_edit.setText(state.get("case_name", ""))
        self.case_number_edit.setText(state.get("case_number", ""))
        self.evaluator_edit.setText(state.get("evaluator", ""))
        self.subject_name_edit.setText(state.get("subject_name", ""))
        
        if "date_of_birth" in state:
            self.dob_edit.setDate(QDate.fromString(state["date_of_birth"], "yyyy-MM-dd"))
        
        if "evaluation_date" in state:
            self.eval_date_edit.setDate(QDate.fromString(state["evaluation_date"], "yyyy-MM-dd"))
        
        self.description_edit.setPlainText(state.get("case_description", ""))
        self.output_dir_edit.setText(state.get("output_directory", ""))
        
        if "template" in state:
            index = self.template_combo.findText(state["template"])
            if index >= 0:
                self.template_combo.setCurrentIndex(index)