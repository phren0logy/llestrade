from langchain_text_splitters import MarkdownHeaderTextSplitter
from src.core.prompt_manager import PromptManager

# Initialize prompt manager
prompt_manager = PromptManager()


def ingest_and_split_markdown(file_path: str) -> list:
    """Reads a markdown file and splits its content into parts using langchain's MarkdownHeaderTextSplitter."""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    # Using MarkdownHeaderTextSplitter to split the text based on markdown headers
    headers_to_split_on = [
        ("#", "Header 1"),
    ]
    text_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    texts = text_splitter.split_text(text)
    
    # The order is preserved by default in the split_text result
    # We return the result directly to maintain the original order
    return texts


def generate_template_fragments(markdown_parts: list) -> list:
    """
    Converts markdown parts into formatted LLM prompts.

    Args:
        markdown_parts: List of markdown sections from ingest_and_split_markdown

    Returns:
        List of dictionaries with "name" and "content" keys for each template fragment
    """
    templates = []

    for i, part in enumerate(markdown_parts, start=1):
        # Initialize an empty fragment
        fragment = ""
        template_name = f"Section {i}"

        # Handle LangChain Document objects
        if hasattr(part, "page_content") and hasattr(part, "metadata"):
            content = part.page_content
            metadata = part.metadata

            # Get the section name from Header 1 if available
            header1_text = metadata.get("Header 1", "")
            if header1_text:
                template_name = header1_text
                # Insert the header at the very beginning of the prompt
                fragment = f"<template>\n # {header1_text}\n"

            # Add metadata headers except for Header 1 (which is already at the top)
            if metadata:
                for header_level, header_text in metadata.items():
                    # Skip Header 1 since we already added it at the top
                    if header_level != "Header 1":
                        fragment += f"\n{header_level}: {header_text}\n"

            # Add the content
            fragment += f"\n{content}</template>\n"
        else:
            # Fallback for non-LangChain document objects
            content = str(part)
            fragment += f"\n<template>{content}\n</template>\n"

        # Add instructions for the LLM
        instructions = prompt_manager.get_template('report_generation_instructions')
        fragment += f"\n{instructions}"

        # Add this template to the list
        templates.append({
            "name": template_name,
            "content": fragment
        })

    return templates


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python ingest_markdown.py <markdown_file>")
        sys.exit(1)
    parts = ingest_and_split_markdown(sys.argv[1])
    for i, part in enumerate(parts):
        print(f"--- part {i+1} ---\n{part}\n")

    # Generate and print template fragments
    print("\n=== GENERATED TEMPLATE FRAGMENTS ===\n")
    fragments = generate_template_fragments(parts)
    for i, fragment in enumerate(fragments, start=1):
        print(f"=== FRAGMENT {i} ===\nName: {fragment['name']}\nContent:\n{fragment['content']}\n")
