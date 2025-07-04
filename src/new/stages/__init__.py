"""
Workflow stages for the new UI.
"""

from .welcome_stage import WelcomeStage
from .setup_stage import ProjectSetupStage
from .import_stage import DocumentImportStage
from .process_stage import DocumentProcessStage
from .analysis_stage import AnalysisStage
from .report_stage import ReportGenerationStage

__all__ = [
    'WelcomeStage', 
    'ProjectSetupStage', 
    'DocumentImportStage', 
    'DocumentProcessStage',
    'AnalysisStage',
    'ReportGenerationStage'
]