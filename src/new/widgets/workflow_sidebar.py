"""
Workflow sidebar widget for the new UI.
Shows stage progress and navigation.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QPainterPath, QPen, QBrush, QColor, QFont


class WorkflowSidebar(QWidget):
    """Sidebar showing workflow progress and navigation."""
    
    # Signals
    stage_clicked = Signal(str)  # stage name
    
    # Stage configuration
    STAGES = [
        {
            'id': 'setup',
            'name': 'Project Setup',
            'description': 'Configure case details',
            'icon': '📋',
            'estimate': '2 min'
        },
        {
            'id': 'import',
            'name': 'Import Documents',
            'description': 'Add source documents',
            'icon': '📁',
            'estimate': '5 min'
        },
        {
            'id': 'process',
            'name': 'Process Documents',
            'description': 'Convert and extract text',
            'icon': '⚙️',
            'estimate': '10-30 min'
        },
        {
            'id': 'analyze',
            'name': 'Analyze Content',
            'description': 'Generate summaries',
            'icon': '🔍',
            'estimate': '15-45 min'
        },
        {
            'id': 'generate',
            'name': 'Generate Report',
            'description': 'Create final report',
            'icon': '📄',
            'estimate': '5-10 min'
        },
        {
            'id': 'refine',
            'name': 'Refine & Export',
            'description': 'Edit and finalize',
            'icon': '✏️',
            'estimate': '10-20 min'
        }
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        
        # Stage states
        self.stage_states: Dict[str, str] = {}  # id -> 'pending'|'current'|'completed'
        self.stage_widgets: Dict[str, 'StageWidget'] = {}
        self.clickable_stages: List[str] = []
        
        # Setup UI
        self.setup_ui()
        
        # Initialize all stages as pending
        for stage in self.STAGES:
            self.set_stage_state(stage['id'], 'pending')
    
    def setup_ui(self):
        """Create the sidebar UI."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = self._create_header()
        layout.addWidget(header)
        
        # Scroll area for stages
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #f5f5f5;
            }
        """)
        
        # Stage container
        self.stage_container = QWidget()
        self.stage_layout = QVBoxLayout(self.stage_container)
        self.stage_layout.setContentsMargins(0, 20, 0, 20)
        self.stage_layout.setSpacing(0)
        
        # Create stage widgets
        for i, stage in enumerate(self.STAGES):
            stage_widget = StageWidget(
                stage_id=stage['id'],
                name=stage['name'],
                description=stage['description'],
                icon=stage['icon'],
                estimate=stage['estimate'],
                is_first=i == 0,
                is_last=i == len(self.STAGES) - 1
            )
            stage_widget.clicked.connect(self._on_stage_clicked)
            
            self.stage_widgets[stage['id']] = stage_widget
            self.stage_layout.addWidget(stage_widget)
        
        scroll.setWidget(self.stage_container)
        layout.addWidget(scroll)
        
        # Footer with time estimate
        footer = self._create_footer()
        layout.addWidget(footer)
        
        # Set fixed width
        self.setFixedWidth(300)
    
    def _create_header(self) -> QWidget:
        """Create the header widget."""
        header = QWidget()
        header.setStyleSheet("""
            QWidget {
                background-color: #1976d2;
                color: white;
                padding: 20px;
            }
        """)
        
        layout = QVBoxLayout(header)
        
        title = QLabel("Workflow Progress")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        self.progress_label = QLabel("Not started")
        self.progress_label.setStyleSheet("font-size: 14px; opacity: 0.9;")
        layout.addWidget(self.progress_label)
        
        return header
    
    def _create_footer(self) -> QWidget:
        """Create the footer widget."""
        footer = QWidget()
        footer.setStyleSheet("""
            QWidget {
                background-color: white;
                border-top: 1px solid #ddd;
                padding: 15px;
            }
        """)
        
        layout = QVBoxLayout(footer)
        
        # Time estimate
        estimate_label = QLabel("Estimated Time")
        estimate_label.setStyleSheet("font-size: 12px; color: #666;")
        layout.addWidget(estimate_label)
        
        self.total_estimate_label = QLabel("45-90 minutes")
        self.total_estimate_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.total_estimate_label)
        
        # Progress percentage
        self.percentage_label = QLabel("0% Complete")
        self.percentage_label.setStyleSheet("font-size: 12px; color: #666; margin-top: 10px;")
        layout.addWidget(self.percentage_label)
        
        return footer
    
    def set_stage_state(self, stage_id: str, state: str):
        """Set the state of a stage."""
        if stage_id not in self.stage_widgets:
            return
        
        self.stage_states[stage_id] = state
        self.stage_widgets[stage_id].set_state(state)
        
        # Update clickability based on completed stages
        self._update_clickable_stages()
        
        # Update progress
        self._update_progress()
    
    def set_stage_progress(self, progress: Dict[str, str]):
        """Update all stage states at once."""
        for stage_id, state in progress.items():
            self.set_stage_state(stage_id, state)
    
    def _update_clickable_stages(self):
        """Update which stages are clickable."""
        self.clickable_stages = []
        
        # Always allow clicking completed stages and current stage
        for stage_id, state in self.stage_states.items():
            if state in ['completed', 'current']:
                self.clickable_stages.append(stage_id)
        
        # Update widget clickability
        for stage_id, widget in self.stage_widgets.items():
            widget.set_clickable(stage_id in self.clickable_stages)
    
    def _update_progress(self):
        """Update progress indicators."""
        # Count completed stages
        completed = sum(1 for state in self.stage_states.values() if state == 'completed')
        total = len(self.STAGES)
        
        # Update header
        if completed == 0:
            self.progress_label.setText("Ready to start")
        elif completed == total:
            self.progress_label.setText("All stages completed!")
        else:
            current_stage = next((s for s in self.STAGES if self.stage_states.get(s['id']) == 'current'), None)
            if current_stage:
                self.progress_label.setText(f"Current: {current_stage['name']}")
            else:
                self.progress_label.setText(f"{completed} of {total} stages completed")
        
        # Update percentage
        percentage = int((completed / total) * 100)
        self.percentage_label.setText(f"{percentage}% Complete")
    
    def _on_stage_clicked(self, stage_id: str):
        """Handle stage click."""
        if stage_id in self.clickable_stages:
            self.stage_clicked.emit(stage_id)


class StageWidget(QWidget):
    """Individual stage widget in the sidebar."""
    
    clicked = Signal(str)  # stage_id
    
    def __init__(self, stage_id: str, name: str, description: str, 
                 icon: str, estimate: str, is_first: bool = False, 
                 is_last: bool = False, parent=None):
        super().__init__(parent)
        
        self.stage_id = stage_id
        self.name = name
        self.description = description
        self.icon = icon
        self.estimate = estimate
        self.is_first = is_first
        self.is_last = is_last
        
        self.state = 'pending'
        self.is_clickable = False
        self.is_hovered = False
        
        self.setup_ui()
        self.setMouseTracking(True)
    
    def setup_ui(self):
        """Create the stage widget UI."""
        self.setFixedHeight(100)
        self.setCursor(Qt.ArrowCursor)
    
    def set_state(self, state: str):
        """Set the stage state."""
        self.state = state
        self.update()
    
    def set_clickable(self, clickable: bool):
        """Set whether the stage is clickable."""
        self.is_clickable = clickable
        self.setCursor(Qt.PointingHandCursor if clickable else Qt.ArrowCursor)
        self.update()
    
    def paintEvent(self, event):
        """Custom paint for the stage widget."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Colors based on state
        if self.state == 'completed':
            bg_color = QColor("#e8f5e9")
            border_color = QColor("#4caf50")
            text_color = QColor("#2e7d32")
            icon_bg = QColor("#4caf50")
        elif self.state == 'current':
            bg_color = QColor("#e3f2fd")
            border_color = QColor("#2196f3")
            text_color = QColor("#1565c0")
            icon_bg = QColor("#2196f3")
        else:  # pending
            bg_color = QColor("#fafafa")
            border_color = QColor("#e0e0e0")
            text_color = QColor("#757575")
            icon_bg = QColor("#bdbdbd")
        
        # Hover effect
        if self.is_hovered and self.is_clickable:
            bg_color = bg_color.lighter(103)
        
        # Draw background
        rect = self.rect()
        painter.fillRect(rect, bg_color)
        
        # Draw left border
        painter.setPen(QPen(border_color, 3))
        painter.drawLine(0, 0, 0, rect.height())
        
        # Draw connection line (except for first item)
        if not self.is_first:
            painter.setPen(QPen(QColor("#ddd"), 2))
            painter.drawLine(30, 0, 30, 25)
        
        # Draw connection line to next (except for last item)
        if not self.is_last:
            painter.setPen(QPen(QColor("#ddd"), 2))
            painter.drawLine(30, 75, 30, rect.height())
        
        # Draw icon circle
        icon_rect = QRect(15, 25, 30, 30)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(icon_bg))
        painter.drawEllipse(icon_rect)
        
        # Draw icon
        painter.setPen(QPen(Qt.white))
        font = painter.font()
        font.setPixelSize(16)
        painter.setFont(font)
        painter.drawText(icon_rect, Qt.AlignCenter, self.icon)
        
        # Draw name
        painter.setPen(QPen(text_color))
        font.setPixelSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(60, 35, self.name)
        
        # Draw description
        painter.setPen(QPen(text_color.lighter(120)))
        font.setPixelSize(12)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(60, 50, self.description)
        
        # Draw estimate
        painter.setPen(QPen(QColor("#999")))
        font.setPixelSize(11)
        painter.setFont(font)
        painter.drawText(60, 70, f"⏱ {self.estimate}")
        
        # Draw checkmark for completed
        if self.state == 'completed':
            painter.setPen(QPen(QColor("#4caf50"), 2))
            font.setPixelSize(20)
            painter.setFont(font)
            painter.drawText(rect.width() - 30, 45, "✓")
    
    def enterEvent(self, event):
        """Handle mouse enter."""
        self.is_hovered = True
        self.update()
    
    def leaveEvent(self, event):
        """Handle mouse leave."""
        self.is_hovered = False
        self.update()
    
    def mousePressEvent(self, event):
        """Handle mouse press."""
        if event.button() == Qt.LeftButton and self.is_clickable:
            self.clicked.emit(self.stage_id)