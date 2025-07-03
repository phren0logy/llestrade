"""
Stage management framework for the new UI.
Controls workflow stages and transitions.
"""

import logging
from typing import Dict, Optional, Type, List

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QWidget, QApplication


class StageManager(QObject):
    """Controls stage transitions and lifecycle."""
    
    # Signals
    stage_changed = Signal(str)  # new stage name
    stage_loading = Signal(str)  # stage being loaded
    can_proceed_changed = Signal(bool)
    can_go_back_changed = Signal(bool)
    validation_changed = Signal(bool, str)  # is_valid, message
    error = Signal(str)  # error message
    
    # Stage workflow order
    STAGE_ORDER = [
        'setup',      # Project setup
        'import',     # Document import
        'process',    # Document processing
        'analysis',   # Analysis
        'generate',   # Report generation
        'refine'      # Refinement
    ]
    
    def __init__(self, main_window):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.main_window = main_window
        self.project = None
        
        # Current stage
        self.current_stage: Optional['BaseStage'] = None
        self.current_stage_name: str = ""
        self.current_stage_index: int = -1
        
        # Stage classes (will be populated dynamically)
        self.stage_classes: Dict[str, Type['BaseStage']] = {}
        
        # Validation state
        self._can_proceed = False
        self._can_go_back = False
        
        # Initialize stages
        self._initialize_stages()
    
    def _initialize_stages(self):
        """Import and register all stage classes."""
        # Import stage classes when they're created
        # For now, we'll use a placeholder
        self.logger.info("Stage manager initialized")
    
    def register_stage(self, name: str, stage_class: Type['BaseStage']):
        """Register a stage class."""
        self.stage_classes[name] = stage_class
        self.logger.debug(f"Registered stage: {name}")
    
    def set_project(self, project):
        """Set the current project."""
        self.project = project
        if self.current_stage:
            self.current_stage.project = project
    
    def load_stage(self, stage_name: str):
        """Load a new stage with proper cleanup."""
        if stage_name not in self.stage_classes:
            # Try to load the stage class dynamically
            self._try_load_stage_class(stage_name)
            
        if stage_name not in self.stage_classes:
            self.logger.error(f"Unknown stage: {stage_name}")
            return
        
        self.stage_loading.emit(stage_name)
        
        # Cleanup current stage
        if self.current_stage:
            self.cleanup_current_stage()
        
        # Force event processing to ensure cleanup completes
        QApplication.processEvents()
        
        # Create new stage
        try:
            stage_class = self.stage_classes[stage_name]
            self.current_stage = stage_class(self.project)
            self.current_stage_name = stage_name
            self.current_stage_index = self.STAGE_ORDER.index(stage_name) if stage_name in self.STAGE_ORDER else -1
            
            # Connect signals
            self.current_stage.completed.connect(self._on_stage_completed)
            self.current_stage.validation_changed.connect(self._on_validation_changed)
            self.current_stage.error.connect(self._on_stage_error)
            
            # Add to main window
            self.main_window.set_stage_widget(self.current_stage)
            
            # Update navigation state
            self._update_navigation()
            
            # Emit stage changed
            self.stage_changed.emit(stage_name)
            
            self.logger.info(f"Loaded stage: {stage_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to load stage {stage_name}: {e}")
            # TODO: Show error dialog
    
    def _try_load_stage_class(self, stage_name: str):
        """Try to dynamically load a stage class."""
        try:
            # Map stage names to class names
            class_map = {
                'setup': 'ProjectSetupStage',
                'import': 'DocumentImportStage',
                'process': 'DocumentProcessingStage',
                'analyze': 'AnalysisStage',
                'generate': 'ReportGenerationStage',
                'refine': 'RefinementStage'
            }
            
            class_name = class_map.get(stage_name)
            if not class_name:
                return
            
            # Try to import from stages module
            module = __import__(f'src.new.stages.{stage_name}_stage', fromlist=[class_name])
            stage_class = getattr(module, class_name, None)
            
            if stage_class:
                self.register_stage(stage_name, stage_class)
                
        except ImportError as e:
            self.logger.debug(f"Stage class not yet implemented: {stage_name} - {e}")
    
    def cleanup_current_stage(self):
        """Clean up the current stage."""
        if not self.current_stage:
            return
        
        self.logger.debug(f"Cleaning up stage: {self.current_stage_name}")
        
        # Disconnect signals
        try:
            self.current_stage.completed.disconnect()
            self.current_stage.validation_changed.disconnect()
            self.current_stage.error.disconnect()
        except:
            pass
        
        # Call stage cleanup
        self.current_stage.cleanup()
        
        # Schedule for deletion
        self.current_stage.deleteLater()
        self.current_stage = None
        
        # Force garbage collection
        import gc
        gc.collect()
    
    def next_stage(self):
        """Move to the next stage in workflow."""
        if not self.can_proceed():
            return
        
        current_index = self.current_stage_index
        if current_index < len(self.STAGE_ORDER) - 1:
            next_stage = self.STAGE_ORDER[current_index + 1]
            self.load_stage(next_stage)
    
    def previous_stage(self):
        """Move to the previous stage in workflow."""
        if not self.can_go_back():
            return
        
        current_index = self.current_stage_index
        if current_index > 0:
            prev_stage = self.STAGE_ORDER[current_index - 1]
            self.load_stage(prev_stage)
    
    def can_proceed(self) -> bool:
        """Check if can proceed to next stage."""
        return self._can_proceed
    
    def can_go_back(self) -> bool:
        """Check if can go back to previous stage."""
        return self._can_go_back
    
    def _update_navigation(self):
        """Update navigation state."""
        # Can go back if not on first stage
        self._can_go_back = self.current_stage_index > 0
        
        # Can proceed if current stage is valid and not last stage
        if self.current_stage:
            is_valid, _ = self.current_stage.validate()
            self._can_proceed = is_valid and self.current_stage_index < len(self.STAGE_ORDER) - 1
        else:
            self._can_proceed = False
        
        self.can_go_back_changed.emit(self._can_go_back)
        self.can_proceed_changed.emit(self._can_proceed)
    
    def _on_stage_completed(self, results: Dict):
        """Handle stage completion."""
        self.logger.info(f"Stage {self.current_stage_name} completed")
        
        # Special handling for setup stage - create the project
        if self.current_stage_name == 'setup' and not self.project:
            self._create_project_from_setup(results)
        
        # Save stage data to project
        if self.project:
            self.project.save_stage_data(self.current_stage_name, results)
            self.project.complete_stage(self.current_stage_name)
        
        # Auto-advance to next stage after a short delay
        QTimer.singleShot(500, self.next_stage)
    
    def _create_project_from_setup(self, results: Dict):
        """Create a new project from setup stage results."""
        from src.new.core import ProjectManager
        
        metadata = results.get('metadata')
        output_dir = results.get('output_directory')
        template = results.get('template')
        
        if not metadata or not output_dir:
            self.logger.error("Missing metadata or output directory for project creation")
            return
        
        # Create project manager if needed
        if not self.main_window.project_manager:
            self.main_window.project_manager = ProjectManager()
        
        # Create the project
        try:
            from pathlib import Path
            base_path = Path(output_dir)
            project_path = self.main_window.project_manager.create_project(base_path, metadata)
            
            # Load the project (returns boolean, project manager keeps the project)
            success = self.main_window.project_manager.load_project(project_path)
            if success:
                self.project = self.main_window.project_manager
                
                # Store template preference
                if template:
                    self.project.update_settings(template=template)
            
            self.logger.info(f"Created new project at: {project_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to create project: {e}")
            self.error.emit(f"Failed to create project: {str(e)}")
    
    def _on_validation_changed(self, is_valid: bool):
        """Handle validation state change."""
        self._update_navigation()
        
        # Get validation message
        if self.current_stage:
            _, message = self.current_stage.validate()
            self.validation_changed.emit(is_valid, message)
    
    def _on_stage_error(self, error_message: str):
        """Handle stage error."""
        self.logger.error(f"Stage error in {self.current_stage_name}: {error_message}")
        # TODO: Show error dialog
    
    def get_stage_progress(self) -> Dict[str, str]:
        """Get progress for all stages."""
        progress = {}
        
        for stage in self.STAGE_ORDER:
            if self.project and stage in self.project.workflow_state.completed_stages:
                progress[stage] = 'completed'
            elif stage == self.current_stage_name:
                progress[stage] = 'current'
            else:
                progress[stage] = 'pending'
        
        return progress
    
    def jump_to_stage(self, stage_name: str):
        """Jump directly to a specific stage."""
        if stage_name not in self.STAGE_ORDER:
            self.logger.error(f"Invalid stage: {stage_name}")
            return
        
        # Check if stage is accessible (previous stages should be completed)
        stage_index = self.STAGE_ORDER.index(stage_name)
        if self.project:
            for i in range(stage_index):
                required_stage = self.STAGE_ORDER[i]
                if required_stage not in self.project.workflow_state.completed_stages:
                    self.logger.warning(f"Cannot jump to {stage_name} - {required_stage} not completed")
                    return
        
        self.load_stage(stage_name)


