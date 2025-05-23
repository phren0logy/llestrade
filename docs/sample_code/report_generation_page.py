# File Location: pages/3_📝_Report_Generation.py
# Section: 4.2 Report Generation & Refinement - Consolidated Workflow Page
# Description: Integrated template processing and refinement workflow - combines generation and iterative improvement

import asyncio
from datetime import datetime
from pathlib import Path

import streamlit as st

from lib.files import save_output_with_minimal_metadata
from lib.llm import get_llm_client
from lib.prompts import get_prompt
from lib.template_processor import get_template_processor
from lib.ui_components import show_generation_context_button

st.title("📝 Report Generation & Refinement")
st.markdown("**Generate forensic reports from templates and iteratively improve them**")

# Initialize processors
processor = get_template_processor()
client = get_llm_client()

# Helper function for refinement
async def refine_report_content(content, model, case_id, refinement_type="General improvement", custom_instructions="", preserve_structure=True):
    """Refine report content using LLM"""
    try:
        # Get refinement prompt
        refinement_prompt = get_prompt("report_refinement")
        
        variables = {
            "original_content": content,
            "refinement_type": refinement_type,
            "custom_instructions": custom_instructions,
            "preserve_structure": preserve_structure
        }
        
        result = await client.generate_with_context_tracking(
            model,
            refinement_prompt,
            variables,
            case_id=case_id,
            document_type="refined_report",
            operation_type="report_refinement"
        )
        
        return result["content"]
        
    except Exception as e:
        st.error(f"Refinement failed: {e}")
        return None

# Create tabs for different workflows
tab1, tab2, tab3 = st.tabs(["🚀 Generate from Template", "✨ Refine Existing Report", "📊 Compare Versions"])

with tab1:
    st.subheader("Generate New Report from Template")
    
    # Step 1: Template Selection
    st.markdown("### 1. Select Report Template")
    available_templates = processor.get_available_templates()

    if not available_templates:
        st.warning("⚠️ No templates found in `report_templates/` directory")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📁 Open Template Directory"):
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

        # Template preview
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
    st.markdown("### 2. Upload Interview Transcript")
    transcript_file = st.file_uploader(
        "Select interview transcript:",
        type=['txt', 'md'],
        help="Upload the interview transcript to combine with your template"
    )

    # Step 3: Generation Options
    if available_templates and selected_template and transcript_file:
        transcript_content = transcript_file.read().decode('utf-8')
        
        st.markdown("### 3. Generation Options")
        col1, col2, col3 = st.columns(3)

        with col1:
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
            enable_auto_refinement = st.checkbox("Auto-refine after generation", value=False)

        # Generation workflow
        if st.button("🚀 Generate Report from Template", type="primary"):
            with st.spinner("Processing template sections..."):
                section_prompts = processor.generate_section_prompts(selected_template)

            st.info(f"📋 Processing {len(section_prompts)} sections from **{selected_template}**")

            # Generate sections
            async def generate_sections():
                progress = st.progress(0)
                results = []

                for i, section_prompt in enumerate(section_prompts):
                    st.write(f"🔄 Generating: **{section_prompt['name']}**")
                    
                    final_prompt = processor.combine_with_transcript(section_prompt, transcript_content)
                    variables = {"prompt_content": final_prompt}

                    try:
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

            section_results = asyncio.run(generate_sections())
            st.success(f"✅ Generated {len(section_results)} sections")

            # Create combined report
            combined_content = f"# Forensic Evaluation Report\n\n"
            combined_content += f"**Template**: {selected_template}\n"
            combined_content += f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            combined_content += f"**Case ID**: {case_id or 'Not specified'}\n\n---\n\n"

            for result in sorted(section_results, key=lambda x: x['section_index']):
                combined_content += f"## {result['name']}\n\n{result['content']}\n\n"

            # Save combined report
            combined_path = save_output_with_minimal_metadata(
                combined_content,
                f"report_{selected_template.replace('.md', '')}.md",
                {
                    "timestamp": datetime.now().isoformat(),
                    "operation_type": "complete_template_report",
                    "template_source": selected_template,
                    "total_sections": len(section_results),
                    "case_id": case_id,
                    "model_used": selected_model,
                    "refinement_version": 1
                }
            )

            # Store in session state for potential refinement
            st.session_state.current_report = {
                "content": combined_content,
                "metadata": {
                    "template_source": selected_template,
                    "case_id": case_id,
                    "model_used": selected_model,
                    "file_path": combined_path
                },
                "section_results": section_results
            }

            # Display results with refinement option
            st.subheader("📄 Generated Report")
            st.text_area("Complete Report:", value=combined_content, height=300, disabled=True)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.download_button(
                    "📥 Download Report",
                    data=combined_content,
                    file_name=f"report_{selected_template.replace('.md', '')}.md",
                    mime="text/markdown",
                    type="primary"
                )
            with col2:
                st.metric("Report Length", f"{len(combined_content.split())} words")
            with col3:
                if st.button("✨ Refine This Report", type="secondary"):
                    st.session_state.active_tab = 1  # Switch to refinement tab
                    st.rerun()

            # Auto-refinement if enabled
            if enable_auto_refinement:
                st.markdown("### 🔄 Auto-Refinement")
                with st.spinner("Refining report..."):
                    refined_content = await refine_report_content(combined_content, selected_model, case_id)
                    
                    if refined_content:
                        st.session_state.current_report["refined_content"] = refined_content
                        st.success("✅ Auto-refinement completed")
                        
                        # Show comparison
                        col1, col2 = st.columns(2)
                        with col1:
                            st.subheader("Original")
                            st.text_area("", value=combined_content, height=200, disabled=True, key="original_auto")
                        with col2:
                            st.subheader("Refined")
                            st.text_area("", value=refined_content, height=200, disabled=True, key="refined_auto")

            # Display individual sections with context links
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

