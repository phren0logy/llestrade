# File Location: pages/2_📋_Summary.py
# Section: 4.3 Summary Generation with Dynamic Model Selection
# Description: Simplified implementation with auto-discovered models

import asyncio
from pathlib import Path

import streamlit as st

from lib.files import save_output_with_minimal_metadata, scan_for_markdown
from lib.llm import add_session_cost, get_llm_client
from lib.prompts import get_prompt

st.title("📋 Document Summary Generation")

# Get LLM client with auto-discovered models
client = get_llm_client()
available_models = client.get_available_models()

if not available_models:
    st.error("❌ No LLM models available. Please configure providers first.")
    st.stop()

# Directory selection
source_dir = st.text_input("Source Directory", value="./outputs")

if st.button("Scan for Markdown Files"):
    if Path(source_dir).exists():
        markdown_files = scan_for_markdown(source_dir)
        st.session_state.markdown_files = [str(f) for f in markdown_files]
        st.success(f"Found {len(markdown_files)} markdown files")
    else:
        st.error("Directory does not exist")

# Dynamic model selection with provider grouping
def show_model_selector():
    """Show grouped model selection"""
    models_by_provider = {}
    for model in available_models:
        provider = model.split("/")[0]
        if provider not in models_by_provider:
            models_by_provider[provider] = []
        models_by_provider[provider].append(model)

    # Show available providers in sidebar
    with st.sidebar:
        st.subheader("Available Providers")
        for provider, models in models_by_provider.items():
            st.success(f"✅ {provider.title()}: {len(models)} models")

    # Model selection with better formatting
    selected_model = st.selectbox(
        "Select Model",
        available_models,
        index=0,
        format_func=lambda x: f"{x.split('/')[0].title()}: {x.split('/')[1]}"
    )

    return selected_model

selected_model = show_model_selector()

# File selection for summarization
if "markdown_files" in st.session_state:
    selected_files = st.multiselect(
        "Select Files to Summarize",
        st.session_state.markdown_files
    )

    if st.button("Generate Summaries") and selected_files:
        async def generate_summaries():
            # Get prompt from Langfuse
            prompt = get_prompt("document-summary")

            progress_bar = st.progress(0)
            results = []

            for i, file_path in enumerate(selected_files):
                st.write(f"Processing: {file_path}")

                # Read file content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Generate summary with context tracking
                variables = {
                    "document_content": content,
                    "document_type": "forensic document"
                }

                result = await client.generate_with_context_tracking(
                    selected_model,
                    prompt,
                    variables,
                    document_type="forensic_summary",
                    operation_type="document_summary",
                    source_file=Path(file_path).name
                )

                summary = result["content"]

                # Save summary with minimal metadata
                summary_path = save_output_with_minimal_metadata(
                    summary,
                    f"summary_{Path(file_path).stem}.md",
                    result["minimal_metadata"]
                )

                results.append({
                    "file": file_path,
                    "summary_path": summary_path,
                    "summary": summary[:200] + "...",
                    "trace_id": result["minimal_metadata"].get("langfuse_trace_id")
                })

                # Update cost tracking
                add_session_cost(result["response"])

                # Update progress
                progress_bar.progress((i + 1) / len(selected_files))

            return results

        # Run async summary generation
        results = asyncio.run(generate_summaries())

        st.success(f"Generated {len(results)} summaries")
        for result in results:
            with st.expander(f"Summary: {Path(result['file']).name}"):
                st.write(result['summary'])
                st.caption(f"Saved to: {result['summary_path']}")

                # Show context button if available
                if result.get('trace_id'):
                    from lib.ui_components import show_generation_context_button
                    show_generation_context_button(result['trace_id']) 
