"""
Worker thread for processing PDF files.
"""

import os

from PySide6.QtCore import QThread, Signal

from src.core.pdf_utils import (
    get_pdf_page_count,
    prepare_pdf_files,
    process_pdf_with_azure,
    split_large_pdf,
)


class PDFProcessingThread(QThread):
    """Worker thread for processing PDF files."""

    progress_signal = Signal(int, str)
    finished_signal = Signal(list)
    error_signal = Signal(str)

    def __init__(self, pdf_files, output_dir, max_pages=1750, overlap=10):
        """Initialize the thread with the PDF files to process."""
        super().__init__()
        self.pdf_files = pdf_files
        self.output_dir = output_dir
        self.max_pages = max_pages
        self.overlap = overlap

    def run(self):
        """Process the selected PDF files and save them to the output directory."""
        try:
            # Create a dedicated temp directory
            temp_dir = os.path.join(self.output_dir, "temp_pdf_processing")
            os.makedirs(temp_dir, exist_ok=True)

            self.progress_signal.emit(5, f"Created temp directory: {temp_dir}")

            # Track progress statistics
            total_files = len(self.pdf_files)
            processed_count = 0

            # Update initial progress
            self.progress_signal.emit(
                10, f"Beginning processing of {total_files} PDF files..."
            )

            results = []

            # Process each PDF file
            for i, pdf_file in enumerate(self.pdf_files):
                # Calculate progress percentage
                progress = 10 + int((i / total_files) * 80)  # Leave 10% for final steps

                # Get the file name without path and extension
                file_name = os.path.basename(pdf_file)
                base_name = os.path.splitext(file_name)[0]

                # Update progress
                self.progress_signal.emit(
                    progress, f"Processing file {i+1}/{total_files}: {file_name}"
                )

                try:
                    # Check if the file exists
                    if not os.path.exists(pdf_file):
                        self.progress_signal.emit(
                            progress, f"File not found (skipping): {pdf_file}"
                        )
                        continue

                    # Check file size
                    file_size_mb = os.path.getsize(pdf_file) / (1024 * 1024)
                    self.progress_signal.emit(
                        progress, f"Processing {file_name} ({file_size_mb:.1f} MB)"
                    )

                    # Process the file
                    self.progress_signal.emit(
                        progress, f"Converting {file_name} to text and markdown..."
                    )

                    # Create target markdown file
                    self.progress_signal.emit(
                        progress + 1,
                        f"Processing {file_name} with Azure Document Intelligence...",
                    )

                    # Get Azure credentials from environment
                    azure_endpoint = os.getenv("AZURE_ENDPOINT")
                    azure_key = os.getenv("AZURE_KEY")

                    if not azure_endpoint or not azure_key:
                        self.progress_signal.emit(
                            progress,
                            f"Azure credentials not found in environment variables. Skipping Azure processing.",
                        )
                        results.append(
                            {
                                "pdf": pdf_file,
                                "status": "failed",
                                "error": "Azure credentials not found",
                            }
                        )
                        continue

                    # Use the proper output directories
                    try:
                        # Make sure the markdown directory exists
                        markdown_dir = os.path.join(self.output_dir, "markdown")
                        json_dir = os.path.join(self.output_dir, "json")
                        os.makedirs(markdown_dir, exist_ok=True)
                        os.makedirs(json_dir, exist_ok=True)

                        # Process the PDF with Azure
                        json_path, markdown_path = process_pdf_with_azure(
                            pdf_file,
                            self.output_dir,
                            json_dir,
                            markdown_dir,
                            azure_endpoint,
                            azure_key,
                        )

                        # Check if conversion was successful
                        if os.path.exists(markdown_path) and os.path.exists(json_path):
                            self.progress_signal.emit(
                                progress + 2,
                                f"Successfully processed {file_name} with Azure Document Intelligence",
                            )
                            processed_count += 1
                            results.append(
                                {
                                    "pdf": pdf_file,
                                    "markdown": markdown_path,
                                    "json": json_path,
                                    "status": "success",
                                }
                            )
                        else:
                            self.progress_signal.emit(
                                progress,
                                f"Failed to process {file_name} with Azure Document Intelligence",
                            )
                            results.append(
                                {
                                    "pdf": pdf_file,
                                    "status": "failed",
                                    "error": "Azure processing failed",
                                }
                            )
                    except Exception as azure_error:
                        self.progress_signal.emit(
                            progress,
                            f"Error during Azure processing: {str(azure_error)}",
                        )
                        results.append(
                            {
                                "pdf": pdf_file,
                                "status": "failed",
                                "error": str(azure_error),
                            }
                        )

                except Exception as e:
                    self.progress_signal.emit(
                        progress, f"Error processing {file_name}: {str(e)}"
                    )
                    results.append(
                        {"pdf": pdf_file, "status": "failed", "error": str(e)}
                    )

            # Final cleanup and report
            try:
                # Cleanup temp directory if needed and it exists
                if os.path.exists(temp_dir) and os.path.isdir(temp_dir):
                    # Only remove files, not the directory itself
                    for temp_file in os.listdir(temp_dir):
                        temp_file_path = os.path.join(temp_dir, temp_file)
                        if os.path.isfile(temp_file_path):
                            try:
                                os.remove(temp_file_path)
                                self.progress_signal.emit(
                                    95, f"Removed temporary file: {temp_file}"
                                )
                            except Exception as e:
                                self.progress_signal.emit(
                                    95,
                                    f"Failed to remove temporary file {temp_file}: {str(e)}",
                                )
            except Exception as cleanup_error:
                self.progress_signal.emit(
                    95, f"Error during cleanup: {str(cleanup_error)}"
                )

            # Final progress update
            self.progress_signal.emit(
                100,
                f"PDF processing complete: {processed_count}/{total_files} files processed successfully",
            )

            # Emit the finished signal with the results
            self.finished_signal.emit(results)

        except Exception as e:
            # Handle any exceptions
            self.error_signal.emit(f"Error during PDF processing: {str(e)}")
