import platform
import tkinter as tk
from os import environ
from pathlib import Path
from sys import base_prefix
from tkinter import filedialog, messagebox, ttk

if not ("TCL_LIBRARY" in environ and "TK_LIBRARY" in environ):
    try:
        tk.Tk()
    except tk.TclError:
        tk_dir = "tcl" if platform.system() == "Windows" else "lib"
        tk_path = Path(base_prefix) / tk_dir
        environ["TCL_LIBRARY"] = str(next(tk_path.glob("tcl8.*")))
        environ["TK_LIBRARY"] = str(next(tk_path.glob("tk8.*")))

from ingest_markdown import generate_template_fragments, ingest_and_split_markdown
from llm_utils import (
    combine_transcript_with_fragments,
    generate_response,
    generate_response_with_pdf,
)


def select_markdown_file():
    file_path = filedialog.askopenfilename(
        title="Select Markdown File",
        filetypes=[
            ("Markdown files", "*.md"),
            ("Text files", "*.txt"),
            ("All files", "*.*"),
        ],
    )
    if file_path:
        # Split the markdown file into parts
        parts = ingest_and_split_markdown(file_path)

        # Generate template fragments from the parts
        prompts = generate_template_fragments(parts)

        # Store the prompts globally
        global current_prompts
        current_prompts = prompts

        # Display the results
        display_results(parts, prompts)
    else:
        messagebox.showinfo("No File Selected", "No markdown file was selected.")


def display_results(parts, prompts):
    # Clear existing content
    result_text.delete("1.0", tk.END)

    # Display markdown parts
    result_text.insert(tk.END, f"=== ORIGINAL MARKDOWN SECTIONS ({len(parts)}) ===\n\n")
    for i, part in enumerate(parts, start=1):
        # Handle LangChain Document objects
        if hasattr(part, "page_content") and hasattr(part, "metadata"):
            content = part.page_content
            metadata = part.metadata
            header = metadata.get("Header 1", f"Section {i}")
            result_text.insert(tk.END, f"=== SECTION {i}: {header} ===\n{content}\n\n")
        else:
            # Fallback for non-LangChain document objects
            result_text.insert(tk.END, f"=== SECTION {i} ===\n{part}\n\n")

    # Display template fragments
    result_text.insert(
        tk.END, f"\n=== GENERATED TEMPLATE FRAGMENTS ({len(prompts)}) ===\n\n"
    )
    for i, prompt in enumerate(prompts, start=1):
        result_text.insert(tk.END, f"=== FRAGMENT {i} ===\n{prompt}\n\n")


def select_transcript_file():
    file_path = filedialog.askopenfilename(
        title="Select Transcript File",
        filetypes=[
            ("Text files", "*.txt"),
            ("PDF files", "*.pdf"),
            ("All files", "*.*"),
        ],
    )
    if file_path:
        transcript_label.config(text=f"Transcript File Selected:\n{file_path}")
        global current_transcript_path
        current_transcript_path = file_path

        # Enable the process button if we have both transcript and prompts
        if current_prompts:
            process_button.config(state=tk.NORMAL)
    else:
        messagebox.showinfo("No File Selected", "No transcript file was selected.")


def process_transcript():
    """Process the transcript with the LLM using the generated prompts."""
    if not current_transcript_path or not current_prompts:
        messagebox.showerror(
            "Error",
            "Please select both a markdown template and a transcript file first.",
        )
        return

    # Show processing indicator
    status_label.config(text="Processing... This may take a few minutes.")
    root.update()

    try:
        # Read the transcript file
        with open(current_transcript_path, "r", encoding="utf-8") as f:
            transcript_text = f.read()

        # Combine transcript with template fragments
        complete_prompts = combine_transcript_with_fragments(
            transcript_text, current_prompts
        )

        # Clear the output text
        output_text.delete("1.0", tk.END)

        # Process each prompt with the LLM
        for i, prompt in enumerate(complete_prompts, start=1):
            # output_text.insert(tk.END, f"=== PROCESSING SECTION {i} ===\n")
            root.update()

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
                output_text.insert(tk.END, f"{result['content']}\n\n")
            else:
                output_text.insert(
                    tk.END, f"Error processing section {i}: {result['error']}\n\n"
                )

            # Scroll to see the latest output
            output_text.see(tk.END)
            root.update()

        status_label.config(text="Processing complete!")

        # Save the output to a markdown file
        output_content = output_text.get("1.0", tk.END)
        if save_output_to_markdown(output_content):
            status_label.config(
                text="Processing complete! Output saved to markdown file."
            )
        else:
            status_label.config(text="Processing complete! (Output not saved)")

    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {str(e)}")
        status_label.config(text="Processing failed.")


