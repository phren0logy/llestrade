"""
Workflow indicator component for the Forensic Psych Report Drafter.
Provides a visual representation of workflow steps and their status.
"""

import os
from enum import Enum
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QVBoxLayout, QLabel


class WorkflowStep(Enum):
    """Enum representing different workflow steps."""
    SELECT_FILES = "select_files"
    PROCESS_PDFS = "process_pdfs"
    SELECT_MARKDOWN = "select_markdown"
    SUMMARIZE_LLM = "summarize_llm"
    COMBINE_SUMMARIES = "combine_summaries"
    INTEGRATE_ANALYSIS = "integrate_analysis"


class WorkflowIndicator(QGroupBox):
    """
    A reusable workflow indicator component that visually represents
    the current status of a multi-step workflow.
    """

    def __init__(self, parent=None):
        """Initialize the workflow indicator."""
        super().__init__("Workflow Progress", parent)
        
        # Initialize state variables
        self.steps = {}
        self.step_labels = {}
        self.step_statuses = {}
        
        # Setup layout
        self.main_layout = QHBoxLayout()
        self.setLayout(self.main_layout)
        
    def add_step(self, step_id, title, description=""):
        """Add a workflow step to the indicator.
        
        Args:
            step_id: Unique identifier for the step
            title: Display title for the step
            description: Optional description of the step
        """
        # Create step layout
        step_layout = QVBoxLayout()
        
        # Create step label
        step_label = QLabel(f"{title}")
        step_label.setStyleSheet("font-weight: bold;")
        step_layout.addWidget(step_label)
        
        # Create status label
        status_label = QLabel("Not Started")
        status_label.setStyleSheet("color: #888;")
        step_layout.addWidget(status_label)
        
        # Store references
        self.steps[step_id] = step_layout
        self.step_labels[step_id] = status_label
        self.step_statuses[step_id] = "not_started"
        
        # Add to main layout
        self.main_layout.addLayout(step_layout)
        
        # Add separator if not the last step
        if len(self.steps) > 1:
            separator = QLabel("→")
            separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
            separator.setStyleSheet("font-weight: bold; font-size: 16px;")
            self.main_layout.insertWidget(self.main_layout.count()-1, separator)
            
    def update_status(self, step_id, status):
        """Update the status of a workflow step.
        
        Args:
            step_id: The step ID to update
            status: New status ("not_started", "in_progress", "complete", "error", "partial")
        """
        if step_id not in self.step_labels:
            print(f"Warning: Step ID {step_id} not found in workflow indicator")
            return
            
        self.step_statuses[step_id] = status
        status_label = self.step_labels[step_id]
        
        # Update label text and style based on status
        if status == "not_started":
            status_label.setText("Not Started")
            status_label.setStyleSheet("color: #888;")
        elif status == "in_progress":
            status_label.setText("In Progress")
            status_label.setStyleSheet("color: #2c7fb8; font-weight: bold;")
        elif status == "complete":
            status_label.setText("Complete ✓")
            status_label.setStyleSheet("color: #2ca05a; font-weight: bold;")
        elif status == "error":
            status_label.setText("Error ✗")
            status_label.setStyleSheet("color: #c0392b; font-weight: bold;")
        elif status == "partial":
            status_label.setText("Partial ⚠")
            status_label.setStyleSheet("color: #f39c12; font-weight: bold;")
            
    def set_status_message(self, message):
        """Set an overall status message for the workflow.
        
        Args:
            message: Status message to display
        """
        # This could be extended to add an overall status message to the component
        pass
