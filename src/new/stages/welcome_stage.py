"""
Welcome stage for the new UI.
Shows recent projects, API key status, and quick start options.
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QMessageBox, QFileDialog, QGroupBox,
    QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QFont, QPalette, QIcon

from src.new.core import SecureSettings, ProjectManager
from src.new.core.stage_manager import BaseStage


class WelcomeStage(BaseStage):
    """Welcome screen with recent projects and quick actions."""
    
    # Signals
    new_project_requested = Signal()
    project_opened = Signal(Path)  # project path
    
    def __init__(self, project=None):
        # Initialize attributes before calling super
        self.settings = SecureSettings()
        # Don't need project for welcome screen
        super().__init__(None)
        
    def setup_ui(self):
        """Create the welcome UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # Header
        header = self._create_header()
        layout.addWidget(header)
        
        # Main content area with two columns
        content_layout = QHBoxLayout()
        content_layout.setSpacing(30)
        
        # Left column - Recent projects
        recent_widget = self._create_recent_projects_widget()
        content_layout.addWidget(recent_widget, 2)  # 2/3 width
        
        # Right column - Quick actions and status
        right_column = QVBoxLayout()
        right_column.setSpacing(20)
        
        # Quick actions
        actions_widget = self._create_quick_actions_widget()
        right_column.addWidget(actions_widget)
        
        # API key status
        api_status_widget = self._create_api_status_widget()
        right_column.addWidget(api_status_widget)
        
        # Quick start guide
        guide_widget = self._create_quick_start_widget()
        right_column.addWidget(guide_widget)
        
        right_column.addStretch()
        content_layout.addLayout(right_column, 1)  # 1/3 width
        
        layout.addLayout(content_layout)
        layout.addStretch()
        
        # Update API status periodically
        self.api_timer = QTimer()
        self.api_timer.timeout.connect(self._update_api_status)
        self.api_timer.start(5000)  # Check every 5 seconds
        
    def _create_header(self) -> QWidget:
        """Create the welcome header."""
        header = QWidget()
        layout = QVBoxLayout(header)
        
        # Title
        title = QLabel("Welcome to Forensic Report Drafter")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(24)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel("Create professional forensic psychological reports with AI assistance")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #666; font-size: 14px;")
        layout.addWidget(subtitle)
        
        return header
        
    def _create_recent_projects_widget(self) -> QWidget:
        """Create the recent projects section."""
        group = QGroupBox("Recent Projects")
        layout = QVBoxLayout(group)
        
        # Get recent projects
        recent_projects = self.settings.get_recent_projects()
        
        if not recent_projects:
            # No recent projects
            empty_label = QLabel("No recent projects")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("color: #999; padding: 40px;")
            layout.addWidget(empty_label)
        else:
            # Create scrollable list of projects
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setStyleSheet("QScrollArea { border: none; }")
            
            container = QWidget()
            grid = QGridLayout(container)
            grid.setSpacing(10)
            
            # Add project cards
            for i, project_info in enumerate(recent_projects[:6]):  # Show max 6
                card = self._create_project_card(project_info)
                row = i // 2
                col = i % 2
                grid.addWidget(card, row, col)
            
            scroll.setWidget(container)
            layout.addWidget(scroll)
        
        return group
        
    def _create_project_card(self, project_info: Dict) -> QWidget:
        """Create a project card widget."""
        card = QFrame()
        card.setFrameStyle(QFrame.Box)
        card.setStyleSheet("""
            QFrame {
                border: 1px solid #ddd;
                border-radius: 8px;
                background-color: white;
                padding: 15px;
            }
            QFrame:hover {
                border-color: #2196f3;
                background-color: #f5f5f5;
            }
        """)
        card.setCursor(Qt.PointingHandCursor)
        
        layout = QVBoxLayout(card)
        
        # Project name
        name_label = QLabel(project_info.get('name', 'Unnamed Project'))
        font = name_label.font()
        font.setBold(True)
        font.setPointSize(12)
        name_label.setFont(font)
        layout.addWidget(name_label)
        
        # Case info
        case_name = project_info.get('metadata', {}).get('case_name', 'No case name')
        case_label = QLabel(f"Case: {case_name}")
        case_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(case_label)
        
        # Last modified
        last_modified = project_info.get('last_modified', '')
        if last_modified:
            try:
                dt = datetime.fromisoformat(last_modified)
                time_str = dt.strftime("%b %d, %Y at %I:%M %p")
                time_label = QLabel(f"Modified: {time_str}")
                time_label.setStyleSheet("color: #999; font-size: 10px;")
                layout.addWidget(time_label)
            except:
                pass
        
        # Path (hidden, for clicking)
        path = Path(project_info.get('path', ''))
        
        # Make card clickable
        card.mousePressEvent = lambda e: self._open_project(path)
        
        return card
        
    def _create_quick_actions_widget(self) -> QWidget:
        """Create quick actions section."""
        group = QGroupBox("Quick Actions")
        layout = QVBoxLayout(group)
        
        # New Project button
        new_btn = QPushButton("📄 New Project")
        new_btn.setMinimumHeight(50)
        new_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196f3;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
        """)
        new_btn.clicked.connect(self._on_new_project)
        layout.addWidget(new_btn)
        
        # Open Project button
        open_btn = QPushButton("📂 Open Project")
        open_btn.setMinimumHeight(40)
        open_btn.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: #2196f3;
                border: 2px solid #2196f3;
                border-radius: 4px;
                font-size: 14px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
            }
        """)
        open_btn.clicked.connect(self._on_open_project)
        layout.addWidget(open_btn)
        
        return group
        
    def _create_api_status_widget(self) -> QWidget:
        """Create API key status section."""
        group = QGroupBox("API Key Status")
        self.api_layout = QVBoxLayout(group)
        
        # Will be populated by _update_api_status
        self._update_api_status()
        
        # Configure button
        config_btn = QPushButton("Configure API Keys")
        config_btn.clicked.connect(self._on_configure_api_keys)
        self.api_layout.addWidget(config_btn)
        
        return group
        
    def _create_quick_start_widget(self) -> QWidget:
        """Create quick start guide section."""
        group = QGroupBox("Quick Start Guide")
        layout = QVBoxLayout(group)
        
        steps = [
            "1. Configure your API keys",
            "2. Create a new project or open existing",
            "3. Import documents (PDF, Word, text)",
            "4. Process and analyze content",
            "5. Generate and refine your report"
        ]
        
        for step in steps:
            label = QLabel(step)
            label.setWordWrap(True)
            label.setStyleSheet("padding: 2px 0;")
            layout.addWidget(label)
        
        return group
        
    def _update_api_status(self):
        """Update API key status display."""
        # Clear existing status items (except configure button)
        while self.api_layout.count() > 1:
            item = self.api_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        providers = [
            ('anthropic', 'Anthropic (Claude)', '🤖'),
            ('gemini', 'Google Gemini', '✨'),
            ('azure_openai', 'Azure OpenAI', '🔷')
        ]
        
        for provider_id, display_name, icon in providers:
            status_layout = QHBoxLayout()
            
            # Icon and name
            name_label = QLabel(f"{icon} {display_name}")
            status_layout.addWidget(name_label)
            
            # Status indicator
            has_key = self.settings.has_api_key(provider_id)
            status_label = QLabel("✓ Configured" if has_key else "✗ Not configured")
            status_label.setStyleSheet(
                "color: #4caf50;" if has_key else "color: #f44336;"
            )
            status_layout.addStretch()
            status_layout.addWidget(status_label)
            
            self.api_layout.insertLayout(self.api_layout.count() - 1, status_layout)
    
    def _on_new_project(self):
        """Handle new project request."""
        self.new_project_requested.emit()
        
    def _on_open_project(self):
        """Handle open project request."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            str(Path.home()),
            "Forensic Report Project (*.frpd)"
        )
        
        if file_path:
            self._open_project(Path(file_path))
            
    def _open_project(self, project_path: Path):
        """Open a specific project."""
        if not project_path.exists():
            QMessageBox.warning(
                self,
                "Project Not Found",
                f"The project file no longer exists:\n{project_path}"
            )
            # Remove from recent projects
            self.settings.remove_recent_project(str(project_path))
            self._update_recent_projects()
            return
            
        self.project_opened.emit(project_path)
        
    def _on_configure_api_keys(self):
        """Open API key configuration dialog."""
        from src.new.widgets import APIKeyDialog
        dialog = APIKeyDialog(self)
        if dialog.exec():
            # Update status after configuration
            self._update_api_status()
            
    def _update_recent_projects(self):
        """Refresh the recent projects display."""
        # Re-create the entire widget
        # This is called after removing a non-existent project
        old_widget = self.findChild(QGroupBox, "Recent Projects")
        if old_widget:
            # Find its position in parent layout
            parent_layout = old_widget.parent().layout()
            if parent_layout:
                index = parent_layout.indexOf(old_widget)
                parent_layout.removeWidget(old_widget)
                old_widget.deleteLater()
                
                # Create new widget and insert at same position
                new_widget = self._create_recent_projects_widget()
                parent_layout.insertWidget(index, new_widget, 2)
    
    def validate(self) -> tuple[bool, str]:
        """Welcome stage is always valid."""
        return True, ""
    
    def save_state(self):
        """No state to save for welcome."""
        pass
    
    def load_state(self):
        """No state to load for welcome."""
        pass
    
    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, 'api_timer'):
            self.api_timer.stop()
        super().cleanup()