# File Location: lib/ui_components.py
# Section: 3.6 UI Components for Human Evaluation and Context Discovery
# Description: Reusable Streamlit components for human evaluation and transparent generation context

from datetime import datetime
from typing import Any, Dict, Optional

import streamlit as st

from .config import LANGFUSE_CONFIG
from .files import get_rich_context_from_langfuse


def show_generation_context_button(trace_id: str, label: str = "🔍 View Generation Context"):
    """Show button that reveals rich generation context on-demand"""
    if not trace_id:
        return

    if st.button(label, key=f"context_{trace_id}"):
        with st.spinner("Fetching generation details..."):
            context = get_rich_context_from_langfuse(trace_id)

            if "error" in context:
                st.error(context["error"])
                return

        # Rich metrics display
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Cost", f"${context.get('cost', 0):.4f}")
        with col2:
            st.metric("Tokens", context.get('tokens', {}).get('total', 0))
        with col3:
            st.metric("Duration", f"{context.get('duration', 0)}ms")

        # Progressive disclosure
        with st.expander("🔧 Prompt Details"):
            prompt_input = context.get('full_prompt', {})
            if isinstance(prompt_input, list):  # Chat format
                for msg in prompt_input:
                    st.write(f"**{msg.get('role', 'unknown').title()}:**")
                    st.code(msg.get('content', ''))
            else:
                st.code(str(prompt_input))

        with st.expander("🏷️ Tags & Metadata"):
            tags = context.get('tags', [])
            if tags:
                st.write("**Tags:**")
                for tag in tags:
                    st.badge(tag)

            metadata = context.get('metadata', {})
            if metadata:
                st.write("**Metadata:**")
                st.json(metadata)

        # Direct Langfuse link
        langfuse_host = LANGFUSE_CONFIG.get("host", "https://cloud.langfuse.com")
        st.link_button("🌐 Open in Langfuse", f"{langfuse_host}/trace/{trace_id}")

def show_document_metadata_preview(metadata: Dict[str, Any]):
    """Show compact metadata preview for document listings"""
    if not metadata:
        st.caption("No metadata available")
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        if "model_key" in metadata:
            st.write(f"**Model:** {metadata['model_key']}")

    with col2:
        if "prompt_name" in metadata:
            st.write(f"**Prompt:** {metadata['prompt_name']}")

    with col3:
        if "timestamp" in metadata:
            date_str = metadata['timestamp'][:10] if metadata['timestamp'] else "Unknown"
            st.write(f"**Generated:** {date_str}")

def show_case_dashboard(case_id: str):
    """Show case-centric dashboard with all related generations"""
    try:
        from langfuse import Langfuse
        langfuse = Langfuse()

        # Fetch all traces for this case
        traces = langfuse.get_traces(tags=[f"case:{case_id}"])

        if not traces:
            st.info(f"No generations found for case {case_id}")
            return

        # Case summary metrics
        total_cost = sum(getattr(t, 'cost', 0) for t in traces)
        total_docs = len(set(t.metadata.get("source_file", "") for t in traces if hasattr(t, 'metadata')))

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Cost", f"${total_cost:.2f}")
        with col2:
            st.metric("Documents Processed", total_docs)
        with col3:
            st.metric("AI Generations", len(traces))

        # Document list with context buttons
        st.subheader("Generated Documents")
        for trace in traces[-10:]:  # Show last 10
            with st.expander(f"📄 {trace.metadata.get('source_file', 'Unknown')} - {trace.metadata.get('operation_type', 'generation')}"):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"**Model:** {trace.model}")
                    st.write(f"**Cost:** ${getattr(trace, 'cost', 0):.4f}")
                with col2:
                    show_generation_context_button(trace.id, "View Details")

    except Exception as e:
        st.error(f"Error loading case dashboard: {e}")

def show_model_comparison_widget(document_traces: list):
    """Widget to compare how different models handled the same document"""
    if len(document_traces) < 2:
        return

    st.subheader("🔄 Model Comparison")

    # Group by model
    by_model = {}
    for trace in document_traces:
        model = getattr(trace, 'model', 'unknown')
        if model not in by_model:
            by_model[model] = []
        by_model[model].append(trace)

    # Show comparison
    for model, traces in by_model.items():
        avg_cost = sum(getattr(t, 'cost', 0) for t in traces) / len(traces)
        st.metric(f"{model} Average Cost", f"${avg_cost:.4f}")

