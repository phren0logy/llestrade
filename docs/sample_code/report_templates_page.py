# File Location: pages/3_📝_Report_Templates.py
# Section: 4.2 Report Templates - Core Workflow Page
# Description: Core template processing workflow - primary user interface for template-driven workflow

import asyncio
from datetime import datetime
from pathlib import Path

import streamlit as st

from lib.files import save_output_with_minimal_metadata
from lib.llm import get_llm_client
from lib.template_processor import get_template_processor
from lib.ui_components import show_generation_context_button

st.title("📝 Report Templates")
st.markdown("**Generate forensic reports from your local markdown templates**")

# Initialize processors
processor = get_template_processor()
client = get_llm_client()

# Step 1: Template Selection
st.subheader("1. Select Report Template")

available_templates = processor.get_available_templates()

if not available_templates:
    st.warning("⚠️ No templates found in `report_templates/` directory")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📁 Open Template Directory"):
            # Platform-specific directory opening code
            pass
    with col2:
        if st.button("➕ Create Example Templates"):
            processor._create_starter_templates()
            st.rerun()
else:
    selected_template = st.selectbox(
        "Choose your report template:",
        available_templates,
        help="Select from your locally stored markdown templates"
    )

    # Template preview and section breakdown
    if selected_template:
        with st.expander("🔍 Preview Template Structure"):
            sections = processor.process_template_to_sections(selected_template)

            col1, col2 = st.columns([1, 2])
            with col1:
                st.metric("Template Sections", len(sections))
                for section in sections:
                    st.write(f"• {section['name']}")

            with col2:
                template_content = processor.load_template(selected_template)
                st.text_area("Template Content", template_content, height=200, disabled=True)

# Step 2: Transcript Upload
st.subheader("2. Upload Interview Transcript")

transcript_file = st.file_uploader(
    "Select interview transcript:",
    type=['txt', 'md'],
    help="Upload the interview transcript to combine with your template"
)

# Step 3: Generation Options and Processing
if available_templates and selected_template and transcript_file:
    transcript_content = transcript_file.read().decode('utf-8')

    st.subheader("3. Generation Options")

    col1, col2, col3 = st.columns(3)

    with col1:
        # Model selection with provider grouping
        available_models = client.get_available_models()
        selected_model = st.selectbox(
            "Model:",
            available_models,
            format_func=lambda x: f"{x.split('/')[0].title()}: {x.split('/')[1]}"
        )

    with col2:
        case_id = st.text_input("Case ID (optional):")

    with col3:
        save_individual = st.checkbox("Save individual sections", value=True)
        generate_combined = st.checkbox("Create combined report", value=True)

    # Main generation workflow
    if st.button("🚀 Generate Report from Template", type="primary"):

        # Process template into section prompts
        with st.spinner("Processing template sections..."):
            section_prompts = processor.generate_section_prompts(selected_template)

        st.info(f"📋 Processing {len(section_prompts)} sections from **{selected_template}**")

        # Generate each section with progress tracking
        async def generate_sections():
            progress = st.progress(0)
            results = []

            for i, section_prompt in enumerate(section_prompts):
                # Show current section being processed
                st.write(f"🔄 Generating: **{section_prompt['name']}**")

                # Combine section prompt with transcript
                final_prompt = processor.combine_with_transcript(section_prompt, transcript_content)

                # Generate with full context tracking
                variables = {"prompt_content": final_prompt}

                # Get Langfuse prompt or use fallback
                try:
                    from lib.prompts import get_prompt
                    langfuse_prompt = get_prompt("direct_generation")
                except:
                    class SimplePrompt:
                        def compile(self, **kwargs):
                            return kwargs.get("prompt_content", "")
                    langfuse_prompt = SimplePrompt()

                result = await client.generate_with_context_tracking(
                    selected_model,
                    langfuse_prompt,
                    variables,
                    case_id=case_id,
                    document_type="report_section",
                    operation_type="template_section_generation",
                    source_file=f"{selected_template}_{section_prompt['name']}"
                )

                # Save individual section if requested
                if save_individual:
                    section_filename = f"section_{section_prompt['name'].replace(' ', '_').lower()}.md"
                    save_output_with_minimal_metadata(
                        result["content"],
                        section_filename,
                        {
                            **result["minimal_metadata"],
                            "template_source": selected_template,
                            "section_name": section_prompt['name']
                        }
                    )

                results.append({
                    "name": section_prompt['name'],
                    "content": result["content"],
                    "trace_id": result["minimal_metadata"].get("langfuse_trace_id"),
                    "section_index": section_prompt['section_index']
                })

                progress.progress((i + 1) / len(section_prompts))

            return results

        # Execute generation
        section_results = asyncio.run(generate_sections())

        st.success(f"✅ Generated {len(section_results)} sections from **{selected_template}**")

        # Display results with context links
        st.subheader("📄 Generated Report Sections")

        for result in section_results:
            with st.expander(f"📝 {result['name']}"):
                st.text_area(
                    "Content:",
                    value=result['content'],
                    height=200,
                    disabled=True,
                    key=f"content_{result['section_index']}"
                )

                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        "📥 Download Section",
                        data=result['content'],
                        file_name=f"{result['name'].replace(' ', '_')}.md",
                        mime="text/markdown",
                        key=f"download_{result['section_index']}"
                    )
                with col2:
                    if result['trace_id']:
                        show_generation_context_button(result['trace_id'])

        # Generate combined report
        if generate_combined:
            st.subheader("📋 Complete Report")

            combined_content = f"# Forensic Evaluation Report\n\n"
            combined_content += f"**Template**: {selected_template}\n"
            combined_content += f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            combined_content += f"**Case ID**: {case_id or 'Not specified'}\n\n---\n\n"

            # Add sections in order
            for result in sorted(section_results, key=lambda x: x['section_index']):
                combined_content += f"## {result['name']}\n\n{result['content']}\n\n"

            # Save with enhanced metadata
            combined_path = save_output_with_minimal_metadata(
                combined_content,
                f"report_{selected_template.replace('.md', '')}.md",
                {
                    "timestamp": datetime.now().isoformat(),
                    "operation_type": "complete_template_report",
                    "template_source": selected_template,
                    "total_sections": len(section_results),
                    "case_id": case_id,
                    "model_used": selected_model
                }
            )

            st.text_area("Complete Report:", value=combined_content, height=300, disabled=True)

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "📥 Download Complete Report",
                    data=combined_content,
                    file_name=f"report_{selected_template.replace('.md', '')}.md",
                    mime="text/markdown",
                    type="primary"
                )
            with col2:
                st.metric("Report Length", f"{len(combined_content.split())} words")

# Template Management Section
st.divider()
st.subheader("🔧 Template Management")

col1, col2 = st.columns(2)

with col1:
    st.write("**Your Local Templates**")
    st.write(f"📁 Stored in: `{processor.template_directory}`")

    if st.button("📂 Open Template Folder"):
        # Platform-specific code to open folder
        pass

with col2:
    st.write("**Template Actions**")
    if st.button("🔄 Refresh Template List"):
        st.rerun()

    if st.button("➕ Create New Template"):
        # Template creation interface
        pass 
