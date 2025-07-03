"""
Project management for the new UI.
Handles project files, auto-save, and state persistence.
"""

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, asdict, field

from PySide6.QtCore import QObject, Signal, QTimer


@dataclass
class ProjectMetadata:
    """Project metadata information."""
    case_name: str
    case_number: str = ""
    subject_name: str = ""
    date_of_birth: str = ""
    evaluation_date: str = ""
    evaluator: str = ""
    case_description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectMetadata':
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class ProjectCosts:
    """Track costs by provider and stage."""
    total: float = 0.0
    by_provider: Dict[str, float] = field(default_factory=dict)
    by_stage: Dict[str, float] = field(default_factory=dict)
    
    def add_cost(self, amount: float, provider: str, stage: str):
        """Add a cost entry."""
        self.total += amount
        self.by_provider[provider] = self.by_provider.get(provider, 0.0) + amount
        self.by_stage[stage] = self.by_stage.get(stage, 0.0) + amount
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectCosts':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class WorkflowState:
    """Track workflow progress."""
    current_stage: str = "project_setup"
    completed_stages: List[str] = field(default_factory=list)
    stage_data: Dict[str, Any] = field(default_factory=dict)
    
    def complete_stage(self, stage: str):
        """Mark a stage as completed."""
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)
    
    def set_stage_data(self, stage: str, data: Any):
        """Store data for a stage."""
        self.stage_data[stage] = data
    
    def get_stage_data(self, stage: str) -> Any:
        """Get data for a stage."""
        return self.stage_data.get(stage)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowState':
        """Create from dictionary."""
        return cls(**data)