def create_human_evaluation_interface(trace_id: str, content: str, document_type: str = "general"):
    """Create forensic-specific human evaluation interface"""
    st.subheader("🔍 Human Evaluation")

    # Display content for evaluation
    st.text_area("Generated Content", value=content, height=250, disabled=True)

    # Forensic-specific evaluation criteria
    col1, col2 = st.columns(2)

    with col1:
        accuracy = st.slider("Factual Accuracy (1-5)", 1, 5, 3, key=f"accuracy_{trace_id}")
        completeness = st.slider("Completeness (1-5)", 1, 5, 3, key=f"completeness_{trace_id}")
        clarity = st.slider("Clarity (1-5)", 1, 5, 3, key=f"clarity_{trace_id}")

    with col2:
        forensic_relevance = st.slider("Forensic Relevance (1-5)", 1, 5, 3, key=f"forensic_{trace_id}")
        ethical_compliance = st.slider("Ethical Standards (1-5)", 1, 5, 3, key=f"ethical_{trace_id}")
        usability = st.slider("Professional Usability (1-5)", 1, 5, 3, key=f"usability_{trace_id}")

    evaluation_notes = st.text_area(
        "Evaluation Notes",
        placeholder="Specific observations, areas for improvement, or concerns...",
        key=f"notes_{trace_id}"
    )

    if st.button("Submit Evaluation", type="primary", key=f"submit_{trace_id}"):
        # Calculate overall score
        overall_score = (accuracy + completeness + clarity + forensic_relevance +
                        ethical_compliance + usability) / 6

        try:
            from lib.prompts import get_langfuse_client
            langfuse_client = get_langfuse_client()
            langfuse_client.score(
                trace_id=trace_id,
                name="human_evaluation",
                value=overall_score,
                metadata={
                    "document_type": document_type,
                    "accuracy": accuracy,
                    "completeness": completeness,
                    "clarity": clarity,
                    "forensic_relevance": forensic_relevance,
                    "ethical_compliance": ethical_compliance,
                    "usability": usability,
                    "evaluation_notes": evaluation_notes,
                    "evaluator": st.session_state.get("evaluator_name", "unknown"),
                    "evaluation_timestamp": datetime.now().isoformat()
                }
            )
            st.success("Evaluation submitted successfully!")
            return True
        except Exception as e:
            st.error(f"Failed to submit evaluation: {e}")
            return False

def show_annotation_queue_dashboard():
    """Dashboard for managing annotation workflow"""
    st.subheader("📋 Annotation Queue Status")

    try:
        from lib.prompts import get_langfuse_client
        langfuse = get_langfuse_client()

        # Get traces needing annotation
        all_traces = langfuse.get_traces(tags=["needs_annotation"])

        if not all_traces:
            st.info("No documents currently in annotation queue")
            return

        # Show queue statistics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Pending Annotations", len(all_traces))
        with col2:
            completed_today = len([t for t in all_traces if t.metadata.get("annotation_date") == datetime.now().strftime("%Y-%m-%d")])
            st.metric("Completed Today", completed_today)
        with col3:
            avg_score = sum(t.score for t in all_traces if hasattr(t, 'score')) / max(len([t for t in all_traces if hasattr(t, 'score')]), 1)
            st.metric("Average Score", f"{avg_score:.2f}")

        # List pending annotations
        st.subheader("Pending Annotations")
        for trace in all_traces[:5]:  # Show first 5
            with st.expander(f"📄 {trace.metadata.get('source_file', 'Unknown')} - {trace.metadata.get('operation_type', 'generation')}"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**Generated:** {trace.metadata.get('timestamp', 'Unknown')}")
                    st.write(f"**Model:** {trace.metadata.get('model_key', 'Unknown')}")
                with col2:
                    if st.button("Annotate", key=f"annotate_{trace.id}"):
                        st.session_state.current_annotation_trace = trace.id
                        st.rerun()

    except Exception as e:
        st.error(f"Error loading annotation queue: {e}")

def show_evaluation_analytics():
    """Show analytics from human evaluations"""
    st.subheader("📊 Evaluation Analytics")

    try:
        from lib.prompts import get_langfuse_client
        langfuse = get_langfuse_client()

        # Get all human evaluations
        evaluations = langfuse.get_traces(tags=["human_evaluated"])

        if not evaluations:
            st.info("No human evaluations available yet")
            return

        # Calculate metrics
        scores = [e.score for e in evaluations if hasattr(e, 'score')]

        if scores:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Evaluations", len(scores))
            with col2:
                st.metric("Average Score", f"{sum(scores)/len(scores):.2f}")
            with col3:
                high_quality = len([s for s in scores if s >= 4.0])
                st.metric("High Quality (≥4.0)", f"{high_quality}/{len(scores)}")

        # Show evaluation trends
        if len(evaluations) > 1:
            st.line_chart([e.score for e in evaluations[-10:] if hasattr(e, 'score')])

    except Exception as e:
        st.error(f"Error loading evaluation analytics: {e}") 
