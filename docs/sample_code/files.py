# File Location: lib/files.py
# Section: 3.5 File Operations with Minimal Metadata
# Description: File handling utilities with lightweight YAML frontmatter

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml


def ensure_directories():
    """Ensure required directories exist"""
    for directory in ["outputs", "templates"]:
        os.makedirs(directory, exist_ok=True)

def scan_for_pdfs(directory: str, recursive: bool = False) -> List[str]:
    """Scan directory for PDF files"""
    path = Path(directory)
    if recursive:
        return list(path.rglob("*.pdf"))
    else:
        return list(path.glob("*.pdf"))

def scan_for_markdown(directory: str) -> List[str]:
    """Scan directory for markdown files"""
    path = Path(directory)
    return list(path.glob("*.md"))

def save_output_with_minimal_metadata(content: str, filename: str, minimal_metadata: Dict[str, Any], output_dir: str = "outputs") -> str:
    """Save content with minimal YAML frontmatter linking to Langfuse"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"{timestamp}_{filename}"

    # Create minimal YAML frontmatter header
    metadata_header = "---\n"
    metadata_header += yaml.dump(minimal_metadata, default_flow_style=False)
    metadata_header += "---\n\n"

    # Combine metadata and content
    full_content = metadata_header + content

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_content)

    return str(output_path)

def save_chunked_output_with_metadata(
    content: str,
    filename: str,
    minimal_metadata: Dict[str, Any],
    chunk_info: Dict[str, Any] = None,
    output_dir: str = "outputs"
) -> str:
    """Save content with enhanced metadata for chunked documents"""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"{timestamp}_{filename}"

    # Enhanced metadata for chunked documents
    enhanced_metadata = {
        **minimal_metadata,
        "chunking_info": {
            "total_chunks": chunk_info.get("total_chunks", 1) if chunk_info else 1,
            "chunking_strategy": chunk_info.get("chunking_strategy", "none") if chunk_info else "none",
            "model_context_window": chunk_info.get("model_context_window") if chunk_info else None,
        } if chunk_info else None
    }

    # Create YAML frontmatter header
    metadata_header = "---\n"
    metadata_header += yaml.dump(enhanced_metadata, default_flow_style=False)
    metadata_header += "---\n\n"

    # Combine metadata and content
    full_content = metadata_header + content

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_content)

    return str(output_path)

def read_metadata_from_file(file_path: str) -> Dict[str, Any]:
    """Extract YAML frontmatter metadata from generated files"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if content.startswith('---\n'):
            end_marker = content.find('\n---\n', 4)
            if end_marker != -1:
                frontmatter = content[4:end_marker]
                return yaml.safe_load(frontmatter)
    except:
        pass

    return {}

def get_rich_context_from_langfuse(trace_id: str) -> Dict[str, Any]:
    """Fetch full generation context from Langfuse using trace ID"""
    try:
        from langfuse import Langfuse
        langfuse = Langfuse()
        trace = langfuse.get_trace(trace_id)

        return {
            "full_prompt": trace.input,
            "model_details": trace.model,
            "cost": trace.cost,
            "tokens": trace.usage,
            "duration": trace.duration,
            "tags": trace.tags,
            "metadata": trace.metadata
        }
    except Exception as e:
        return {"error": f"Could not fetch context: {e}"}

def save_output(content: str, filename: str, output_dir: str = "outputs") -> str:
    """Save content to output directory with timestamp (legacy method)"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"{timestamp}_{filename}"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return str(output_path) 
