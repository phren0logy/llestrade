"""
Worker thread for processing PDF files.
"""

import os
from PyQt6.QtCore import QThread, pyqtSignal

from pdf_utils import (
    prepare_pdf_files,
)


class PDFProcessingThread(QThread):
    """Worker thread for processing PDF files."""

    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(list, str)
    error_signal = pyqtSignal(str)

    def __init__(self, pdf_files, output_dir, max_pages=1750, overlap=10):
        """Initialize the thread with the PDF files to process."""
        super().__init__()
        self.pdf_files = pdf_files
        self.output_dir = output_dir
        self.max_pages = max_pages
        self.overlap = overlap

    def run(self):
        """Run the PDF processing operations."""
        try:
            processed_files = []
            temp_dir = None

            # Process PDF files, showing progress
            for i, pdf_path in enumerate(self.pdf_files):
                try:
                    # Update progress
                    progress_pct = int((i / len(self.pdf_files)) * 100)
                    self.progress_signal.emit(
                        progress_pct, f"Checking: {os.path.basename(pdf_path)}"
                    )

                    # If this is the first file, create the temp directory and initialize
                    if i == 0:
                        processed_files, temp_dir = prepare_pdf_files(
                            [pdf_path], self.output_dir, self.max_pages, self.overlap
                        )
                    else:
                        # Process each file and add to the processed list
                        new_files, _ = prepare_pdf_files(
                            [pdf_path], temp_dir, self.max_pages, self.overlap
                        )
                        processed_files.extend(new_files)

                except Exception as e:
                    self.error_signal.emit(f"Error processing {pdf_path}: {str(e)}")
                    return

            # Signal completion with processed files and temp directory
            self.finished_signal.emit(processed_files, temp_dir)

        except Exception as e:
            self.error_signal.emit(f"Error during PDF processing: {str(e)}")
