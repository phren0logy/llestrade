# File Location: lib/template_processor.py
# Section: 3.8 Local Template Processing Engine
# Description: Core processor for locally stored markdown report templates

from pathlib import Path
from typing import Any, Dict, List

import streamlit as st
from langchain_text_splitters import MarkdownHeaderTextSplitter

from .prompts import get_prompt


class LocalTemplateProcessor:
    """
    Core processor for locally stored markdown report templates.

    This enables the primary workflow: forensic professionals maintain
    standardized markdown templates locally, and this system converts
    them into section-based LLM prompts for comprehensive report generation.
    """

    def __init__(self, template_directory: str = "report_templates"):
        self.template_directory = Path(template_directory)
        self.header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "Header 1")],  # Split on main sections
            strip_headers=False  # Preserve headers for context
        )
        self._ensure_template_directory()

    def _ensure_template_directory(self):
        """Ensure template directory exists with example templates"""
        self.template_directory.mkdir(exist_ok=True)

        # Create example templates for new users
        if not any(self.template_directory.glob("*.md")):
            self._create_starter_templates()

    def get_available_templates(self) -> List[str]:
        """Get list of user's local markdown templates"""
        return sorted([f.name for f in self.template_directory.glob("*.md")])

    def load_template(self, template_name: str) -> str:
        """Load template content from user's local directory"""
        template_path = self.template_directory / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_name}")

        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()

    def process_template_to_sections(self, template_name: str) -> List[Dict[str, Any]]:
        """
        Split user's template into sections for individual processing.

        Each Header 1 section becomes a separate prompt, allowing focused
        generation and better quality control.
        """
        template_content = self.load_template(template_name)

        # Use LangChain to split by headers while preserving structure
        sections = self.header_splitter.split_text(template_content)

        processed_sections = []
        for i, section in enumerate(sections, start=1):
            if hasattr(section, "page_content") and hasattr(section, "metadata"):
                section_name = section.metadata.get("Header 1", f"Section {i}")

                processed_sections.append({
                    "name": section_name,
                    "content": section.page_content,
                    "metadata": section.metadata,
                    "template_source": template_name,
                    "section_index": i
                })

        return processed_sections

    def generate_section_prompts(self, template_name: str) -> List[Dict[str, Any]]:
        """
        Convert template sections into LLM-ready prompts.

        This is where user templates become structured prompts that guide
        LLM generation for each section of the forensic report.
        """
        sections = self.process_template_to_sections(template_name)

        # Get standardized instructions for report generation
        try:
            instructions = get_prompt("section_processing")
        except:
            # Fallback instructions if Langfuse unavailable
            instructions = """Generate this section of a forensic psychiatric evaluation report. Use information from the interview transcript. Organize relevant information including direct quotes. Write in complete paragraphs following professional forensic reporting standards."""

        prompts = []
        for section in sections:
            # Structure as template + instructions
            prompt_content = f"""<template>
# {section['name']}

{section['content']}
</template>

{instructions}"""

            prompts.append({
                "name": section['name'],
                "content": prompt_content,
                "template_source": template_name,
                "section_index": section['section_index'],
                "metadata": section['metadata']
            })

        return prompts

    def combine_with_transcript(self, section_prompt: Dict[str, Any], transcript_content: str) -> str:
        """Combine section prompt with interview transcript for final generation"""
        return f"""{section_prompt['content']}

<transcript>
{transcript_content}
</transcript>"""

@st.cache_resource
def get_template_processor():
    """Cached template processor instance"""
    return LocalTemplateProcessor() 
