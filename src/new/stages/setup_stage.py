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

from src.new.core import BaseStage, ProjectMetadata, SecureSettings


class ProjectSetupStage(BaseStage):
    """Initial project setup and metadata collection."""
    
    def __init__(self, project=None):
        # Track if this is a new project or editing existing
        self.is_new_project = project is None
        self.settings = SecureSettings()
        
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
        
        # Main form
        form_widget = self._create_form_widget()
        layout.addWidget(form_widget)
        
        # Action buttons
        button_widget = self._create_button_widget()
        layout.addWidget(button_widget)
        
        # Add stretch to push everything to the top
        layout.addStretch()
        
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
        
        # Evaluator name - auto-populated from settings
        self.evaluator_edit = QLineEdit()
        evaluator_name = self.settings.get_setting("evaluator_name", "")
        if evaluator_name:
            self.evaluator_edit.setText(evaluator_name)
            self.evaluator_edit.setReadOnly(True)
            self.evaluator_edit.setStyleSheet("QLineEdit { background-color: #f5f5f5; }")
            self.evaluator_edit.setToolTip("Evaluator name is set in application settings")
        else:
            self.evaluator_edit.setPlaceholderText("Set evaluator name in app settings")
        case_layout.addRow("Evaluator:", self.evaluator_edit)
        
        # Note about evaluator
        if not evaluator_name:
            evaluator_note = QLabel("⚠️ Please set your name in File → Settings")
            evaluator_note.setStyleSheet("color: #ff9800; font-size: 12px;")
            case_layout.addRow("", evaluator_note)
        
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
        
        # Settings button (if evaluator not set)
        evaluator_name = self.settings.get_setting("evaluator_name", "")
        if not evaluator_name:
            settings_btn = QPushButton("Open Settings")
            settings_btn.clicked.connect(self._open_settings)
            layout.addWidget(settings_btn)
        
        return widget
    
    def _browse_output_dir(self):
        """Browse for output directory."""
        # Start from Documents folder
        start_dir = str(Path.home() / "Documents")
        
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            start_dir,
            QFileDialog.ShowDirsOnly
        )
        
        if directory:
            self.output_dir_edit.setText(directory)
    
    def _open_settings(self):
        """Open the settings dialog."""
        from src.new.dialogs import SettingsDialog
        
        dialog = SettingsDialog(self)
        if dialog.exec():
            # Refresh evaluator name after settings change
            evaluator_name = self.settings.get_setting("evaluator_name", "")
            if evaluator_name:
                self.evaluator_edit.setText(evaluator_name)
                self.evaluator_edit.setReadOnly(True)
                self.evaluator_edit.setStyleSheet("QLineEdit { background-color: #f5f5f5; }")
                self.evaluator_edit.setToolTip("Evaluator name is set in application settings")
                
                # Hide the warning and settings button
                self.setup_ui()  # Refresh the UI
                self._validate()  # Re-validate
    
    def validate(self) -> tuple[bool, str]:
        """Check if stage can proceed."""
        # Check required fields
        if not self.case_name_edit.text().strip():
            return False, "Please enter a case name"
        
        if not self.subject_name_edit.text().strip():
            return False, "Please enter the subject's name"
        
        if not self.output_dir_edit.text().strip():
            return False, "Please select an output directory"
        
        # Check if directory exists
        output_dir = Path(self.output_dir_edit.text())
        if not output_dir.exists():
            return False, "Selected output directory does not exist"
        
        # Check evaluator name
        evaluator = self.evaluator_edit.text().strip()
        if not evaluator:
            return False, "Please set your evaluator name in application settings"
        
        return True, ""
    
    def save_state(self):
        """Save current state to project."""
        if not self.project:
            return
        
        # Get evaluator name from settings or form
        evaluator_name = self.settings.get_setting("evaluator_name", "")
        if not evaluator_name:
            evaluator_name = self.evaluator_edit.text().strip()
        
        # Collect all the form data
        metadata = ProjectMetadata(
            case_name=self.case_name_edit.text().strip(),
            case_number=self.case_number_edit.text().strip(),
            subject_name=self.subject_name_edit.text().strip(),
            date_of_birth=self.dob_edit.date().toString("yyyy-MM-dd"),
            evaluation_date=self.eval_date_edit.date().toString("yyyy-MM-dd"),
            evaluator=evaluator_name,
            case_description=self.description_edit.toPlainText().strip()
        )
        
        # Save the data
        self.project.update_metadata(metadata)
        self.project.update_settings(
            template=self.template_combo.currentText(),
            output_directory=self.output_dir_edit.text()
        )
    
    def load_state(self):
        """Load state from project."""
        if not self.project or self.is_new_project:
            # Set default output directory for new projects
            default_dir = str(Path.home() / "Documents" / "Forensic Reports")
            self.output_dir_edit.setText(default_dir)
            return
        
        # Load metadata
        metadata = self.project.project_data.get('metadata', {})
        self.case_name_edit.setText(metadata.get('case_name', ''))
        self.case_number_edit.setText(metadata.get('case_number', ''))
        self.subject_name_edit.setText(metadata.get('subject_name', ''))
        
        # Load dates
        if 'date_of_birth' in metadata:
            dob = QDate.fromString(metadata['date_of_birth'], "yyyy-MM-dd")
            if dob.isValid():
                self.dob_edit.setDate(dob)
        
        if 'evaluation_date' in metadata:
            eval_date = QDate.fromString(metadata['evaluation_date'], "yyyy-MM-dd")
            if eval_date.isValid():
                self.eval_date_edit.setDate(eval_date)
        
        # Load evaluator
        if 'evaluator' in metadata:
            self.evaluator_edit.setText(metadata['evaluator'])
        
        # Load description
        self.description_edit.setPlainText(metadata.get('case_description', ''))
        
        # Load settings
        settings = self.project.project_data.get('settings', {})
        if 'template' in settings:
            index = self.template_combo.findText(settings['template'])
            if index >= 0:
                self.template_combo.setCurrentIndex(index)
        
        if 'output_directory' in settings:
            self.output_dir_edit.setText(settings['output_directory'])
    
    def get_form_data(self) -> Dict[str, Any]:
        """Get all form data for project creation."""
        # Get evaluator name from settings or form
        evaluator_name = self.settings.get_setting("evaluator_name", "")
        if not evaluator_name:
            evaluator_name = self.evaluator_edit.text().strip()
        
        metadata = ProjectMetadata(
            case_name=self.case_name_edit.text().strip(),
            case_number=self.case_number_edit.text().strip(),
            subject_name=self.subject_name_edit.text().strip(),
            date_of_birth=self.dob_edit.date().toString("yyyy-MM-dd"),
            evaluation_date=self.eval_date_edit.date().toString("yyyy-MM-dd"),
            evaluator=evaluator_name,
            case_description=self.description_edit.toPlainText().strip()
        )
        
        return {
            'metadata': metadata,
            'output_directory': self.output_dir_edit.text(),
            'template': self.template_combo.currentText()
        }