class ProjectManager(QObject):
    """Manages project files with auto-save and state persistence."""
    
    # Signals
    project_changed = Signal()
    project_saved = Signal()
    auto_saved = Signal()
    project_loaded = Signal(str)  # project path
    cost_added = Signal(float, str, str)  # amount, provider, stage
    
    VERSION = "1.0"
    PROJECT_EXTENSION = ".frpd"
    
    def __init__(self, project_path: Optional[Path] = None):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        
        self.project_path: Optional[Path] = None
        self.project_dir: Optional[Path] = None
        self.project_id: Optional[str] = None
        
        # Project data
        self.metadata: Optional[ProjectMetadata] = None
        self.costs = ProjectCosts()
        self.workflow_state = WorkflowState()
        self.settings: Dict[str, Any] = {}
        
        # Auto-save timer
        self._auto_save_timer = QTimer()
        self._auto_save_timer.timeout.connect(self.auto_save)
        self._auto_save_timer.setInterval(60000)  # 1 minute
        self._modified = False
        
        # Load project if path provided
        if project_path:
            self.load_project(project_path)
    
    def create_project(self, base_path: Path, metadata: ProjectMetadata) -> Path:
        """Create a new project with directory structure."""
        # Generate project ID
        self.project_id = str(uuid.uuid4())
        
        # Create project directory
        safe_name = "".join(c for c in metadata.case_name if c.isalnum() or c in " -_")
        project_name = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.project_dir = base_path / project_name
        self.project_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        subdirs = [
            "source_documents",
            "processed_documents", 
            "summaries",
            "reports",
            "templates",
            "logs",
            "backups"
        ]
        for subdir in subdirs:
            (self.project_dir / subdir).mkdir(exist_ok=True)
        
        # Set project file path
        self.project_path = self.project_dir / f"{project_name}{self.PROJECT_EXTENSION}"
        
        # Initialize project data
        self.metadata = metadata
        self.costs = ProjectCosts()
        self.workflow_state = WorkflowState()
        self.settings = {
            "llm_provider": "anthropic",
            "llm_model": "claude-sonnet-4-20250514",
            "template_id": "standard_competency"
        }
        
        # Save initial project file
        self.save_project()
        
        # Start auto-save
        self._auto_save_timer.start()
        
        self.project_loaded.emit(str(self.project_path))
        self.logger.info(f"Created new project: {self.project_path}")
        
        return self.project_path
    
    def load_project(self, project_path: Path) -> bool:
        """Load existing project."""
        try:
            if not project_path.exists():
                raise FileNotFoundError(f"Project file not found: {project_path}")
            
            with open(project_path, 'r') as f:
                data = json.load(f)
            
            # Validate version
            version = data.get("version", "0.0")
            if version != self.VERSION:
                self.logger.warning(f"Project version mismatch: {version} != {self.VERSION}")
            
            # Set paths
            self.project_path = project_path
            self.project_dir = project_path.parent
            self.project_id = data.get("project_id")
            
            # Load data
            self.metadata = ProjectMetadata.from_dict(data.get("metadata", {}))
            self.costs = ProjectCosts.from_dict(data.get("costs", {}))
            self.workflow_state = WorkflowState.from_dict(data.get("workflow_state", {}))
            self.settings = data.get("settings", {})
            
            # Start auto-save
            self._auto_save_timer.start()
            self._modified = False
            
            self.project_loaded.emit(str(self.project_path))
            self.logger.info(f"Loaded project: {self.project_path}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load project: {e}")
            return False
    
    def save_project(self) -> bool:
        """Save project to file."""
        if not self.project_path:
            self.logger.error("No project path set")
            return False
        
        try:
            # Create project data
            project_data = {
                "version": self.VERSION,
                "project_id": self.project_id,
                "created_date": self._get_created_date(),
                "last_modified": datetime.now().isoformat(),
                "metadata": self.metadata.to_dict() if self.metadata else {},
                "costs": self.costs.to_dict(),
                "workflow_state": self.workflow_state.to_dict(),
                "settings": self.settings
            }
            
            # Write to temporary file first
            temp_path = self.project_path.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                json.dump(project_data, f, indent=2)
            
            # Create backup if file exists
            if self.project_path.exists():
                backup_dir = self.project_dir / "backups"
                backup_dir.mkdir(exist_ok=True)
                backup_path = backup_dir / f"{self.project_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                shutil.copy2(self.project_path, backup_path)
                
                # Keep only last 10 backups
                backups = sorted(backup_dir.glob("*.json"))
                if len(backups) > 10:
                    for old_backup in backups[:-10]:
                        old_backup.unlink()
            
            # Move temp file to actual path
            temp_path.replace(self.project_path)
            
            self._modified = False
            self.project_saved.emit()
            self.logger.debug(f"Saved project: {self.project_path}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save project: {e}")
            return False
    
    def auto_save(self):
        """Auto-save if project has been modified."""
        if self._modified:
            if self.save_project():
                self.auto_saved.emit()
                self.logger.debug("Auto-saved project")
    
    def _get_created_date(self) -> str:
        """Get project creation date."""
        if self.project_path and self.project_path.exists():
            # Try to read from existing file
            try:
                with open(self.project_path, 'r') as f:
                    data = json.load(f)
                return data.get("created_date", datetime.now().isoformat())
            except:
                pass
        return datetime.now().isoformat()
    
    def mark_modified(self):
        """Mark project as modified."""
        self._modified = True
        self.project_changed.emit()
    
    # Metadata management
    def update_metadata(self, **kwargs):
        """Update project metadata."""
        if not self.metadata:
            self.metadata = ProjectMetadata(**kwargs)
        else:
            for key, value in kwargs.items():
                if hasattr(self.metadata, key):
                    setattr(self.metadata, key, value)
        self.mark_modified()
    
    # Cost tracking
    def add_cost(self, amount: float, provider: str, stage: str):
        """Add a cost entry."""
        self.costs.add_cost(amount, provider, stage)
        self.cost_added.emit(amount, provider, stage)
        self.mark_modified()
    
    def get_total_cost(self) -> float:
        """Get total project cost."""
        return self.costs.total
    
    # Workflow management
    def set_current_stage(self, stage: str):
        """Set the current workflow stage."""
        self.workflow_state.current_stage = stage
        self.mark_modified()
    
    def complete_current_stage(self):
        """Mark current stage as completed."""
        self.workflow_state.complete_stage(self.workflow_state.current_stage)
        self.mark_modified()
    
    def complete_stage(self, stage: str):
        """Mark a specific stage as completed."""
        self.workflow_state.complete_stage(stage)
        self.mark_modified()
    
    def save_stage_data(self, stage: str, data: Any):
        """Save data for a stage."""
        self.workflow_state.set_stage_data(stage, data)
        self.mark_modified()
    
    def get_stage_data(self, stage: str) -> Any:
        """Get saved data for a stage."""
        return self.workflow_state.get_stage_data(stage)
    
    # Settings management
    def update_settings(self, **kwargs):
        """Update project settings."""
        self.settings.update(kwargs)
        self.mark_modified()
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a project setting."""
        return self.settings.get(key, default)
    
    # File management
    def get_project_file(self, subdir: str, filename: str) -> Path:
        """Get path to a file within the project."""
        return self.project_dir / subdir / filename
    
    def list_project_files(self, subdir: str, pattern: str = "*") -> List[Path]:
        """List files in a project subdirectory."""
        dir_path = self.project_dir / subdir
        if dir_path.exists():
            return list(dir_path.glob(pattern))
        return []
    
    # Cleanup
    def close_project(self):
        """Close the current project."""
        # Stop auto-save
        self._auto_save_timer.stop()
        
        # Save if modified
        if self._modified:
            self.save_project()
        
        # Clear data
        self.project_path = None
        self.project_dir = None
        self.project_id = None
        self.metadata = None
        self.costs = ProjectCosts()
        self.workflow_state = WorkflowState()
        self.settings = {}
        self._modified = False
        
        self.logger.info("Closed project")