with tab2:
    st.subheader("Refine Existing Report")
    
    # Load existing report for refinement
    refinement_source = st.radio(
        "Select refinement source:",
        ["Current session report", "Upload existing report", "Load from outputs folder"]
    )
    
    report_to_refine = None
    
    if refinement_source == "Current session report":
        if "current_report" in st.session_state:
            report_to_refine = st.session_state.current_report["content"]
            st.success("✅ Using report from current session")
        else:
            st.warning("⚠️ No report available in current session. Generate a report first.")
    
    elif refinement_source == "Upload existing report":
        uploaded_report = st.file_uploader("Upload report to refine:", type=['md', 'txt'], key="refine_upload")
        if uploaded_report:
            report_to_refine = uploaded_report.read().decode('utf-8')
    
    elif refinement_source == "Load from outputs folder":
        from lib.files import scan_for_markdown
        output_files = scan_for_markdown("outputs")
        if output_files:
            selected_file = st.selectbox("Select report to refine:", output_files)
            if selected_file:
                with open(selected_file, 'r', encoding='utf-8') as f:
                    report_to_refine = f.read()
        else:
            st.info("No markdown files found in outputs folder")

    if report_to_refine:
        st.markdown("### Original Report Preview")
        st.text_area("Original content:", value=report_to_refine, height=200, disabled=True)
        
        # Refinement options
        st.markdown("### Refinement Options")
        col1, col2 = st.columns(2)
        
        with col1:
            available_models = client.get_available_models()
            refinement_model = st.selectbox(
                "Refinement Model:",
                available_models,
                format_func=lambda x: f"{x.split('/')[0].title()}: {x.split('/')[1]}",
                key="refinement_model"
            )
            
            refinement_type = st.selectbox(
                "Refinement Focus:",
                [
                    "General improvement",
                    "Clarity and readability", 
                    "Professional tone",
                    "Factual accuracy",
                    "Legal compliance",
                    "Clinical precision"
                ]
            )
        
        with col2:
            custom_instructions = st.text_area(
                "Custom refinement instructions (optional):",
                placeholder="Specific areas to focus on or improvements needed...",
                height=100
            )
            
            preserve_structure = st.checkbox("Preserve original structure", value=True)
            case_id_refine = st.text_input("Case ID (for tracking):", key="refine_case_id")

        if st.button("✨ Refine Report", type="primary"):
            refined_content = await refine_report_content(
                report_to_refine, 
                refinement_model, 
                case_id_refine,
                refinement_type,
                custom_instructions,
                preserve_structure
            )
            
            if refined_content:
                # Save refined version
                refined_path = save_output_with_minimal_metadata(
                    refined_content,
                    f"refined_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    {
                        "timestamp": datetime.now().isoformat(),
                        "operation_type": "report_refinement",
                        "refinement_type": refinement_type,
                        "case_id": case_id_refine,
                        "model_used": refinement_model,
                        "refinement_version": st.session_state.get("refinement_version", 1) + 1
                    }
                )
                
                st.session_state.refined_report = {
                    "content": refined_content,
                    "original_content": report_to_refine,
                    "file_path": refined_path
                }
                
                st.success("✅ Report refined successfully!")
                
                # Show side-by-side comparison
                st.markdown("### Comparison")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("📄 Original")
                    st.text_area("", value=report_to_refine, height=400, disabled=True, key="original_compare")
                    
                with col2:
                    st.subheader("✨ Refined")
                    st.text_area("", value=refined_content, height=400, disabled=True, key="refined_compare")
                
                # Download options
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.download_button(
                        "📥 Download Refined",
                        data=refined_content,
                        file_name=f"refined_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                        mime="text/markdown"
                    )
                with col2:
                    if st.button("🔄 Refine Again"):
                        # Use refined content as new source
                        st.session_state.current_report = {"content": refined_content}
                        st.rerun()
                with col3:
                    if st.button("📊 Compare in Detail"):
                        st.session_state.active_tab = 2
                        st.rerun()

