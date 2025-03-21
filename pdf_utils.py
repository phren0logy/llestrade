"""
PDF utility functions for the Forensic Psych Report Drafter.
Handles PDF file operations like splitting and merging.
"""

import os
import json
import shutil
from pathlib import Path
from PyPDF2 import PdfReader, PdfWriter

# Azure Document Intelligence imports
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, DocumentContentFormat, AnalyzeResult

def get_pdf_page_count(pdf_path):
    """
    Get the number of pages in a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        int: Number of pages in the PDF
    """
    with open(pdf_path, 'rb') as file:
        reader = PdfReader(file)
        return len(reader.pages)


def split_large_pdf(pdf_path, output_dir, max_pages=1750, overlap=10):
    """
    Split a large PDF into smaller segments with overlap.
    
    Args:
        pdf_path: Path to the PDF file to split
        output_dir: Directory to save the split PDF files
        max_pages: Maximum number of pages per segment
        overlap: Number of pages to overlap between segments
        
    Returns:
        list: Paths to the split PDF files
    """
    # Get filename without extension and the extension
    pdf_filename = os.path.basename(pdf_path)
    filename_base, ext = os.path.splitext(pdf_filename)
    
    # Create a reader object
    with open(pdf_path, 'rb') as file:
        reader = PdfReader(file)
        total_pages = len(reader.pages)
        
        # If the PDF is not large enough to split, return the original path
        if total_pages <= max_pages:
            return [pdf_path]
        
        # Calculate how many segments we'll need
        segment_count = (total_pages - 1) // max_pages + 1
        output_files = []
        
        # Split the PDF into segments
        for i in range(segment_count):
            start_page = max(0, i * max_pages - overlap if i > 0 else 0)
            end_page = min(total_pages, (i + 1) * max_pages)
            
            # Create a writer for this segment
            writer = PdfWriter()
            
            # Add the relevant pages to the writer
            for page_num in range(start_page, end_page):
                writer.add_page(reader.pages[page_num])
            
            # Determine output filename for this segment
            output_filename = f"{filename_base}_part{i+1:03d}_{start_page+1:05d}-{end_page:05d}{ext}"
            output_path = os.path.join(output_dir, output_filename)
            
            # Write the output file
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
            
            output_files.append(output_path)
        
        return output_files


def prepare_pdf_files(pdf_files, output_dir, max_pages=1750, overlap=10):
    """
    Process PDF files, splitting large ones and organizing them.
    
    Args:
        pdf_files: List of paths to PDF files
        output_dir: Directory to save processed PDF files
        max_pages: Maximum number of pages per segment
        overlap: Number of pages to overlap between segments
        
    Returns:
        tuple: (processed_files, temp_dir)
            processed_files: List of paths to processed PDF files
            temp_dir: Path to the temporary directory containing split files
    """
    # Create a temporary directory inside the output directory
    temp_dir = os.path.join(output_dir, "temp_pdf_processing")
    os.makedirs(temp_dir, exist_ok=True)
    
    processed_files = []
    
    for pdf_path in pdf_files:
        # Check the page count
        page_count = get_pdf_page_count(pdf_path)
        
        if page_count > max_pages:
            # Split the large PDF
            split_files = split_large_pdf(pdf_path, temp_dir, max_pages, overlap)
            processed_files.extend(split_files)
        else:
            # Just add the original file to the processed list
            processed_files.append(pdf_path)
    
    return processed_files, temp_dir


def cleanup_temp_files(temp_dir):
    """
    Remove the temporary directory and its contents.
    
    Args:
        temp_dir: Path to the temporary directory
    """
    shutil.rmtree(temp_dir, ignore_errors=True)