def save_output_to_markdown(content):
    """Save the processed output to a markdown file."""
    from tkinter import filedialog

    # Suggest default filename
    default_filename = "report-objective-section.md"

    # Prompt user for file location with suggested filename
    file_path = filedialog.asksaveasfilename(
        defaultextension=".md",
        filetypes=[("Markdown files", "*.md"), ("All files", "*.*")],
        initialfile=default_filename,
        title="Save Report Output",
    )

    if not file_path:
        # User cancelled the save dialog
        return False

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save file: {str(e)}")
        return False


def copy_to_clipboard(event=None):
    """Copy the selected text to clipboard."""
    try:
        selected_text = output_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        root.clipboard_clear()
        root.clipboard_append(selected_text)
        status_label.config(text="Text copied to clipboard!")
    except tk.TclError:
        # No selection
        status_label.config(text="Please select text to copy.")


def select_prompt_file():
    """Select a text file containing the prompt for PDF analysis."""
    file_path = filedialog.askopenfilename(
        title="Select Prompt File",
        filetypes=[
            ("Text files", "*.txt"),
            ("Markdown files", "*.md"),
            ("All files", "*.*"),
        ],
    )
    if file_path:
        prompt_label.config(text=f"Prompt File Selected:\n{file_path}")
        global current_prompt_path
        current_prompt_path = file_path

        # Enable the process button if we have both prompt and PDF
        if current_pdf_path:
            process_pdf_button.config(state=tk.NORMAL)
    else:
        messagebox.showinfo("No File Selected", "No prompt file was selected.")


def select_pdf_file():
    """Select a PDF file for analysis."""
    file_path = filedialog.askopenfilename(
        title="Select PDF File",
        filetypes=[
            ("PDF files", "*.pdf"),
            ("All files", "*.*"),
        ],
    )
    if file_path:
        pdf_label.config(text=f"PDF File Selected:\n{file_path}")
        global current_pdf_path
        current_pdf_path = file_path

        # Enable the process button if we have both prompt and PDF
        if current_prompt_path:
            process_pdf_button.config(state=tk.NORMAL)
    else:
        messagebox.showinfo("No File Selected", "No PDF file was selected.")


def process_pdf_with_prompt():
    """Process the PDF file with the provided prompt using Claude's native PDF handling."""
    if not current_prompt_path or not current_pdf_path:
        messagebox.showerror(
            "Error",
            "Please select both a prompt file and a PDF file first.",
        )
        return

    # Show processing indicator
    pdf_status_label.config(text="Processing... This may take a few minutes.")
    root.update()

    try:
        # Read the prompt file
        with open(current_prompt_path, "r", encoding="utf-8") as f:
            prompt_text = f.read()

        # Process the PDF file with the prompt
        result = generate_response_with_pdf(
            prompt_text=prompt_text,
            pdf_file_path=current_pdf_path,
            max_tokens=32000,
            thinking_budget_tokens=16000,
            temperature=0.1,
            timeout=180,  # Longer timeout for PDF processing
            max_retries=2,
        )

        # Clear the output text
        pdf_output_text.delete("1.0", tk.END)

        if result["success"]:
            # Display the thinking process if available
            if result["thinking"]:
                pdf_output_text.insert(
                    tk.END,
                    f"=== CLAUDE'S THINKING PROCESS ===\n{result['thinking']}\n\n",
                )

            # Display the content
            pdf_output_text.insert(tk.END, f"{result['content']}\n\n")

            # Show token usage if available
            if "usage_info" in result:
                usage = result["usage_info"]
                pdf_output_text.insert(
                    tk.END,
                    f"\n=== TOKEN USAGE ===\nInput tokens: {usage.get('input_tokens', 'N/A')}\nOutput tokens: {usage.get('output_tokens', 'N/A')}\n",
                )

            pdf_status_label.config(text="Processing complete!")

            # Save only the content to a markdown file
            if save_pdf_output_to_markdown(result['content']):
                pdf_status_label.config(
                    text="Processing complete! Output saved to markdown file."
                )
            else:
                pdf_status_label.config(text="Processing complete! (Output not saved)")
        else:
            pdf_output_text.insert(tk.END, f"Error processing: {result['error']}\n")
            pdf_status_label.config(text="Processing failed.")

    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {str(e)}")
        pdf_status_label.config(text="Processing failed.")