# Base class for stages (to be moved to separate file)
class BaseStage(QWidget):
    """Base class for all workflow stages."""
    
    # Signals
    progress = Signal(int, str)  # percent, message
    completed = Signal(dict)     # results
    error = Signal(str)          # error message
    validation_changed = Signal(bool)  # can proceed
    
    def __init__(self, project):
        super().__init__()
        self.project = project
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._is_valid = False
        
        # Setup UI and load state
        self.setup_ui()
        self.load_state()
        
        # Validate initial state
        self._validate()
    
    def setup_ui(self):
        """Create the UI for this stage."""
        raise NotImplementedError("Subclasses must implement setup_ui")
    
    def validate(self) -> tuple[bool, str]:
        """Check if stage can proceed."""
        raise NotImplementedError("Subclasses must implement validate")
    
    def save_state(self):
        """Save current state to project."""
        raise NotImplementedError("Subclasses must implement save_state")
    
    def load_state(self):
        """Load state from project."""
        raise NotImplementedError("Subclasses must implement load_state")
    
    def _validate(self):
        """Internal validation that emits signal."""
        old_valid = self._is_valid
        self._is_valid, _ = self.validate()
        
        if old_valid != self._is_valid:
            self.validation_changed.emit(self._is_valid)
    
    def cleanup(self):
        """Clean up resources when leaving stage."""
        self.save_state()
        self.logger.debug(f"Cleaned up {self.__class__.__name__}")