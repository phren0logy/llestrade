"""
Worker thread for processing PDF files with Azure Document Intelligence.
"""

import os
from PySide6.QtCore import QThread, Signal

from src.core.pdf_utils import (
    process_pdfs_with_azure,
)


class AzureProcessingThread(QThread):
    """Worker thread for processing PDF files with Azure Document Intelligence."""

    progress_signal = Signal(int, str)
    finished_signal = Signal(dict)
    error_signal = Signal(str)

    def __init__(self, pdf_files, output_dir, azure_endpoint=None, azure_key=None):
        """Initialize the thread with the PDF files to process with Azure."""
        super().__init__()
        self.pdf_files = pdf_files
        self.output_dir = output_dir
        self.azure_endpoint = azure_endpoint
        self.azure_key = azure_key

    def run(self):
        """Run the Azure Document Intelligence processing operations."""
        try:
            # Send initial progress
            self.progress_signal.emit(
                0,
                f"Starting Azure Document Intelligence processing for {len(self.pdf_files)} files",
            )

            # Log Azure credentials (without sensitive details)
            self.progress_signal.emit(
                5,
                f"Using Azure endpoint: {self.azure_endpoint[:20]}... (truncated)"
            )
            if self.azure_key:
                self.progress_signal.emit(
                    5,
                    f"API key available: {'Yes' if self.azure_key else 'No'}"
                )
            else:
                self.error_signal.emit("Azure API key is missing or empty")
                return

            # Process files in batches to update progress
            total_files = len(self.pdf_files)
            results = {
                "total": total_files,
                "processed": 0,
                "skipped": 0,
                "failed": 0,
                "files": [],
            }

            # Check if there are any files to process
            if not self.pdf_files:
                self.error_signal.emit("No PDF files to process with Azure")
                return

            # Create output directories
            try:
                os.makedirs(os.path.join(self.output_dir, "json"), exist_ok=True)
                os.makedirs(os.path.join(self.output_dir, "markdown"), exist_ok=True)
                self.progress_signal.emit(10, "Created output directories for Azure results")
            except Exception as e:
                self.error_signal.emit(f"Error creating output directories: {str(e)}")
                return

            # Process each file and update progress
            for i, pdf_path in enumerate(self.pdf_files):
                try:
                    # Update progress
                    progress_pct = 10 + int((i / total_files) * 80)  # Save 10% for completion
                    self.progress_signal.emit(
                        progress_pct,
                        f"Processing with Azure ({i+1}/{total_files}): {os.path.basename(pdf_path)}",
                    )

                    # Check if file exists
                    if not os.path.exists(pdf_path):
                        self.progress_signal.emit(
                            progress_pct,
                            f"File not found: {pdf_path}"
                        )
                        results["failed"] += 1
                        results["files"].append(
                            {"pdf": pdf_path, "status": "failed", "error": "File not found"}
                        )
                        continue

                    # Get basename for checking if already processed
                    basename = os.path.splitext(os.path.basename(pdf_path))[0]
                    json_file = os.path.join(
                        self.output_dir, "json", f"{basename}.json"
                    )
                    md_file = os.path.join(
                        self.output_dir, "markdown", f"{basename}.md"
                    )

                    # Check if already processed
                    if os.path.exists(json_file) and os.path.exists(md_file):
                        self.progress_signal.emit(
                            progress_pct,
                            f"Already processed (skipping): {os.path.basename(pdf_path)}"
                        )
                        results["skipped"] += 1
                        results["files"].append(
                            {
                                "pdf": pdf_path,
                                "status": "skipped",
                                "json": json_file,
                                "markdown": md_file,
                            }
                        )
                        continue

                    # Update status
                    self.progress_signal.emit(
                        progress_pct + 2,
                        f"Sending to Azure: {os.path.basename(pdf_path)} ({os.path.getsize(pdf_path)/1024/1024:.1f} MB)"
                    )

                    # Process individual file with detailed error handling
                    try:
                        file_result = process_pdfs_with_azure(
                            [pdf_path], self.output_dir, self.azure_endpoint, self.azure_key
                        )
                        
                        # Update progress after successful processing
                        self.progress_signal.emit(
                            progress_pct + 5,
                            f"Successfully processed with Azure: {os.path.basename(pdf_path)}"
                        )

                        # Update results
                        results["processed"] += file_result["processed"]
                        results["skipped"] += file_result["skipped"]
                        results["failed"] += file_result["failed"]
                        results["files"].extend(file_result["files"])
                    
                    except Exception as process_error:
                        error_msg = str(process_error)
                        self.progress_signal.emit(
                            progress_pct,
                            f"Error with Azure processing: {error_msg}"
                        )
                        results["failed"] += 1
                        results["files"].append(
                            {"pdf": pdf_path, "status": "failed", "error": error_msg}
                        )

                except Exception as e:
                    error_msg = str(e)
                    self.progress_signal.emit(
                        progress_pct,
                        f"Exception during processing: {error_msg}"
                    )
                    results["failed"] += 1
                    results["files"].append(
                        {"pdf": pdf_path, "status": "failed", "error": error_msg}
                    )

            # Signal completion with results
            self.progress_signal.emit(100, f"Azure processing complete: {results['processed']} processed, {results['failed']} failed")
            self.finished_signal.emit(results)

        except Exception as e:
            error_msg = str(e)
            self.progress_signal.emit(0, f"Critical error: {error_msg}")
            self.error_signal.emit(f"Error during Azure processing: {error_msg}")
