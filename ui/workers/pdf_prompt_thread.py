"""
PDF Prompt Thread module for the Forensic Psych Report Drafter.
Handles processing PDF files with Claude using native PDF handling and extended thinking.
"""

import os
import time
import logging
from typing import Dict, Any
from pathlib import Path
from PySide6.QtCore import QThread, Signal

from llm.factory import create_provider
from src.core.prompt_manager import PromptManager

class PDFPromptThread(QThread):
    """Thread for processing PDFs with Claude in the background."""
    
    update_signal = Signal(str)
    progress_signal = Signal(int, int)
    finished_signal = Signal(dict)
    
    def __init__(self, pdf_path: str, prompt_text: str, output_dir: str):
        """Initialize the thread with paths to PDF and prompt."""
        super().__init__()
        self.pdf_path = pdf_path
        self.prompt_text = prompt_text
        self.output_dir = output_dir
        self.result = None
        self.thinking_budget_tokens = 16000  # Default thinking budget tokens
        
    def run(self):
        """Run the processing on the background thread."""
        try:
            # Initialize the LLM provider using factory
            self.update_signal.emit("Initializing LLM provider...")
            # Use Anthropic specifically for PDF processing since it has native PDF support
            llm_provider = create_provider(provider="anthropic")
            
            # Check if the PDF file exists
            if not os.path.exists(self.pdf_path):
                raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")
                
            # Get the PDF filename for later use in output files
            pdf_filename = os.path.basename(self.pdf_path)
            pdf_name = os.path.splitext(pdf_filename)[0]
            
            # Update progress
            self.update_signal.emit(f"Processing PDF with Claude: {pdf_filename}")
            self.progress_signal.emit(10, 100)
            
            # Prepare for PDF processing with extended thinking
            self.update_signal.emit("Sending PDF and prompt to Claude (this may take a while)...")
            self.progress_signal.emit(20, 100)
            
            # Initialize PromptManager
            try:
                app_dir = Path(__file__).parent.parent.parent
                template_dir = app_dir / 'prompt_templates'
                prompt_manager = PromptManager(template_dir=template_dir)
                system_prompt = prompt_manager.get_system_prompt()
            except Exception as e:
                logging.error(f"Error initializing PromptManager: {e}")
                system_prompt = "You are an advanced assistant designed to help a forensic psychiatrist. Your task is to analyze and objectively document case information in a formal clinical style, maintaining professional psychiatric documentation standards."
            
            self.update_signal.emit("Processing with Claude's PDF handling and extended thinking...")
            self.progress_signal.emit(40, 100)
            
            # Call Claude API with the unified pdf_and_thinking method
            try:
                self.update_signal.emit("Claude is analyzing the PDF...")
                self.progress_signal.emit(60, 100)
                
                # Use the new unified method for processing PDFs with thinking
                result = llm_provider.generate_with_pdf_and_thinking(
                    prompt=self.prompt_text,
                    pdf_file_path=self.pdf_path,
                    model="claude-3-7-sonnet-20250219",
                    max_tokens=32000,
                    temperature=1.0,  # As required by Anthropic for thinking mode
                    system_prompt=system_prompt,
                    thinking_budget_tokens=self.thinking_budget_tokens
                )
                
                # Store the result
                self.result = result
                
                # Save content to file
                self.update_signal.emit("Saving results to files...")
                self.progress_signal.emit(80, 100)
                
                # Create output directory if it doesn't exist
                if not os.path.exists(self.output_dir):
                    os.makedirs(self.output_dir)
                
                # Generate filenames
                timestamp = time.strftime("%Y-%m-%d")
                content_filename = f"{timestamp}-{pdf_name}-content.md"
                thinking_filename = f"{timestamp}-{pdf_name}-thinking.md"
                
                # Save content and thinking to separate files
                content_path = os.path.join(self.output_dir, content_filename)
                thinking_path = os.path.join(self.output_dir, thinking_filename)
                
                with open(content_path, "w", encoding="utf-8") as f:
                    f.write(result.get("content", "") or "")
                
                with open(thinking_path, "w", encoding="utf-8") as f:
                    f.write(result.get("thinking", "") or "")
                
                self.update_signal.emit(f"Results saved to: {self.output_dir}")
                self.update_signal.emit(f"Content file: {content_filename}")
                self.update_signal.emit(f"Thinking file: {thinking_filename}")
                
                # Add file paths to result
                self.result["content_file"] = content_path
                self.result["thinking_file"] = thinking_path
                
            except Exception as e:
                logging.error(f"Error processing PDF with Claude: {str(e)}")
                self.update_signal.emit(f"Error: {str(e)}")
                self.result = {
                    "success": False,
                    "error": str(e)
                }
            
            # Complete progress
            self.progress_signal.emit(100, 100)
            self.update_signal.emit("PDF processing complete!")
            
            # Emit the finished signal with the result
            self.finished_signal.emit(self.result)
            
        except Exception as e:
            logging.error(f"Error in PDF prompt thread: {str(e)}")
            self.update_signal.emit(f"Error: {str(e)}")
            self.finished_signal.emit({
                "success": False,
                "error": str(e)
            })