def save_pdf_output_to_markdown(content):
    """Save the processed PDF output to a markdown file."""
    # Prompt user for file location with suggested filename
    file_path = filedialog.asksaveasfilename(
        defaultextension=".md",
        filetypes=[("Markdown files", "*.md"), ("All files", "*.*")],
        initialfile="test-results-analysis.md",
        title="Save Test Results Analysis",
    )

    if not file_path:
        # User cancelled the save dialog
        return False

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save file: {str(e)}")
        return False


def copy_pdf_output_to_clipboard(event=None):
    """Copy the selected text from PDF output to clipboard."""
    try:
        selected_text = pdf_output_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        root.clipboard_clear()
        root.clipboard_append(selected_text)
        pdf_status_label.config(text="Text copied to clipboard!")
    except tk.TclError:
        # No selection
        pdf_status_label.config(text="Please select text to copy.")


# Setup the main window
root = tk.Tk()
root.title("Forensic Psych Report Drafter")
root.geometry("1000x800")  # Set a larger initial window size

# Global variables
current_prompts = []
current_transcript_path = None
current_prompt_path = None
current_pdf_path = None

# Create a notebook
notebook = ttk.Notebook(root)
notebook.pack(pady=10, expand=True, fill=tk.BOTH)

# Create a tab for phase 1
phase1_tab = ttk.Frame(notebook)
notebook.add(phase1_tab, text="Phase 1 - Prompts")

# Create a tab for phase 2
phase2_tab = ttk.Frame(notebook)
notebook.add(phase2_tab, text="Phase 2 - Objective Section")

# Create a tab for phase 3
phase3_tab = ttk.Frame(notebook)
notebook.add(phase3_tab, text="Phase 3 - Testing")

# Create top frame for buttons and controls in phase 1
phase1_top_frame = ttk.Frame(phase1_tab)
phase1_top_frame.pack(pady=5, fill=tk.X)

# Button to select the markdown file in phase 1
markdown_button = ttk.Button(
    phase1_top_frame, text="Select Markdown File", command=select_markdown_file
)
markdown_button.pack(side=tk.LEFT, padx=10, pady=5)

# Create top frame for buttons and controls in phase 2
phase2_top_frame = ttk.Frame(phase2_tab)
phase2_top_frame.pack(pady=5, fill=tk.X)

# Button to select the transcript file in phase 2
transcript_button = ttk.Button(
    phase2_top_frame, text="Select Transcript File", command=select_transcript_file
)
transcript_button.pack(side=tk.LEFT, padx=10, pady=5)

# Button to process the transcript with the LLM
process_button = ttk.Button(
    phase2_top_frame,
    text="Process with LLM",
    command=process_transcript,
    state=tk.DISABLED,
)
process_button.pack(side=tk.LEFT, padx=10, pady=5)

# Button to copy selected text to clipboard
copy_button = ttk.Button(
    phase2_top_frame, text="Copy Selected Text", command=copy_to_clipboard
)
copy_button.pack(side=tk.LEFT, padx=10, pady=5)

# Label to display transcript file path in phase 2
transcript_label = ttk.Label(phase2_tab, text="No transcript file selected.")
transcript_label.pack(pady=5, anchor=tk.W, padx=10)

