"""
Workflow indicator component for the Forensic Psych Report Drafter.
Provides a visual representation of workflow steps and their status.
"""

import os
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGroupBox, QHBoxLayout, QVBoxLayout, QLabel


class WorkflowIndicator(QGroupBox):
    """
    A reusable workflow indicator component that visually represents
    steps in a process and their current status.
    """
    
    # Style definitions
    STYLES = {
        "active": "background-color: #4CAF50; color: white; border: 1px solid #388E3C; border-radius: 4px; padding: 8px;",
        "pending": "background-color: #FFF8E1; color: #795548; border: 1px solid #FFECB3; border-radius: 4px; padding: 8px;",
        "disabled": "background-color: #F5F5F5; color: #9E9E9E; border: 1px solid #E0E0E0; border-radius: 4px; padding: 8px;",
        "complete": "background-color: #C8E6C9; color: #2E7D32; border: 1px solid #A5D6A7; border-radius: 4px; padding: 8px;",
        "arrow": "font-size: 16px; font-weight: bold; padding: 4px;",
        "arrow_active": "color: #4CAF50; font-size: 16px; font-weight: bold; padding: 4px;",
        "arrow_disabled": "color: #9E9E9E; font-size: 16px; font-weight: bold; padding: 4px;",
        "status": "color: #666; font-style: italic; padding: 4px;"
    }
    
    def __init__(self, title="Processing Workflow", steps=None):
        """
        Initialize the workflow indicator with steps.
        
        Args:
            title: Title for the group box
            steps: List of step names to display
        """
        super().__init__(title)
        
        # If no steps provided, use default
        self.steps = steps or ["1. Select Files", "2. Process Files", "3. Integration"]
        
        # Set up UI
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the UI components for the workflow indicator."""
        workflow_layout = QHBoxLayout()
        
        # Create step labels and arrows
        self.step_labels = []
        self.arrows = []
        
        for i, step in enumerate(self.steps):
            # Create step label
            label = QLabel(step)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(self.STYLES["disabled"])
            self.step_labels.append(label)
            
            # Add to layout
            workflow_layout.addWidget(label)
            
            # Add arrow if not the last step
            if i < len(self.steps) - 1:
                arrow = QLabel("→")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow.setStyleSheet(self.STYLES["arrow_disabled"])
                self.arrows.append(arrow)
                workflow_layout.addWidget(arrow)
        
        # Add status summary label
        self.status_label = QLabel("⏳ Waiting for input")
        self.status_label.setStyleSheet(self.STYLES["status"])
        
        # Create main layout
        main_layout = QVBoxLayout()
        main_layout.addLayout(workflow_layout)
        main_layout.addWidget(self.status_label)
        
        self.setLayout(main_layout)
    
    def update_status(self, current_step, completed_steps=None, status_message=None):
        """
        Update the workflow status display.
        
        Args:
            current_step: Index of the current active step (0-based)
            completed_steps: List of indices of completed steps
            status_message: Optional status message to display
        """
        completed_steps = completed_steps or []
        
        # Reset all steps to disabled state
        for i, label in enumerate(self.step_labels):
            if i in completed_steps:
                label.setStyleSheet(self.STYLES["complete"])
            elif i == current_step:
                label.setStyleSheet(self.STYLES["active"])
            elif i < current_step:
                label.setStyleSheet(self.STYLES["pending"])
            else:
                label.setStyleSheet(self.STYLES["disabled"])
        
        # Update arrows
        for i, arrow in enumerate(self.arrows):
            if i < current_step or i in completed_steps:
                arrow.setStyleSheet(self.STYLES["arrow_active"])
            else:
                arrow.setStyleSheet(self.STYLES["arrow_disabled"])
        
        # Update status message if provided
        if status_message:
            self.status_label.setText(status_message)
    
    def set_status_message(self, message):
        """Set just the status message without changing the workflow state."""
        self.status_label.setText(message)
