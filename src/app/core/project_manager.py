"""
Project management for the new UI.
Handles project files, auto-save, and state persistence.
"""

import json
import logging
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any, List, TYPE_CHECKING
from dataclasses import dataclass, asdict, field

from PySide6.QtCore import QObject, Signal, QTimer

if TYPE_CHECKING:
    from .summary_groups import SummaryGroup

from .secure_settings import SecureSettings
from .file_tracker import DashboardMetrics, WorkspaceMetrics, build_workspace_metrics


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


PROJECT_FILENAME = "project.frpd"
SOURCES_FILENAME = "sources.json"


@dataclass
class SourceTreeState:
    """Persisted source folder selection relative to the project directory."""

    root: str = ""  # relative path from project dir (allows .. for external roots)
    selected_folders: List[str] = field(default_factory=list)  # relative to root
    include_root_files: bool = False
    last_scan: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    version: str = "1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceTreeState":
        payload = {**data}
        payload.setdefault("selected_folders", [])
        payload.setdefault("warnings", [])
        return cls(**payload)


@dataclass
class ConversionSettings:
    """Conversion helper configuration for a project."""

    helper: str = "azure_di"
    options: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversionSettings":
        payload = {**data}
        payload.setdefault("options", {})
        return cls(**payload)


@dataclass
class DashboardState:
    """UI state for the dashboard experience."""

    last_open_tab: str = "documents"
    pending_jobs: List[Dict[str, Any]] = field(default_factory=list)
    notices: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DashboardState":
        payload = {**data}
        payload.setdefault("pending_jobs", [])
        payload.setdefault("notices", [])
        return cls(**payload)


def _sanitize_project_folder(name: str) -> str:
    """Return a filesystem-friendly folder name derived from the project title."""
    if not name:
        return "project"
    # Replace whitespace with dashes and drop unsupported characters
    candidate = re.sub(r"\s+", "-", name.strip())
    candidate = re.sub(r"[^A-Za-z0-9._-]", "", candidate)
    candidate = re.sub(r"-+", "-", candidate)
    candidate = candidate.strip("-_.")
    return candidate or "project"


def _ensure_unique_dir(base_path: Path, folder_name: str) -> Path:
    """Return a unique directory path, appending numeric suffixes if needed."""
    candidate = base_path / folder_name
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        suffixed = base_path / f"{folder_name}-{index}"
        if not suffixed.exists():
            return suffixed
        index += 1