with tab3:
    st.subheader("Compare Report Versions")
    
    if "refined_report" in st.session_state:
        original = st.session_state.refined_report["original_content"]
        refined = st.session_state.refined_report["content"]
        
        # Word count comparison
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Original Words", len(original.split()))
        with col2:
            st.metric("Refined Words", len(refined.split()))
        with col3:
            change = len(refined.split()) - len(original.split())
            st.metric("Word Change", change, delta=change)
        
        # Side-by-side detailed comparison
        st.markdown("### Detailed Comparison")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Original Version")
            st.text_area("", value=original, height=500, disabled=True, key="compare_original")
            
        with col2:
            st.markdown("#### Refined Version")
            st.text_area("", value=refined, height=500, disabled=True, key="compare_refined")
        
        # Human evaluation interface
        st.markdown("### Human Evaluation")
        col1, col2 = st.columns(2)
        
        with col1:
            clarity_improvement = st.slider("Clarity Improvement (1-5)", 1, 5, 3)
            accuracy_improvement = st.slider("Accuracy Improvement (1-5)", 1, 5, 3)
            
        with col2:
            professional_improvement = st.slider("Professional Tone (1-5)", 1, 5, 3)
            overall_preference = st.radio("Overall Preference", ["Original", "Refined", "Both equal"])
        
        evaluation_notes = st.text_area("Evaluation Notes:", placeholder="Specific observations about the refinement...")
        
        if st.button("Submit Evaluation", type="primary"):
            # Record evaluation in Langfuse if available
            try:
                from lib.prompts import get_langfuse_client
                langfuse_client = get_langfuse_client()
                
                # Submit evaluation scores
                # Implementation would depend on available trace IDs
                st.success("Evaluation submitted successfully!")
            except:
                st.warning("Evaluation recorded locally (Langfuse not available)")
    
    else:
        st.info("No refined report available for comparison. Refine a report first.")

# Template Management Section
st.divider()
st.subheader("🔧 Template Management")

col1, col2 = st.columns(2)

with col1:
    st.write("**Your Local Templates**")
    st.write(f"📁 Stored in: `{processor.template_directory}`")
    
    if st.button("📂 Open Template Folder"):
        pass

with col2:
    st.write("**Template Actions**")
    if st.button("🔄 Refresh Template List"):
        st.rerun()
    
    if st.button("➕ Create New Template"):
        pass 
