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

def save_output_with_metadata(content: str, filename: str, metadata: Dict[str, Any], output_dir: str = "outputs") -> str:
    """Save content with metadata header to output directory"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"{timestamp}_{filename}"
    
    # Create metadata header
    metadata_header = "---\n"
    metadata_header += yaml.dump(metadata, default_flow_style=False)
    metadata_header += "---\n\n"
    
    # Combine metadata and content
    full_content = metadata_header + content
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_content)
    
    return str(output_path)

def save_output(content: str, filename: str, output_dir: str = "outputs") -> str:
    """Save content to output directory with timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"{timestamp}_{filename}"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return str(output_path)

def read_metadata_from_file(file_path: str) -> Dict[str, Any]:
    """Extract metadata from a markdown file with YAML frontmatter"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if content.startswith('---\n'):
            # Find the end of frontmatter
            end_marker = content.find('\n---\n', 4)
            if end_marker != -1:
                frontmatter = content[4:end_marker]
                return yaml.safe_load(frontmatter)
    except:
        pass
    
    return {} 
