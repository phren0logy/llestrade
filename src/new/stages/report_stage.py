"""
Report Generation stage for the new UI.
Handles creation of integrated reports from document summaries.
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QTextEdit, QSplitter, QMessageBox, QAbstractItemView,
    QComboBox, QCheckBox, QFormLayout, QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QFont, QTextCursor

from src.new.core.stage_manager import BaseStage
from src.config.app_config import get_available_providers_and_models, get_configured_llm_provider
from src.core.prompt_manager import PromptManager
from llm import create_provider
from llm.tokens import TokenCounter


class ReportGenerationThread(QThread):
    """Worker thread for generating integrated reports."""
    
    # Signals
    progress = Signal(int, str)  # percent, message
    report_generated = Signal(str, str)  # report_path, report_content
    finished = Signal()
    error = Signal(str)
    status = Signal(str)  # status messages
    
    def __init__(self,
                 summaries_dir: Path,
                 output_dir: Path,
                 subject_name: str,
                 subject_dob: str,
                 case_info: str,
                 provider_id: str,
                 model_name: str,
                 report_type: str = "integrated_analysis"):
        super().__init__()
        self.summaries_dir = summaries_dir
        self.output_dir = output_dir
        self.subject_name = subject_name
        self.subject_dob = subject_dob
        self.case_info = case_info
        self.provider_id = provider_id
        self.model_name = model_name
        self.report_type = report_type
        self._is_running = True
        self.logger = logging.getLogger(__name__)
        self.llm_provider = None
        
    def stop(self):
        """Stop the worker thread."""
        self._is_running = False
        
    def run(self):
        """Generate the integrated report."""
        try:
            # Initialize LLM provider
            self.status.emit("Initializing LLM provider...")
            provider_info = get_configured_llm_provider(
                provider_id_override=self.provider_id,
                model_override=self.model_name
            )
            
            if not provider_info or not provider_info.get("provider"):
                raise Exception(f"Failed to initialize {self.provider_id} provider")
                
            self.llm_provider = provider_info["provider"]
            provider_label = provider_info.get("provider_label", self.provider_id)
            effective_model = provider_info.get("effective_model_name", self.model_name)
            
            self.status.emit(f"Using {provider_label} ({effective_model})")
            
            # Load all summaries
            self.progress.emit(10, "Loading document summaries...")
            summaries = self._load_summaries()
            
            if not summaries:
                raise Exception("No summaries found. Please run the Analysis stage first.")
            
            self.status.emit(f"Found {len(summaries)} summaries to integrate")
            
            # Combine summaries
            self.progress.emit(20, "Combining summaries...")
            combined_summaries = self._combine_summaries(summaries)
            
            # Get prompt template
            self.progress.emit(30, "Preparing prompt...")
            prompt_manager = PromptManager()
            
            if self.report_type == "integrated_analysis":
                prompt_template = prompt_manager.get_prompt_template("integrated_analysis_prompt")
                
                # Format the prompt with case information
                system_prompt = prompt_template["system_prompt"]
                user_prompt = prompt_template["user_prompt"].format(
                    subject_name=self.subject_name,
                    subject_dob=self.subject_dob,
                    case_info=self.case_info,
                    combined_summaries=combined_summaries
                )
            else:
                # For other report types, use report_generation_instructions
                template = prompt_manager.get_template("report_generation_instructions")
                system_prompt = "You are a forensic psychiatrist creating a professional evaluation report."
                user_prompt = template + f"\n\n<transcript>\n{combined_summaries}\n</transcript>"
            
            # Generate the report
            self.progress.emit(40, "Generating integrated report...")
            self.status.emit("Sending request to LLM (this may take a few minutes)...")
            
            # Count tokens
            total_prompt = system_prompt + "\n" + user_prompt
            token_count = TokenCounter.count(total_prompt, self.provider_id)
            self.status.emit(f"Prompt tokens: {token_count['total']:,}")
            
            # Generate response
            response = self.llm_provider.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.3  # Lower temperature for more consistent reports
            )
            
            if not response:
                raise Exception("No response received from LLM")
            
            # Save the report
            self.progress.emit(80, "Saving report...")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_filename = f"integrated_report_{timestamp}.md"
            report_path = self.output_dir / report_filename
            
            # Ensure output directory exists
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            # Save to file
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(f"# Integrated Analysis Report\n\n")
                f.write(f"**Subject**: {self.subject_name}\n")
                f.write(f"**Date of Birth**: {self.subject_dob}\n")
                f.write(f"**Report Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"**Provider**: {provider_label} ({effective_model})\n\n")
                f.write("---\n\n")
                f.write(response)
            
            self.progress.emit(100, "Report generated successfully!")
            self.report_generated.emit(str(report_path), response)
            
        except Exception as e:
            self.logger.error(f"Error generating report: {e}", exc_info=True)
            self.error.emit(str(e))
        finally:
            self.finished.emit()
    
    def _load_summaries(self) -> List[Dict[str, str]]:
        """Load all summaries from the summaries directory."""
        summaries = []
        
        if not self.summaries_dir.exists():
            return summaries
        
        # Look for summary files
        for summary_file in sorted(self.summaries_dir.glob("*_summary.md")):
            try:
                with open(summary_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                summaries.append({
                    'filename': summary_file.name,
                    'content': content,
                    'source': summary_file.stem.replace('_summary', '')
                })
            except Exception as e:
                self.logger.warning(f"Failed to load summary {summary_file}: {e}")
        
        return summaries
    
    def _combine_summaries(self, summaries: List[Dict[str, str]]) -> str:
        """Combine all summaries into a single document."""
        combined = []
        
        for summary in summaries:
            combined.append(f"## Summary: {summary['source']}\n")
            combined.append(summary['content'])
            combined.append("\n---\n")
        
        return "\n".join(combined)


class ReportGenerationStage(BaseStage):
    """Stage for generating integrated reports from summaries."""
    
    def __init__(self, project):
        self.worker = None
        self.available_providers = {}
        self.report_content = ""
        super().__init__(project)
        
    def setup_ui(self):
        """Create the UI for report generation."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # Title
        title = QLabel("Generate Integrated Report")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)
        
        # Description
        desc = QLabel("Create a comprehensive report by integrating all document summaries.")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Configuration section
        config_group = QGroupBox("Report Configuration")
        config_layout = QFormLayout()
        
        # Report type selection
        self.report_type_group = QButtonGroup()
        
        self.integrated_radio = QRadioButton("Integrated Analysis (Comprehensive)")
        self.integrated_radio.setChecked(True)
        self.report_type_group.addButton(self.integrated_radio, 0)
        
        self.standard_radio = QRadioButton("Standard Report (Template-based)")
        self.report_type_group.addButton(self.standard_radio, 1)
        
        report_type_layout = QVBoxLayout()
        report_type_layout.addWidget(self.integrated_radio)
        report_type_layout.addWidget(self.standard_radio)
        config_layout.addRow("Report Type:", report_type_layout)
        
        # LLM Provider selection
        self.provider_combo = QComboBox()
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        config_layout.addRow("LLM Provider:", self.provider_combo)
        
        # Model selection
        self.model_combo = QComboBox()
        config_layout.addRow("Model:", self.model_combo)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # Progress section
        progress_group = QGroupBox("Generation Progress")
        progress_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)
        
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(150)
        progress_layout.addWidget(self.status_text)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # Report preview section
        preview_group = QGroupBox("Report Preview")
        preview_layout = QVBoxLayout()
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        preview_layout.addWidget(self.preview_text)
        
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group, 1)  # Give it more space
        
        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.generate_button = QPushButton("Generate Report")
        self.generate_button.clicked.connect(self._generate_report)
        button_layout.addWidget(self.generate_button)
        
        self.save_button = QPushButton("Save Report As...")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save_report_as)
        button_layout.addWidget(self.save_button)
        
        layout.addLayout(button_layout)
        
        # Load available providers
        self._load_providers()
        
        # Initial validation
        self._validate()
        
    def _load_providers(self):
        """Load available LLM providers."""
        try:
            providers_and_models = get_available_providers_and_models()
            
            # Clear and populate provider combo
            self.provider_combo.clear()
            self.model_combo.clear()
            
            for provider_info in providers_and_models:
                display_name = provider_info["display_name"]
                provider_id = provider_info["id"]
                model = provider_info["model"]
                
                # Add to combo with provider info as data
                self.provider_combo.addItem(display_name, {
                    "provider_id": provider_id,
                    "model": model
                })
            
            # Select first provider if available
            if self.provider_combo.count() > 0:
                self.provider_combo.setCurrentIndex(0)
                self._on_provider_changed(self.provider_combo.currentText())
                    
        except Exception as e:
            self.logger.error(f"Failed to load providers: {e}")
            
    def _on_provider_changed(self, provider_name: str):
        """Handle provider selection change."""
        if not provider_name:
            return
            
        # Get provider data from current selection
        provider_data = self.provider_combo.currentData()
        if not provider_data:
            return
            
        # Update model combo with the single model from settings
        self.model_combo.clear()
        model = provider_data["model"]
        self.model_combo.addItem(model, model)
        self.model_combo.setCurrentIndex(0)
                
        self._validate()
        
    def _generate_report(self):
        """Start report generation."""
        if self.worker and self.worker.isRunning():
            return
            
        # Check if project exists
        if not self.project:
            QMessageBox.warning(self, "No Project", "Please create or load a project first.")
            return
            
        # Get configuration
        provider_data = self.provider_combo.currentData()
        if not provider_data:
            QMessageBox.warning(self, "No Provider", "Please select an LLM provider.")
            return
            
        provider_id = provider_data["provider_id"]
        model_name = provider_data["model"]
        report_type = "integrated_analysis" if self.integrated_radio.isChecked() else "standard"
        
        # Get paths
        project_dir = Path(self.project.project_data['paths']['base'])
        summaries_dir = project_dir / "summaries"
        reports_dir = project_dir / "reports"
        
        # Get case information
        metadata = self.project.project_data.get('metadata', {})
        subject_name = metadata.get('subject_name', 'Unknown')
        subject_dob = metadata.get('date_of_birth', 'Unknown')
        case_info = metadata.get('case_description', '')
        
        # Create worker thread
        self.worker = ReportGenerationThread(
            summaries_dir=summaries_dir,
            output_dir=reports_dir,
            subject_name=subject_name,
            subject_dob=subject_dob,
            case_info=case_info,
            provider_id=provider_id,
            model_name=model_name,
            report_type=report_type
        )
        
        # Connect signals
        self.worker.progress.connect(self._update_progress)
        self.worker.status.connect(self._update_status)
        self.worker.report_generated.connect(self._on_report_generated)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self._on_finished)
        
        # Update UI
        self.generate_button.setEnabled(False)
        self.status_text.clear()
        self.preview_text.clear()
        self.progress_bar.setValue(0)
        
        # Start generation
        self.worker.start()
        
    def _update_progress(self, value: int, message: str):
        """Update progress bar and status."""
        self.progress_bar.setValue(value)
        self._update_status(message)
        
    def _update_status(self, message: str):
        """Add status message."""
        self.status_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        # Auto-scroll to bottom
        cursor = self.status_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.status_text.setTextCursor(cursor)
        
    def _on_report_generated(self, report_path: str, report_content: str):
        """Handle successful report generation."""
        self.report_content = report_content
        self.preview_text.setPlainText(report_content)
        self.save_button.setEnabled(True)
        
        # Update project state
        if self.project:
            stage_data = self.project.get_stage_data('report') or {}
            stage_data['last_report'] = report_path
            stage_data['generated_at'] = datetime.now().isoformat()
            self.project.update_stage_data('report', stage_data)
            
        self._update_status(f"Report saved to: {report_path}")
        
    def _on_error(self, error_message: str):
        """Handle generation error."""
        self._update_status(f"ERROR: {error_message}")
        QMessageBox.critical(self, "Report Generation Error", error_message)
        
    def _on_finished(self):
        """Handle worker finished."""
        self.generate_button.setEnabled(True)
        self.worker = None
        self._validate()
        
    def _save_report_as(self):
        """Save report with custom filename."""
        # Implementation for save as dialog
        pass
        
    def validate(self) -> tuple[bool, str]:
        """Check if stage can proceed."""
        # Check if project exists
        if not self.project:
            return False, "No project loaded"
            
        # Check if summaries exist
        project_dir = Path(self.project.project_data['paths']['base'])
        summaries_dir = project_dir / "summaries"
        
        if not summaries_dir.exists() or not any(summaries_dir.glob("*_summary.md")):
            return False, "No document summaries found. Please complete the Analysis stage first."
            
        # Check if provider is selected
        if not self.provider_combo.currentData():
            return False, "Please select an LLM provider"
            
        # Check if report has been generated
        reports_dir = project_dir / "reports"
        if reports_dir.exists() and any(reports_dir.glob("*.md")):
            return True, "Report generated successfully"
            
        return False, "Please generate a report before proceeding"
        
    def save_state(self):
        """Save current state to project."""
        if not self.project:
            return
            
        stage_data = {
            'provider': self.provider_combo.currentData(),
            'model': self.model_combo.currentText(),
            'report_type': 'integrated_analysis' if self.integrated_radio.isChecked() else 'standard',
            'report_content': self.report_content
        }
        
        self.project.update_stage_data('report', stage_data)
        
    def load_state(self):
        """Load state from project."""
        if not self.project:
            return
            
        stage_data = self.project.get_stage_data('report') or {}
        
        # Restore provider selection
        if 'provider' in stage_data:
            index = self.provider_combo.findData(stage_data['provider'])
            if index >= 0:
                self.provider_combo.setCurrentIndex(index)
                
        # Restore model selection
        if 'model' in stage_data:
            index = self.model_combo.findText(stage_data['model'])
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
                
        # Restore report type
        if stage_data.get('report_type') == 'standard':
            self.standard_radio.setChecked(True)
            
        # Restore report content if available
        if 'report_content' in stage_data:
            self.report_content = stage_data['report_content']
            self.preview_text.setPlainText(self.report_content)
            self.save_button.setEnabled(bool(self.report_content))
            
    def cleanup(self):
        """Clean up resources when leaving stage."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)
            
        super().cleanup()