class ProjectManager(QObject):
    """Manages project files with auto-save and state persistence."""
    
    # Signals
    project_changed = Signal()
    project_saved = Signal()
    auto_saved = Signal()
    project_loaded = Signal(str)  # project path
    cost_added = Signal(float, str, str)  # amount, provider, stage
    
    VERSION = "2.0"
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
        self.source_state = SourceTreeState()
        self.conversion_settings = ConversionSettings()
        self.dashboard_state = DashboardState()
        self.dashboard_metrics: DashboardMetrics = DashboardMetrics.empty()
        self.workspace_metrics: Optional[WorkspaceMetrics] = None
        self.version_warning: Optional[str] = None
        
        # Auto-save timer
        self._auto_save_timer = QTimer()
        self._auto_save_timer.timeout.connect(self.auto_save)
        self._auto_save_timer.setInterval(60000)  # 1 minute
        self._modified = False
        self._file_tracker = None
        self.summary_groups: Dict[str, "SummaryGroup"] = {}
        
        # Load project if path provided
        if project_path:
            self.load_project(project_path)
    
    def create_project(self, base_path: Path, metadata: ProjectMetadata) -> Path:
        """Create a new project with directory structure."""
        # Generate project ID
        self.project_id = str(uuid.uuid4())
        
        # Create project directory based on sanitized case name (spaces → dashes)
        safe_name = _sanitize_project_folder(metadata.case_name)
        self.project_dir = _ensure_unique_dir(base_path, safe_name)
        self.project_dir.mkdir(parents=True, exist_ok=True)
        project_name = self.project_dir.name
        
        # Create subdirectories
        subdirs = [
            "converted_documents",
            "bulk_analysis",
            "reports",
            "templates",
            "backups",
        ]
        for subdir in subdirs:
            (self.project_dir / subdir).mkdir(exist_ok=True)
        
        # Set project file path
        self.project_path = self.project_dir / PROJECT_FILENAME
        
        # Initialize project data
        self.metadata = metadata
        self.costs = ProjectCosts()
        self.workflow_state = WorkflowState()
        self.settings = {
            "llm_provider": "anthropic",
            "llm_model": "claude-sonnet-4-20250514",
            "template_id": "standard_competency"
        }
        self.source_state = SourceTreeState()
        self.conversion_settings = ConversionSettings()
        self.dashboard_state = DashboardState()
        self.dashboard_metrics = DashboardMetrics.empty()
        self.workspace_metrics = None
        self.version_warning = None
        
        # Save initial project file
        self.save_project()
        self._write_sources_state()
        
        # Add to recent projects
        settings = SecureSettings()
        project_info = {
            'name': project_name,
            'metadata': asdict(self.metadata),
            'last_modified': datetime.now().isoformat()
        }
        settings.add_recent_project(str(self.project_path), project_info)
        
        # Start auto-save
        self._auto_save_timer.start()
        
        self.project_loaded.emit(str(self.project_path))
        self.logger.info(f"Created new project: {self.project_path}")
        self.refresh_summary_groups()
        
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
                self.version_warning = version
            else:
                self.version_warning = None
            
            # Set paths
            self.project_path = project_path
            self.project_dir = project_path.parent
            self.project_id = data.get("project_id")
            
            # Load data
            self.metadata = ProjectMetadata.from_dict(data.get("metadata", {}))
            self.costs = ProjectCosts.from_dict(data.get("costs", {}))
            self.workflow_state = WorkflowState.from_dict(data.get("workflow_state", {}))
            self.settings = data.get("settings", {})
            self.source_state = SourceTreeState.from_dict(data.get("source", {}))
            self.conversion_settings = ConversionSettings.from_dict(data.get("conversion", {}))
            self.dashboard_state = DashboardState.from_dict(data.get("dashboard_state", {}))
            self.dashboard_metrics = DashboardMetrics.from_dict(data.get("dashboard_metrics"))
            self.workspace_metrics = None

            # Update recent projects
            settings = SecureSettings()
            project_info = {
                'name': self.project_name,
                'metadata': asdict(self.metadata),
                'last_modified': datetime.now().isoformat()
            }
            settings.add_recent_project(str(self.project_path), project_info)
            
            # Start auto-save
            self._auto_save_timer.start()
            self._modified = False

            # Load persisted source tree selections (create if missing)
            self._load_sources_state()
            
            self.project_loaded.emit(str(self.project_path))
            self.logger.info(f"Loaded project: {self.project_path}")
            self.refresh_summary_groups()
            
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
                "settings": self.settings,
                "source": self.source_state.to_dict(),
                "conversion": self.conversion_settings.to_dict(),
                "dashboard_state": self.dashboard_state.to_dict(),
                "dashboard_metrics": self.dashboard_metrics.to_dict() if self.dashboard_metrics else None,
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

            # Persist source selection alongside project file
            self._write_sources_state()

            # Update recent projects
            settings = SecureSettings()
            project_info = {
                'name': self.project_name or self.project_path.stem,
                'metadata': asdict(self.metadata) if self.metadata else {},
                'last_modified': datetime.now().isoformat()
            }
            settings.add_recent_project(str(self.project_path), project_info)
            
            self._modified = False
            self.project_saved.emit()
            self.logger.debug(f"Saved project: {self.project_path}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save project: {e}")
            return False

    def _sources_file(self) -> Optional[Path]:
        if not self.project_dir:
            return None
        return self.project_dir / SOURCES_FILENAME

    def _write_sources_state(self) -> None:
        path = self._sources_file()
        if not path:
            return
        try:
            path.write_text(json.dumps(self.source_state.to_dict(), indent=2))
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.warning("Failed to persist sources.json: %s", exc)

    def _load_sources_state(self) -> None:
        path = self._sources_file()
        if not path:
            return
        if not path.exists():
            self._write_sources_state()
            return
        try:
            payload = json.loads(path.read_text())
            self.source_state = SourceTreeState.from_dict(payload)
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.warning("Failed to load sources.json (%s), resetting", exc)
            self.source_state = SourceTreeState()
            self._write_sources_state()

    def auto_save(self):
        """Auto-save if project has been modified."""
        if self._modified:
            if self.save_project():
                self.auto_saved.emit()
                self.logger.debug("Auto-saved project")

    # ------------------------------------------------------------------
    # Dashboard helpers
    # ------------------------------------------------------------------
    def get_file_tracker(self):
        """Return a lazily-instantiated FileTracker for the project."""
        from .file_tracker import FileTracker

        if not self.project_dir:
            raise RuntimeError("Project must be created or loaded before accessing FileTracker")
        if self._file_tracker is None or self._file_tracker.project_path != self.project_dir:
            self._file_tracker = FileTracker(self.project_dir)
            self._file_tracker.load()
        return self._file_tracker

    def build_highlight_jobs(self):
        """Return highlight extraction jobs for the current project."""
        from .highlight_manager import build_highlight_jobs

        return build_highlight_jobs(self)

    def get_dashboard_metrics(self, refresh: bool = False) -> DashboardMetrics:
        """Return dashboard-friendly file metrics, optionally refreshing first."""
        tracker = self.get_file_tracker()

        if not refresh and self.dashboard_metrics and self.dashboard_metrics.last_scan:
            return self.dashboard_metrics

        snapshot = tracker.snapshot if not refresh else None
        if snapshot is None:
            if tracker.snapshot and not refresh:
                snapshot = tracker.snapshot
            else:
                snapshot = tracker.scan()
                self.update_source_state(last_scan=snapshot.timestamp.isoformat())

        if snapshot:
            metrics = snapshot.to_dashboard_metrics()
        else:
            metrics = DashboardMetrics.empty()

        self._store_dashboard_metrics(metrics, mark_modified=refresh or metrics.last_scan is not None)
        return self.dashboard_metrics

    def _store_dashboard_metrics(self, metrics: DashboardMetrics, *, mark_modified: bool = True) -> None:
        if self.dashboard_metrics == metrics:
            return
        self.dashboard_metrics = metrics
        self.workspace_metrics = None
        if mark_modified:
            self.mark_modified()

    def get_workspace_metrics(self, refresh: bool = False) -> WorkspaceMetrics:
        """Return combined dashboard and group metrics for workspace views."""
        if not refresh and self.workspace_metrics is not None:
            return self.workspace_metrics

        dashboard = self.get_dashboard_metrics(refresh=refresh)
        tracker = self.get_file_tracker()
        snapshot = tracker.snapshot or tracker.load()
        summary_groups = self.list_summary_groups()

        metrics = build_workspace_metrics(
            snapshot=snapshot,
            dashboard=dashboard,
            summary_groups=summary_groups,
        )
        self._store_workspace_metrics(metrics)
        return metrics

    def _store_workspace_metrics(self, metrics: WorkspaceMetrics) -> None:
        self.workspace_metrics = metrics

    # ------------------------------------------------------------------
    # Summary group helpers
    # ------------------------------------------------------------------
    def refresh_summary_groups(self) -> List["SummaryGroup"]:
        from .summary_groups import load_summary_groups

        if not self.project_dir:
            self.summary_groups = {}
            return []
        groups = load_summary_groups(self.project_dir)
        self.summary_groups = {group.group_id: group for group in groups}
        self.workspace_metrics = None
        return groups

    def list_summary_groups(self) -> List["SummaryGroup"]:
        if not self.summary_groups:
            return self.refresh_summary_groups()
        return list(self.summary_groups.values())

    def save_summary_group(self, group: "SummaryGroup") -> "SummaryGroup":
        from .summary_groups import save_summary_group

        if not self.project_dir:
            raise RuntimeError("Project must be created or loaded before saving summary groups")
        group.files = sorted({path.strip() for path in group.files if path.strip()})
        group.directories = sorted({path.strip("/").strip() for path in group.directories if path.strip("/").strip()})
        saved = save_summary_group(self.project_dir, group)
        self.summary_groups[saved.group_id] = saved
        self.workspace_metrics = None
        self.mark_modified()
        return saved

    def delete_summary_group(self, group_id: str) -> bool:
        from .summary_groups import delete_summary_group

        group = self.summary_groups.get(group_id)
        if not group or not self.project_dir:
            return False
        delete_summary_group(self.project_dir, group)
        self.summary_groups.pop(group_id, None)
        self.workspace_metrics = None
        self.mark_modified()
        return True
    
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
    def update_metadata(self, metadata=None, **kwargs):
        """Update project metadata."""
        if metadata and isinstance(metadata, ProjectMetadata):
            # If a ProjectMetadata object is passed, use it directly
            self.metadata = metadata
        elif not self.metadata:
            # Create new metadata from kwargs
            self.metadata = ProjectMetadata(**kwargs)
        else:
            # Update existing metadata with kwargs
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

    # Source state management
    def update_source_state(
        self,
        *,
        root: Optional[str] = None,
        selected_folders: Optional[List[str]] = None,
        include_root_files: Optional[bool] = None,
        warnings: Optional[List[str]] = None,
        last_scan: Optional[str] = None,
    ) -> None:
        if root is not None:
            self.source_state.root = root
        if selected_folders is not None:
            self.source_state.selected_folders = selected_folders
        if include_root_files is not None:
            self.source_state.include_root_files = include_root_files
        if warnings is not None:
            self.source_state.warnings = warnings
        if last_scan is not None:
            self.source_state.last_scan = last_scan
        self.workspace_metrics = None
        self.mark_modified()
        self._write_sources_state()

    def update_conversion_helper(self, helper: str, **options: Any) -> None:
        self.conversion_settings.helper = helper
        self.conversion_settings.options = dict(options)
        self.mark_modified()

    def update_dashboard_state(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if hasattr(self.dashboard_state, key):
                setattr(self.dashboard_state, key, value)
        self.mark_modified()
    
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
    @property
    def project_data(self) -> Dict[str, Any]:
        """Provide project data in the format expected by stages."""
        if not self.project_path:
            return {}
        base_paths = {
            'base': str(self.project_dir),
            'converted_documents': str(self.project_dir / 'converted_documents'),
            'bulk_analysis': str(self.project_dir / 'bulk_analysis'),
            'reports': str(self.project_dir / 'reports'),
            'templates': str(self.project_dir / 'templates'),
            'backups': str(self.project_dir / 'backups'),
        }

        return {
            'paths': base_paths,
            'metadata': self.metadata.to_dict() if self.metadata else {},
            'settings': self.settings,
            'workflow_state': self.workflow_state.to_dict(),
            'costs': self.costs.to_dict(),
            'project_id': self.project_id,
            'source': self.source_state.to_dict(),
            'conversion': self.conversion_settings.to_dict(),
            'dashboard_state': self.dashboard_state.to_dict(),
            'dashboard_metrics': self.dashboard_metrics.to_dict() if self.dashboard_metrics else None,
        }
    
    @property
    def project_name(self) -> str:
        """Get the project name from the project path."""
        if self.project_dir:
            return self.project_dir.name
        return ""

    @staticmethod
    def read_dashboard_metrics_from_disk(path: Path) -> DashboardMetrics:
        """Return persisted dashboard metrics without fully loading the project."""
        project_file = path
        if project_file.is_dir():
            project_file = project_file / PROJECT_FILENAME
        elif project_file.suffix != ProjectManager.PROJECT_EXTENSION:
            project_file = project_file / PROJECT_FILENAME

        if not project_file.exists():
            return DashboardMetrics.empty()

        try:
            payload = json.loads(project_file.read_text())
        except Exception as exc:  # pragma: no cover - defensive logging
            logging.getLogger(__name__).debug(
                "Failed to read dashboard metrics from %s: %s", project_file, exc
            )
            return DashboardMetrics.empty()

        return DashboardMetrics.from_dict(payload.get("dashboard_metrics"))
    
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
        self.source_state = SourceTreeState()
        self.conversion_settings = ConversionSettings()
        self.dashboard_state = DashboardState()
        self.dashboard_metrics = DashboardMetrics.empty()
        self.workspace_metrics = None
        self._file_tracker = None
        self._modified = False

        self.logger.info("Closed project")
