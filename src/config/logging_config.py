"""
Centralized logging configuration for the Forensic Psych Report Drafter application.
Provides consistent logging setup with file rotation and configurable log levels.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from datetime import datetime


class ApplicationLogger:
    """Centralized logging configuration for the application."""
    
    def __init__(self, app_name="forensic_report_drafter"):
        self.app_name = app_name
        self.log_dir = Path.home() / f".{app_name}" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
    def setup(self, debug=False):
        """Configure application-wide logging."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG if debug else logging.INFO)
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / f"{self.app_name}.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO if not debug else logging.DEBUG)
        
        # Formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - '
            '[%(filename)s:%(lineno)d] - %(funcName)s() - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(detailed_formatter)
        
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(simple_formatter)
        
        # Add handlers
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        # Configure specific loggers
        self._configure_module_loggers(debug)
        
        # Add startup message
        root_logger.info(f"Logging initialized - Debug: {debug}, Log dir: {self.log_dir}")
        
    def _configure_module_loggers(self, debug):
        """Configure logging levels for specific modules."""
        module_configs = {
            'llm': logging.DEBUG if debug else logging.INFO,
            'llm.providers': logging.DEBUG if debug else logging.INFO,
            'ui.workers': logging.DEBUG if debug else logging.INFO,
            'app_config': logging.INFO,
            'prompt_manager': logging.INFO,
        }
        
        for module, level in module_configs.items():
            logging.getLogger(module).setLevel(level)
            
        # Suppress noisy libraries
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)