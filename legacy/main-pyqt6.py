#!/usr/bin/env python3
"""
Forensic Psych Report Drafter - PyQt6 Implementation
A tool for forensic psychologists to draft reports from markdown templates and transcripts.
"""

import os
import platform
import site
import sys
from pathlib import Path

# Set debugging
os.environ["QT_DEBUG_PLUGINS"] = "1"


# Find PyQt6 paths
def find_pyqt_paths():
    # Check all site-packages
    for site_dir in site.getsitepackages():
        qt_dir = os.path.join(site_dir, "PyQt6", "Qt6")
        if os.path.exists(qt_dir):
            return qt_dir
    return None


qt_dir = find_pyqt_paths()
if qt_dir:
    print(f"Found Qt directory: {qt_dir}")

    # Set explicit paths before importing
    if platform.system() == "Darwin":
        os.environ["DYLD_LIBRARY_PATH"] = (
            f"{qt_dir}:{os.environ.get('DYLD_LIBRARY_PATH', '')}"
        )
        print(f"Set DYLD_LIBRARY_PATH: {os.environ['DYLD_LIBRARY_PATH']}")

    # Set plugin paths
    os.environ["QT_PLUGIN_PATH"] = os.path.join(qt_dir, "plugins")
    print(f"Set QT_PLUGIN_PATH: {os.environ['QT_PLUGIN_PATH']}")

    # Set platform plugin path
    platform_dir = os.path.join(qt_dir, "plugins", "platforms")
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platform_dir
    print(
        f"Set QT_QPA_PLATFORM_PLUGIN_PATH: {os.environ['QT_QPA_PLATFORM_PLUGIN_PATH']}"
    )

    # Check for cocoa plugin
    cocoa_path = os.path.join(platform_dir, "libqcocoa.dylib")
    if os.path.exists(cocoa_path):
        print(f"Found cocoa plugin: {cocoa_path}")
    else:
        print(f"WARNING: Cocoa plugin not found at {cocoa_path}")
        if os.path.exists(platform_dir):
            print("Files in platforms directory:")
            for f in os.listdir(platform_dir):
                print(f"  - {f}")
else:
    print("Could not find PyQt6 Qt6 directory")

# Enable high DPI scaling
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

# Now import PyQt6 and utilities
try:
    from PyQt6.QtCore import (
        QEvent,
        QPoint,
        QSize,
        Qt,
        QTimer
    )
    from PyQt6.QtGui import QAction, QFont
    from PyQt6.QtWidgets import (
        QApplication,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QTextEdit,
        QPushButton,
        QScrollArea,
        QSplitter,
        QStatusBar,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )

    # Import utility functions
    from ingest_markdown import generate_template_fragments, ingest_and_split_markdown
    from llm_utils import (
        combine_transcript_with_fragments,
        generate_response,
        generate_response_with_extended_thinking,
        generate_response_with_pdf,
    )
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)