# Status label for phase 2
status_label = ttk.Label(phase2_tab, text="")
status_label.pack(pady=5, anchor=tk.W, padx=10)

# Create top frame for buttons and controls in phase 3
phase3_top_frame = ttk.Frame(phase3_tab)
phase3_top_frame.pack(pady=5, fill=tk.X)

# Button to select the prompt file in phase 3
prompt_button = ttk.Button(
    phase3_top_frame, text="Select Prompt File", command=select_prompt_file
)
prompt_button.pack(side=tk.LEFT, padx=10, pady=5)

# Button to select the PDF file in phase 3
pdf_button = ttk.Button(
    phase3_top_frame, text="Select PDF File", command=select_pdf_file
)
pdf_button.pack(side=tk.LEFT, padx=10, pady=5)

# Button to process the PDF with the prompt
process_pdf_button = ttk.Button(
    phase3_top_frame,
    text="Process PDF with LLM",
    command=process_pdf_with_prompt,
    state=tk.DISABLED,
)
process_pdf_button.pack(side=tk.LEFT, padx=10, pady=5)

# Button to copy selected text from PDF output to clipboard
copy_pdf_button = ttk.Button(
    phase3_top_frame, text="Copy Selected Text", command=copy_pdf_output_to_clipboard
)
copy_pdf_button.pack(side=tk.LEFT, padx=10, pady=5)

# Labels to display file paths in phase 3
prompt_label = ttk.Label(phase3_tab, text="No prompt file selected.")
prompt_label.pack(pady=5, anchor=tk.W, padx=10)

pdf_label = ttk.Label(phase3_tab, text="No PDF file selected.")
pdf_label.pack(pady=5, anchor=tk.W, padx=10)

# Status label for phase 3
pdf_status_label = ttk.Label(phase3_tab, text="")
pdf_status_label.pack(pady=5, anchor=tk.W, padx=10)

# Create a frame for the text widget and scrollbar in phase 1
text_frame = ttk.Frame(phase1_tab)
text_frame.pack(pady=5, fill=tk.BOTH, expand=True, padx=10)

# Text widget to display the results of splitting the markdown file
result_text = tk.Text(text_frame, wrap=tk.WORD, height=30, width=80)
result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

# Add scrollbar to the text widget
scrollbar = ttk.Scrollbar(text_frame, command=result_text.yview)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
result_text.config(yscrollcommand=scrollbar.set)

# Configure text widget with a larger font
result_text.configure(font=("TkDefaultFont", 12))

# Create a frame for the output text widget and scrollbar in phase 2
output_frame = ttk.Frame(phase2_tab)
output_frame.pack(pady=5, fill=tk.BOTH, expand=True, padx=10)

# Text widget to display the LLM output
output_text = tk.Text(output_frame, wrap=tk.WORD, height=30, width=80)
output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

# Add scrollbar to the output text widget
output_scrollbar = ttk.Scrollbar(output_frame, command=output_text.yview)
output_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
output_text.config(yscrollcommand=output_scrollbar.set)

# Configure output text widget with a larger font
output_text.configure(font=("TkDefaultFont", 12))

# Create a frame for the PDF output text widget and scrollbar in phase 3
pdf_output_frame = ttk.Frame(phase3_tab)
pdf_output_frame.pack(pady=5, fill=tk.BOTH, expand=True, padx=10)

# Text widget to display the PDF analysis output
pdf_output_text = tk.Text(pdf_output_frame, wrap=tk.WORD, height=30, width=80)
pdf_output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

# Add scrollbar to the PDF output text widget
pdf_output_scrollbar = ttk.Scrollbar(pdf_output_frame, command=pdf_output_text.yview)
pdf_output_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
pdf_output_text.config(yscrollcommand=pdf_output_scrollbar.set)

# Configure PDF output text widget with a larger font
pdf_output_text.configure(font=("TkDefaultFont", 12))

# Bind Ctrl+C to copy function for both output text widgets
output_text.bind("<Control-c>", copy_to_clipboard)
pdf_output_text.bind("<Control-c>", copy_pdf_output_to_clipboard)

root.mainloop()
