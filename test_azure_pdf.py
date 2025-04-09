#!/usr/bin/env python
"""
Test script to diagnose Azure PDF processing issues.
"""

import os
import sys
import traceback
from pathlib import Path

def test_azure_pdf_processing():
    """Test processing a single PDF file with Azure Document Intelligence."""
    try:
        from pdf_utils import process_pdfs_with_azure, test_azure_connection
        
        # First, test the Azure connection
        connection_result = test_azure_connection()
        print(f"Azure connection test: {connection_result}")
        
        if not connection_result.get('success', False):
            print(f"Azure connection failed: {connection_result.get('error', 'Unknown error')}")
            return
        
        # Get Azure credentials from environment
        azure_endpoint = os.getenv("AZURE_ENDPOINT")
        azure_key = os.getenv("AZURE_KEY")
        
        print(f"Using Azure endpoint: {azure_endpoint[:20]}... (truncated)")
        print(f"API key available: {'Yes' if azure_key else 'No'}")
        
        # Get the PDF files directory
        script_dir = Path(__file__).parent
        
        # Ask for a PDF file path or use a sample
        if len(sys.argv) > 1:
            pdf_path = sys.argv[1]
        else:
            # Prompt for PDF file
            pdf_path = input("Enter path to a PDF file to test: ")
        
        # Check if file exists
        if not os.path.exists(pdf_path):
            print(f"Error: PDF file not found: {pdf_path}")
            return
        
        # Set output directory
        output_dir = os.path.join(script_dir, "test_azure_output")
        os.makedirs(output_dir, exist_ok=True)
        print(f"Output directory: {output_dir}")
        
        # Process the PDF
        print(f"Starting Azure processing for {pdf_path}...")
        try:
            result = process_pdfs_with_azure([pdf_path], output_dir, azure_endpoint, azure_key)
            print("Processing result:")
            for key, value in result.items():
                if key != "files":
                    print(f"  {key}: {value}")
                else:
                    print("  Files:")
                    for file_info in value:
                        print(f"    - {file_info.get('pdf', 'Unknown')}: {file_info.get('status', 'Unknown')}")
                        if file_info.get('status') == 'failed':
                            print(f"      Error: {file_info.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"Error during PDF processing: {str(e)}")
            traceback.print_exc()
            
    except ImportError as e:
        print(f"Import error: {str(e)}")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    test_azure_pdf_processing()
