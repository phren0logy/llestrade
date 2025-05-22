"""
Prompt management system for LLM interactions.
Handles loading and formatting of prompt templates.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional


class PromptManager:
    """Manages loading and formatting of prompt templates.
    
    Templates are stored in text files in a specified directory.
    Template files can include placeholders in {variable} format.
    """
    
    def __init__(self, template_dir: str = "prompt_templates"):
        """Initialize the prompt manager with a template directory.
        
        Args:
            template_dir: Directory containing prompt template files
        """
        self.template_dir = Path(template_dir)
        self.templates: Dict[str, str] = {}
        self._load_templates()
    
    def _load_templates(self) -> None:
        """Load all templates from the template directory."""
        if not self.template_dir.exists():
            logging.warning(f"Template directory not found: {self.template_dir}")
            return
            
        for template_file in self.template_dir.glob("*.md"):
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    self.templates[template_file.stem] = f.read()
                logging.debug(f"Loaded template: {template_file.stem}")
            except Exception as e:
                logging.error(f"Error loading template {template_file}: {e}")
    
    def get_template(self, name: str, **kwargs: Any) -> str:
        """Get a template by name with optional formatting.
        
        Args:
            name: Name of the template (without extension)
            **kwargs: Variables to format into the template
            
        Returns:
            The template content with variables substituted
            
        Raises:
            KeyError: If template not found
        """
        if name not in self.templates:
            raise KeyError(f"Template not found: {name}")
            
        template = self.templates[name]
        return template.format(**kwargs)
        
    def get_system_prompt(self) -> str:
        """Get the system prompt.
        
        Returns:
            The system prompt content, or a default if not found
        """
        try:
            return self.get_template("system_prompt")
        except KeyError:
            # Default system prompt if not found in templates
            logging.warning("Using default system prompt as template not found")
            return (
                "You are an advanced assistant designed to help a forensic psychiatrist. "
                "Your task is to analyze and objectively document case information in a formal clinical style, "
                "maintaining professional psychiatric documentation standards. Distinguish between information "
                "from the subject and objective findings. Report specific details such as dates, frequencies, "
                "dosages, and other relevant clinical data. Document without emotional language or judgment."
            )