def process_pdf_with_azure(
    pdf_path, 
    output_dir, 
    json_dir=None, 
    markdown_dir=None, 
    endpoint=None, 
    key=None
):
    """
    Process a PDF file using Azure Document Intelligence.
    
    Args:
        pdf_path: Path to the PDF file to process
        output_dir: Base output directory
        json_dir: Directory for JSON output (if None, will be created in output_dir)
        markdown_dir: Directory for markdown output (if None, will be created in output_dir)
        endpoint: Azure Document Intelligence endpoint
        key: Azure Document Intelligence API key
        
    Returns:
        tuple: (json_path, markdown_path) - Paths to the created files
    
    Raises:
        ValueError: If the Azure endpoint or key is not provided
        Exception: If there's an error processing the file
    """
    # Check for Azure credentials
    if not endpoint or not key:
        # Look for environment variables
        endpoint = os.getenv("AZURE_ENDPOINT")
        key = os.getenv("AZURE_KEY")
        
        if not endpoint or not key:
            raise ValueError("Azure endpoint and key must be provided or set as environment variables")
    
    # Create output directories if needed
    if not json_dir:
        json_dir = os.path.join(output_dir, "json")
    if not markdown_dir:
        markdown_dir = os.path.join(output_dir, "markdown")
    
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(markdown_dir, exist_ok=True)
    
    # Get the file name for the output files
    file_name = os.path.basename(pdf_path)
    base_name = os.path.splitext(file_name)[0]
    
    # Define output file paths
    json_path = os.path.join(json_dir, f"{base_name}.json")
    markdown_path = os.path.join(markdown_dir, f"{base_name}.md")
    
    # Skip if both files already exist
    if os.path.exists(json_path) and os.path.exists(markdown_path):
        return json_path, markdown_path
    
    # Initialize the Document Intelligence client
    document_intelligence_client = DocumentIntelligenceClient(
        endpoint=endpoint, 
        credential=AzureKeyCredential(key)
    )
    
    # Process the file with Azure Document Intelligence
    try:
        with open(pdf_path, "rb") as file:
            # Process for markdown
            markdown_poller = document_intelligence_client.begin_analyze_document(
                "prebuilt-layout",
                AnalyzeDocumentRequest(body=file),
                output_content_format=DocumentContentFormat.MARKDOWN
            )
            
            # Reset file pointer for JSON processing
            file.seek(0)
            
            # Process for JSON (default format)
            json_poller = document_intelligence_client.begin_analyze_document(
                "prebuilt-layout",
                AnalyzeDocumentRequest(body=file)
            )
        
        # Get the results
        markdown_result = markdown_poller.result()
        json_result = json_poller.result()
        
        # Save markdown content
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(f"# {file_name}\n\n")
            f.write(markdown_result.content)
        
        # Save JSON content
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_result.as_dict(), f, indent=4)
        
        return json_path, markdown_path
    
    except Exception as e:
        raise Exception(f"Error processing {pdf_path} with Azure: {str(e)}")


def process_pdfs_with_azure(
    pdf_files, 
    output_dir, 
    endpoint=None, 
    key=None
):
    """
    Process multiple PDF files using Azure Document Intelligence.
    
    Args:
        pdf_files: List of paths to PDF files
        output_dir: Base output directory
        endpoint: Azure Document Intelligence endpoint
        key: Azure Document Intelligence API key
        
    Returns:
        dict: Dictionary with information about processed files
    """
    # Create output directories
    json_dir = os.path.join(output_dir, "json")
    markdown_dir = os.path.join(output_dir, "markdown")
    
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(markdown_dir, exist_ok=True)
    
    # Track processing results
    results = {
        "total": len(pdf_files),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "files": []
    }
    
    # Process each file
    for pdf_path in pdf_files:
        try:
            # Check if files already exist
            file_name = os.path.basename(pdf_path)
            base_name = os.path.splitext(file_name)[0]
            json_path = os.path.join(json_dir, f"{base_name}.json")
            markdown_path = os.path.join(markdown_dir, f"{base_name}.md")
            
            if os.path.exists(json_path) and os.path.exists(markdown_path):
                # Skip if both files already exist
                results["skipped"] += 1
                results["files"].append({
                    "pdf": pdf_path,
                    "status": "skipped",
                    "json": json_path,
                    "markdown": markdown_path
                })
                continue
            
            # Process the file
            json_path, markdown_path = process_pdf_with_azure(
                pdf_path, 
                output_dir, 
                json_dir, 
                markdown_dir, 
                endpoint, 
                key
            )
            
            results["processed"] += 1
            results["files"].append({
                "pdf": pdf_path,
                "status": "processed",
                "json": json_path,
                "markdown": markdown_path
            })
            
        except Exception as e:
            results["failed"] += 1
            results["files"].append({
                "pdf": pdf_path,
                "status": "failed",
                "error": str(e)
            })
    
    return results
