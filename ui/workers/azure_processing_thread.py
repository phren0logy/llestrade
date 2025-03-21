"""
Worker thread for processing PDF files with Azure Document Intelligence.
"""

import os
from PyQt6.QtCore import QThread, pyqtSignal

from pdf_utils import (
    process_pdfs_with_azure,
)


class AzureProcessingThread(QThread):
    """Worker thread for processing PDF files with Azure Document Intelligence."""

    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

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

            # Process files in batches to update progress
            total_files = len(self.pdf_files)
            results = {
                "total": total_files,
                "processed": 0,
                "skipped": 0,
                "failed": 0,
                "files": [],
            }

            # Process each file and update progress
            for i, pdf_path in enumerate(self.pdf_files):
                try:
                    # Update progress
                    progress_pct = int((i / total_files) * 100)
                    self.progress_signal.emit(
                        progress_pct,
                        f"Processing with Azure: {os.path.basename(pdf_path)}",
                    )

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

                    # Process individual file
                    file_result = process_pdfs_with_azure(
                        [pdf_path], self.output_dir, self.azure_endpoint, self.azure_key
                    )

                    # Update results
                    results["processed"] += file_result["processed"]
                    results["skipped"] += file_result["skipped"]
                    results["failed"] += file_result["failed"]
                    results["files"].extend(file_result["files"])

                except Exception as e:
                    results["failed"] += 1
                    results["files"].append(
                        {"pdf": pdf_path, "status": "failed", "error": str(e)}
                    )

            # Signal completion with results
            self.finished_signal.emit(results)

        except Exception as e:
            self.error_signal.emit(f"Error during Azure processing: {str(e)}")