class ForensicReportDrafter(QMainWindow):
    """Main application window for the Forensic Psych Report Drafter."""

    def __init__(self):
        super().__init__()

        # Initialize variables
        self.current_prompts = []
        self.current_transcript_path = None
        self.current_prompt_path = None
        self.current_pdf_path = None

        # Set up the main window
        self.setWindowTitle("Forensic Psych Report Drafter")
        self.setGeometry(100, 100, 1000, 800)

        # Set up the status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Create the tab widget
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)

        # Create the tabs
        self.prompts_tab = QWidget()
        self.testing_tab = QWidget()
        self.refinement_tab = QWidget()

        # Add tabs to the widget
        self.tab_widget.addTab(self.prompts_tab, "Complex Markdown Report")
        self.tab_widget.addTab(self.testing_tab, "Phase 3 - Testing")
        self.tab_widget.addTab(self.refinement_tab, "Report Refinement")

        # Set up each tab
        self.setup_prompts_tab()
        self.setup_testing_tab()
        self.setup_refinement_tab()

    def setup_prompts_tab(self):
        """Set up the Prompts tab with buttons and text area."""
        # Create main layout
        layout = QVBoxLayout()

        # Create button area
        button_layout = QHBoxLayout()

        # Add markdown select button
        self.markdown_button = QPushButton("Select Markdown File")
        self.markdown_button.clicked.connect(self.select_markdown_file)
        button_layout.addWidget(self.markdown_button)

        # Add transcript select button
        self.transcript_button = QPushButton("Select Transcript File")
        self.transcript_button.clicked.connect(self.select_transcript_file)
        button_layout.addWidget(self.transcript_button)

        # Add process button (disabled by default)
        self.process_button = QPushButton("Process with LLM")
        self.process_button.clicked.connect(self.process_transcript)
        self.process_button.setEnabled(False)
        button_layout.addWidget(self.process_button)

        # Add save button (initially disabled)
        self.save_button = QPushButton("Save Results")
        self.save_button.clicked.connect(self.save_output_to_markdown)
        self.save_button.setEnabled(False)
        button_layout.addWidget(self.save_button)

        # Add copy button
        self.copy_button = QPushButton("Copy Selected Text")
        self.copy_button.clicked.connect(self.copy_to_clipboard)
        button_layout.addWidget(self.copy_button)

        # Add spacer to push buttons to the left
        button_layout.addStretch()

        # Add the button layout to the main layout
        layout.addLayout(button_layout)

        # Add label for transcript path
        self.transcript_label = QLabel("No transcript file selected.")
        layout.addWidget(self.transcript_label)

        # Add status label
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        # Create a vertical splitter to separate original markdown and processed output
        self.splitter = QSplitter(Qt.Orientation.Vertical)

        # Create another splitter for the top section (markdown results and transcript preview)
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Create text area for displaying markdown results
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFont(QFont("Menlo", 12))
        self.top_splitter.addWidget(self.result_text)

        # Create text area for displaying transcript preview
        self.transcript_preview = QTextEdit()
        self.transcript_preview.setReadOnly(True)
        self.transcript_preview.setFont(QFont("Menlo", 12))
        self.transcript_preview.setPlaceholderText(
            "Transcript preview will appear here"
        )
        self.top_splitter.addWidget(self.transcript_preview)

        # Add the top splitter to the main splitter
        self.splitter.addWidget(self.top_splitter)

        # Create text area for displaying processed output
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Menlo", 12))
        self.splitter.addWidget(self.output_text)

        # Add the splitter to the main layout
        layout.addWidget(self.splitter)

        # Set the layout for the widget
        self.prompts_tab.setLayout(layout)

    def setup_testing_tab(self):
        """Set up the Testing tab with buttons and text areas."""
        # Create main layout
        layout = QVBoxLayout()

        # Create button area
        button_layout = QHBoxLayout()

        # Add prompt select button
        self.prompt_button = QPushButton("Select Prompt File")
        self.prompt_button.clicked.connect(self.select_prompt_file)
        button_layout.addWidget(self.prompt_button)

        # Add PDF select button
        self.pdf_button = QPushButton("Select PDF File")
        self.pdf_button.clicked.connect(self.select_pdf_file)
        button_layout.addWidget(self.pdf_button)

        # Add process PDF button (disabled by default)
        self.process_pdf_button = QPushButton("Process PDF with LLM")
        self.process_pdf_button.clicked.connect(self.process_pdf_with_prompt)
        self.process_pdf_button.setEnabled(False)
        button_layout.addWidget(self.process_pdf_button)

        # Add copy button
        self.copy_pdf_button = QPushButton("Copy Selected Text")
        self.copy_pdf_button.clicked.connect(self.copy_pdf_output_to_clipboard)
        button_layout.addWidget(self.copy_pdf_button)

        # Add spacer to push buttons to the left
        button_layout.addStretch()

        # Add the button layout to the main layout
        layout.addLayout(button_layout)

        # Add labels for file paths
        self.prompt_label = QLabel("No prompt file selected.")
        layout.addWidget(self.prompt_label)

        self.pdf_label = QLabel("No PDF file selected.")
        layout.addWidget(self.pdf_label)

        # Add status label
        self.pdf_status_label = QLabel("")
        layout.addWidget(self.pdf_status_label)

        # Create text area for displaying PDF output
        self.pdf_output_text = QTextEdit()
        self.pdf_output_text.setReadOnly(True)
        self.pdf_output_text.setFont(QFont("Menlo", 12))

        # Add the text area to the main layout
        layout.addWidget(self.pdf_output_text)

        # Set the layout for the widget
        self.testing_tab.setLayout(layout)

    def setup_refinement_tab(self):
        """Set up the Report Refinement tab with buttons and text areas."""
        # Create main layout
        layout = QVBoxLayout()

        # Create button area
        button_layout = QHBoxLayout()

        # Add draft report select button
        self.draft_button = QPushButton("Select Draft Report")
        self.draft_button.clicked.connect(self.select_draft_report)
        button_layout.addWidget(self.draft_button)

        # Add transcript select button
        self.refinement_transcript_button = QPushButton("Select Transcript File")
        self.refinement_transcript_button.clicked.connect(
            self.select_refinement_transcript
        )
        button_layout.addWidget(self.refinement_transcript_button)

        # Add refine button (disabled by default)
        self.refine_button = QPushButton("Refine")
        self.refine_button.clicked.connect(self.refine_report)
        self.refine_button.setEnabled(False)
        button_layout.addWidget(self.refine_button)

        # Add save results button (disabled by default)
        self.save_refinement_button = QPushButton("Save Results")
        self.save_refinement_button.clicked.connect(self.save_refinement_results)
        self.save_refinement_button.setEnabled(False)
        button_layout.addWidget(self.save_refinement_button)

        # Add spacer to push buttons to the left
        button_layout.addStretch()

        # Add the button layout to the main layout
        layout.addLayout(button_layout)

        # Add prompt input area
        prompt_layout = QVBoxLayout()
        self.refinement_prompt_label = QLabel("Refinement Prompt:")
        prompt_layout.addWidget(self.refinement_prompt_label)

        # Configure QTextEdit for better editing - with proper height and scrolling
        self.refinement_prompt_text = QTextEdit()
        self.refinement_prompt_text.setMinimumHeight(120)  # Increased height for better usability
        self.refinement_prompt_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.refinement_prompt_text.setFont(QFont("Menlo", 12))
        self.refinement_prompt_text.setPlaceholderText(
            """This draft report, wrapped in <draft> tags, is a rough draft of a forensic psychiatric report. Perform the following steps to improve the report:
1. Check the report against the provided transcript, wrapped in <transcript> tags, for accuracy. Minor changes to punctuation and capitalization are OK and do not need to be changed.
2. Check each section for information that is repeated in other sections. Put this information in the most appropriate section, and reference that section in other parts of the report where that information was repeated.
3. Some information may not appear in the transcript, such as quotes from other documents or psychometric testing. Do not make changes to this information that does not appear in the transcript.
4. After making those changes, revise the document for readability. Preserve details that are important for accurate diagnosis and formulation.
5. Output only the final revised report."""
        )
        prompt_layout.addWidget(self.refinement_prompt_text)

        # Add prompt layout to main layout
        layout.addLayout(prompt_layout)

        # Add labels for file paths
        self.draft_label = QLabel("No draft report selected.")
        layout.addWidget(self.draft_label)

        self.refinement_transcript_label = QLabel("No transcript file selected.")
        layout.addWidget(self.refinement_transcript_label)

        # Add status label
        self.refinement_status_label = QLabel("")
        layout.addWidget(self.refinement_status_label)

        # Create a vertical splitter for the output
        self.refinement_splitter = QSplitter(Qt.Orientation.Vertical)

        # Create text area for displaying thinking output
        self.thinking_text = QTextEdit()
        self.thinking_text.setReadOnly(True)
        self.thinking_text.setFont(QFont("Menlo", 12))
        self.thinking_text.setPlaceholderText("LLM thinking will appear here")
        self.refinement_splitter.addWidget(self.thinking_text)

        # Create text area for displaying refined content
        self.refinement_output_text = QTextEdit()
        self.refinement_output_text.setReadOnly(True)
        self.refinement_output_text.setFont(QFont("Menlo", 12))
        self.refinement_output_text.setPlaceholderText(
            "Refined content will appear here"
        )
        self.refinement_splitter.addWidget(self.refinement_output_text)

        # Add the splitter to the main layout
        layout.addWidget(self.refinement_splitter)

        # Set the layout for the widget
        self.refinement_tab.setLayout(layout)

        # Initialize variables
        self.current_draft_path = None
        self.current_refinement_transcript_path = None
        self.draft_content = None
        self.refinement_transcript_content = None

    def select_markdown_file(self):
        """Open a file dialog to select a markdown file and process it."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Markdown File",
            "",
            "Markdown Files (*.md);;Text Files (*.txt);;All Files (*.*)",
        )

        if file_path:
            try:
                # Split the markdown file into parts
                parts = ingest_and_split_markdown(file_path)

                # Generate template fragments from the parts
                prompts = generate_template_fragments(parts)

                # Store the prompts
                self.current_prompts = prompts

                # Display the results
                self.display_results(parts, prompts)

                # Update status bar
                self.status_bar.showMessage(f"Loaded markdown file: {file_path}", 5000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
        else:
            self.status_bar.showMessage("No file selected", 3000)

    def display_results(self, parts, prompts):
        """Display the markdown parts and generated prompts in the text area."""
        # Clear existing content
        self.result_text.clear()

        # Display markdown parts
        self.result_text.append(f"=== ORIGINAL MARKDOWN SECTIONS ({len(parts)}) ===\n")
        for i, part in enumerate(parts, start=1):
            # Handle LangChain Document objects
            if hasattr(part, "page_content") and hasattr(part, "metadata"):
                content = part.page_content
                metadata = part.metadata
                header = metadata.get("Header 1", f"Section {i}")
                self.result_text.append(f"=== SECTION {i}: {header} ===\n{content}\n")
            else:
                # Fallback for non-LangChain document objects
                self.result_text.append(f"=== SECTION {i} ===\n{part}\n")

        # Display template fragments
        self.result_text.append(
            f"\n=== GENERATED TEMPLATE FRAGMENTS ({len(prompts)}) ===\n"
        )
        for i, prompt in enumerate(prompts, start=1):
            self.result_text.append(f"=== FRAGMENT {i} ===\n{prompt}\n")

    def select_transcript_file(self):
        """Open a file dialog to select a transcript file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Transcript File",
            "",
            "Text Files (*.txt);;PDF Files (*.pdf);;All Files (*.*)",
        )

        if file_path:
            self.transcript_label.setText(f"Transcript File Selected:\n{file_path}")
            self.current_transcript_path = file_path

            # Enable process button if we have both transcript and prompts
            if self.current_prompts:
                self.process_button.setEnabled(True)

            # Load and display transcript preview
            try:
                # Read the first 5000 characters of the transcript file
                with open(file_path, "r", encoding="utf-8") as f:
                    transcript_text = f.read(5000)

                # Display the preview
                self.transcript_preview.clear()
                self.transcript_preview.setPlainText(transcript_text)

                # Add an indication if this is just a preview
                file_size = os.path.getsize(file_path)
                if file_size > 5000:
                    self.transcript_preview.append(
                        "\n\n[... Preview only, file continues ...]"
                    )

            except Exception as e:
                self.transcript_preview.setPlainText(
                    f"Error loading transcript preview: {str(e)}"
                )

            # Update status bar
            self.status_bar.showMessage(f"Selected transcript file: {file_path}", 5000)
        else:
            self.status_bar.showMessage("No file selected", 3000)

    def process_transcript(self):
        """Process the transcript with the LLM using the generated prompts."""
        if not self.current_transcript_path or not self.current_prompts:
            QMessageBox.warning(
                self,
                "Warning",
                "Please select both a markdown template and a transcript file first.",
            )
            return

        # Show processing indicator
        self.status_label.setText("Processing... This may take a few minutes.")
        QApplication.processEvents()

        try:
            # Read the transcript file
            with open(self.current_transcript_path, "r", encoding="utf-8") as f:
                transcript_text = f.read()

            # Combine transcript with template fragments
            complete_prompts = combine_transcript_with_fragments(
                transcript_text, self.current_prompts
            )

            # Clear the output text
            self.output_text.clear()

            # Process each prompt with the LLM
            for i, prompt in enumerate(complete_prompts, start=1):
                QApplication.processEvents()

                # Set timeout parameters
                timeout = 120.0  # 2 minutes timeout
                max_retries = 2

                # Generate response with timeout handling
                result = generate_response(
                    prompt=prompt,
                    max_tokens=8000,
                    temperature=0.1,
                    timeout=timeout,
                    max_retries=max_retries,
                )

                if result["success"]:
                    self.output_text.append(f"{result['content']}\n\n")
                else:
                    self.output_text.append(
                        f"Error processing section {i}: {result['error']}\n\n"
                    )

                # Ensure the latest output is visible
                self.output_text.ensureCursorVisible()
                QApplication.processEvents()

            # Enable the save button once processing is complete
            self.save_button.setEnabled(True)

            self.status_label.setText("Processing complete!")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
            self.status_label.setText("Processing failed.")

    def save_output_to_markdown(self):
        """Save the processed output to a markdown file."""
        # Get the output content
        output_content = self.output_text.toPlainText()

        if not output_content.strip():
            self.status_bar.showMessage("No content to save", 3000)
            return

        # Suggest default filename
        default_filename = "report-objective-section.md"

        # Prompt user for file location with suggested filename
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Report Output",
            default_filename,
            "Markdown Files (*.md);;All Files (*.*)",
        )

        if not file_path:
            # User cancelled the save dialog
            self.status_bar.showMessage("Save cancelled", 3000)
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(output_content)
            self.status_bar.showMessage(f"Output saved to {file_path}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file: {str(e)}")
            self.status_bar.showMessage("Failed to save file", 3000)

    def copy_to_clipboard(self):
        """Copy the selected text from the output text area to clipboard."""
        # Check if selection is in the output text
        selected_text = self.output_text.textCursor().selectedText()
        if selected_text:
            QApplication.clipboard().setText(selected_text)
            self.status_bar.showMessage("Text copied to clipboard", 3000)
            return

        # If no selection in output text, check result text
        selected_text = self.result_text.textCursor().selectedText()
        if selected_text:
            QApplication.clipboard().setText(selected_text)
            self.status_bar.showMessage("Text copied to clipboard", 3000)
        else:
            self.status_bar.showMessage("No text selected", 3000)

    def select_prompt_file(self):
        """Open a file dialog to select a prompt file for PDF analysis."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Prompt File", "", "Text Files (*.txt);;All Files (*.*)"
        )

        if file_path:
            self.prompt_label.setText(f"Prompt File Selected:\n{file_path}")
            self.current_prompt_path = file_path

            # Enable the process button if we have both prompt and PDF files
            if self.current_pdf_path:
                self.process_pdf_button.setEnabled(True)

            # Update status bar
            self.status_bar.showMessage(f"Selected prompt file: {file_path}", 5000)
        else:
            self.status_bar.showMessage("No file selected", 3000)

    def select_pdf_file(self):
        """Open a file dialog to select a PDF file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select PDF File", "", "PDF Files (*.pdf);;All Files (*.*)"
        )

        if file_path:
            self.pdf_label.setText(f"PDF File Selected:\n{file_path}")
            self.current_pdf_path = file_path

            # Enable the process button if we have both prompt and PDF files
            if self.current_prompt_path:
                self.process_pdf_button.setEnabled(True)

            # Update status bar
            self.status_bar.showMessage(f"Selected PDF file: {file_path}", 5000)
        else:
            self.status_bar.showMessage("No file selected", 3000)

    def process_pdf_with_prompt(self):
        """Process the PDF file with the provided prompt using Claude's native PDF handling."""
        if not self.current_prompt_path or not self.current_pdf_path:
            QMessageBox.warning(
                self,
                "Warning",
                "Please select both a prompt file and a PDF file first.",
            )
            return

        # Show processing indicator
        self.pdf_status_label.setText("Processing PDF... This may take a few minutes.")
        QApplication.processEvents()

        try:
            # Read the prompt file
            with open(self.current_prompt_path, "r", encoding="utf-8") as f:
                prompt_text = f.read()

            # Set timeout parameters
            timeout = 120.0  # 2 minutes timeout
            max_retries = 2

            # Clear the output text
            self.pdf_output_text.clear()

            # Process the PDF with the LLM
            result = generate_response_with_pdf(
                prompt_text=prompt_text,
                pdf_file_path=self.current_pdf_path,
                max_tokens=8000,
                thinking_budget_tokens=1000,
                temperature=0.1,
                timeout=timeout,
                max_retries=max_retries,
            )

            if result["success"]:
                self.pdf_output_text.append(result["content"])

                # Show thinking process if available
                if "thinking" in result and result["thinking"]:
                    self.pdf_output_text.append("\n\n=== LLM THINKING PROCESS ===\n\n")
                    self.pdf_output_text.append(result["thinking"])

                self.pdf_status_label.setText("Processing complete!")

                # Offer to save the output to a markdown file
                if (
                    QMessageBox.question(
                        self,
                        "Save PDF Analysis Output",
                        "Would you like to save the output to a markdown file?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    == QMessageBox.StandardButton.Yes
                ):
                    output_content = self.pdf_output_text.toPlainText()
                    if self.save_pdf_output_to_markdown(output_content):
                        self.pdf_status_label.setText(
                            "Processing complete! Output saved to markdown file."
                        )
                    else:
                        self.pdf_status_label.setText(
                            "Processing complete! (Output not saved)"
                        )
            else:
                self.pdf_output_text.append(f"Error processing PDF: {result['error']}")
                self.pdf_status_label.setText("Processing failed.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
            self.pdf_status_label.setText("Processing failed.")

    def save_pdf_output_to_markdown(self, content):
        """Save the processed PDF output to a markdown file."""
        # Suggest default filename
        default_filename = "pdf-analysis-output.md"

        # Prompt user for file location with suggested filename
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF Analysis Output",
            default_filename,
            "Markdown Files (*.md);;All Files (*.*)",
        )

        if not file_path:
            # User cancelled the save dialog
            return False

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file: {str(e)}")
            return False

    def copy_pdf_output_to_clipboard(self):
        """Copy the selected text from the PDF output text area to clipboard."""
        selected_text = self.pdf_output_text.textCursor().selectedText()
        if selected_text:
            QApplication.clipboard().setText(selected_text)
            self.status_bar.showMessage("Text copied to clipboard", 3000)
        else:
            self.status_bar.showMessage("No text selected", 3000)

    def select_draft_report(self):
        """Open a file dialog to select a draft report markdown file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Draft Report",
            "",
            "Markdown Files (*.md);;Text Files (*.txt);;All Files (*.*)",
        )

        if file_path:
            try:
                # Read the draft report file
                with open(file_path, "r", encoding="utf-8") as f:
                    self.draft_content = f.read()

                # Update the label
                self.draft_label.setText(f"Draft Report Selected:\n{file_path}")
                self.current_draft_path = file_path

                # Enable the refine button if both files are selected
                if self.current_refinement_transcript_path:
                    self.refine_button.setEnabled(True)

                # Update status bar
                self.status_bar.showMessage(f"Selected draft report: {file_path}", 5000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
        else:
            self.status_bar.showMessage("No file selected", 3000)

    def select_refinement_transcript(self):
        """Open a file dialog to select a transcript file for refinement."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Transcript File", "", "Text Files (*.txt);;All Files (*.*)"
        )

        if file_path:
            try:
                # Read the transcript file
                with open(file_path, "r", encoding="utf-8") as f:
                    self.refinement_transcript_content = f.read()

                # Update the label
                self.refinement_transcript_label.setText(
                    f"Transcript File Selected:\n{file_path}"
                )
                self.current_refinement_transcript_path = file_path

                # Enable the refine button if both files are selected
                if self.current_draft_path:
                    self.refine_button.setEnabled(True)

                # Update status bar
                self.status_bar.showMessage(
                    f"Selected transcript file: {file_path}", 5000
                )
            except Exception as e:
                QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
        else:
            self.status_bar.showMessage("No file selected", 3000)

    def refine_report(self):
        """Process the draft report and transcript with LLM using extended thinking."""
        if not self.current_draft_path or not self.current_refinement_transcript_path:
            QMessageBox.warning(
                self,
                "Warning",
                "Please select both a draft report and a transcript file first.",
            )
            return

        # Show processing indicator
        self.refinement_status_label.setText(
            "Processing... This may take a few minutes."
        )
        QApplication.processEvents()

        try:
            # Wrap the draft content in draft tags
            wrapped_draft = f"<draft>\n{self.draft_content}\n</draft>"

            # Wrap the transcript content in transcript tags
            wrapped_transcript = (
                f"<transcript>\n{self.refinement_transcript_content}\n</transcript>"
            )

            # Get the current refinement prompt - force an update to ensure latest content
            QApplication.processEvents()
            refinement_prompt = self.refinement_prompt_text.toPlainText().strip()

            # Use default prompt if empty
            if not refinement_prompt:
                refinement_prompt = """This draft report, wrapped in <draft> tags, is a rough draft of a forensic psychiatric report. Perform the following steps to improve the report:
                1. Check the report against the provided transcript, wrapped in <transcript> tags, for accuracy. Minor changes to punctuation and capitalization are OK and do not need to be changed.
                2. Check each section for information that is repeated in other sections. Put this information in the most appropriate section, and reference that section in other parts of the report where that information was repeated.
                3. Some information may not appear in the transcript, such as quotes from other documents or psychometric testing. Do not make changes to this information that does not appear in the transcript.
                4. After making those changes, revise the document for readability. Preserve details that are important for accurate diagnosis and formulation.
                5. Output only the final revised report."""
                self.refinement_prompt_text.setPlainText(refinement_prompt)
                QApplication.processEvents()

            # Combine everything into a single prompt
            combined_prompt = (
                f"{refinement_prompt}\n\n{wrapped_draft}\n\n{wrapped_transcript}"
            )

            # Clear the output texts
            self.thinking_text.clear()
            self.refinement_output_text.clear()

            # Get timeout parameters
            timeout = 240.0  # 4 minutes timeout
            max_retries = 2

            # Use the generate_response_with_extended_thinking function
            result = generate_response_with_extended_thinking(
                prompt=combined_prompt,
                max_tokens=64000,
                thinking_budget_tokens=32000,
                timeout=timeout,
                max_retries=max_retries,
            )

            if result["success"]:
                # Display the thinking process
                if result["thinking"]:
                    self.thinking_text.setPlainText(result["thinking"])

                # Display the content
                if result["content"]:
                    self.refinement_output_text.setPlainText(result["content"])

                # Enable the save button
                self.save_refinement_button.setEnabled(True)
            else:
                error_message = result.get("error", "Unknown error occurred")
                self.refinement_output_text.setPlainText(f"Error: {error_message}")

            self.refinement_status_label.setText("Processing complete!")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
            self.refinement_status_label.setText("Processing failed.")

    def save_refinement_results(self):
        """Save the refinement output to a markdown file."""
        # Get the output content
        output_content = self.refinement_output_text.toPlainText()

        if not output_content.strip():
            self.status_bar.showMessage("No content to save", 3000)
            return

        # Suggest default filename based on the original draft
        if self.current_draft_path:
            draft_filename = os.path.basename(self.current_draft_path)
            default_filename = f"refined-{draft_filename}"
        else:
            default_filename = "refined-report.md"

        # Prompt user for file location with suggested filename
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Refined Report",
            default_filename,
            "Markdown Files (*.md);;All Files (*.*)",
        )

        if not file_path:
            # User cancelled the save dialog
            self.status_bar.showMessage("Save cancelled", 3000)
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(output_content)
            self.status_bar.showMessage(f"Refinement saved to {file_path}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file: {str(e)}")
            self.status_bar.showMessage("Failed to save file", 3000)


def main():
    """Main function to run the application."""
    app = QApplication(sys.argv)
    window = ForensicReportDrafter()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
