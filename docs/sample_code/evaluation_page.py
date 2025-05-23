# File Location: pages/5_🔬_Evaluation.py
# Section: 4.4 Human Evaluation with Native Langfuse Integration
# Description: Human-centric evaluation with native Langfuse integration

import asyncio
from datetime import datetime
from pathlib import Path

import streamlit as st

from lib.config import get_all_available_models as get_available_models
from lib.files import read_metadata_from_file, scan_for_markdown
from lib.llm import get_llm_client
from lib.prompts import get_langfuse_client
from lib.ui_components import (
    create_human_evaluation_interface,
    show_generation_context_button,
)

st.title("🔬 Human Evaluation & Testing")

tab1, tab2, tab3, tab4 = st.tabs(["📋 Manual Annotation", "⚖️ Side-by-Side Comparison", "📊 User Feedback", "🤖 Automated Evaluation"])

with tab1:
    st.subheader("Manual Annotation Queue")

    # Document selection for annotation
    annotation_dir = st.text_input("Generated Documents Directory", value="./outputs")

    if st.button("Load Annotation Queue"):
        if Path(annotation_dir).exists():
            markdown_files = scan_for_markdown(annotation_dir)
            # Filter files that need annotation
            unannotated_files = []
            for file_path in markdown_files:
                metadata = read_metadata_from_file(str(file_path))
                if not metadata.get("human_annotation_score"):
                    unannotated_files.append(str(file_path))

            st.session_state.annotation_queue = unannotated_files
            st.success(f"Loaded {len(unannotated_files)} documents needing annotation")

    if "annotation_queue" in st.session_state and st.session_state.annotation_queue:
        # Current document for annotation
        current_file = st.session_state.annotation_queue[0]
        st.info(f"Annotating: {Path(current_file).name}")

        # Read document content
        with open(current_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract metadata for context
        metadata = read_metadata_from_file(current_file)

        # Display document content
        st.text_area("Generated Content", value=content, height=300, disabled=True)

        # Show generation context button
        if metadata.get("langfuse_trace_id"):
            show_generation_context_button(metadata["langfuse_trace_id"], "🔍 View Generation Details")

        # Annotation interface
        col1, col2 = st.columns(2)

        with col1:
            accuracy_score = st.slider("Accuracy (1-5)", 1, 5, 3, key="accuracy")
            completeness_score = st.slider("Completeness (1-5)", 1, 5, 3, key="completeness")
            clarity_score = st.slider("Clarity (1-5)", 1, 5, 3, key="clarity")

        with col2:
            forensic_relevance = st.slider("Forensic Relevance (1-5)", 1, 5, 3, key="forensic")
            factual_accuracy = st.slider("Factual Accuracy (1-5)", 1, 5, 3, key="factual")
            ethical_compliance = st.slider("Ethical Compliance (1-5)", 1, 5, 3, key="ethical")

        annotation_notes = st.text_area("Annotation Notes", placeholder="Specific observations, corrections, or recommendations...")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("✅ Submit Annotation", type="primary"):
                # Calculate overall score
                overall_score = (accuracy_score + completeness_score + clarity_score +
                               forensic_relevance + factual_accuracy + ethical_compliance) / 6

                # Send annotation to Langfuse
                try:
                    langfuse_client = get_langfuse_client()
                    langfuse_client.score(
                        trace_id=metadata.get("langfuse_trace_id"),
                        name="human_annotation",
                        value=overall_score,
                        metadata={
                            "accuracy": accuracy_score,
                            "completeness": completeness_score,
                            "clarity": clarity_score,
                            "forensic_relevance": forensic_relevance,
                            "factual_accuracy": factual_accuracy,
                            "ethical_compliance": ethical_compliance,
                            "notes": annotation_notes,
                            "annotator": st.session_state.get("annotator_name", "unknown"),
                            "annotation_timestamp": datetime.now().isoformat()
                        }
                    )

                    # Remove from queue and advance
                    st.session_state.annotation_queue.pop(0)
                    st.success("Annotation submitted successfully!")
                    st.rerun()

                except Exception as e:
                    st.error(f"Failed to submit annotation: {e}")

        with col2:
            if st.button("⏭️ Skip Document"):
                st.session_state.annotation_queue.append(st.session_state.annotation_queue.pop(0))
                st.rerun()

        with col3:
            st.metric("Remaining", len(st.session_state.annotation_queue))

with tab2:
    st.subheader("Side-by-Side Model Comparison")

    # Model selection for comparison
    available_models = get_available_models()
    if len(available_models) >= 2:
        col1, col2 = st.columns(2)
        with col1:
            model_a = st.selectbox("Model A", available_models, key="model_a")
        with col2:
            model_b = st.selectbox("Model B", available_models, index=1, key="model_b")

        # Document selection
        test_document = st.text_area("Test Document Content", height=150)
        prompt_type = st.selectbox("Prompt Type", ["document-summary", "report-generation", "analysis"])

        if st.button("Generate Comparison") and test_document:
            async def run_comparison():
                client = get_llm_client()
                prompt = get_langfuse_client().get_prompt(prompt_type)

                variables = {"document_content": test_document}

                # Generate with both models
                result_a = await client.generate_with_context_tracking(
                    model_a, prompt, variables,
                    operation_type="comparison_a",
                    document_type="test_comparison"
                )

                result_b = await client.generate_with_context_tracking(
                    model_b, prompt, variables,
                    operation_type="comparison_b",
                    document_type="test_comparison"
                )

                return result_a, result_b

            with st.spinner("Generating responses..."):
                result_a, result_b = asyncio.run(run_comparison())

            # Display side-by-side comparison
            col1, col2 = st.columns(2)

            with col1:
                st.subheader(f"📊 {model_a}")
                st.text_area("Response A", value=result_a["content"], height=300, disabled=True)
                if result_a["minimal_metadata"].get("langfuse_trace_id"):
                    show_generation_context_button(result_a["minimal_metadata"]["langfuse_trace_id"])

            with col2:
                st.subheader(f"📊 {model_b}")
                st.text_area("Response B", value=result_b["content"], height=300, disabled=True)
                if result_b["minimal_metadata"].get("langfuse_trace_id"):
                    show_generation_context_button(result_b["minimal_metadata"]["langfuse_trace_id"])

            # Comparison voting
            st.subheader("Human Preference")
            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button(f"👍 Prefer {model_a}", type="primary"):
                    # Record preference in Langfuse
                    langfuse_client = get_langfuse_client()
                    langfuse_client.score(
                        trace_id=result_a["minimal_metadata"]["langfuse_trace_id"],
                        name="human_preference",
                        value=1.0,
                        metadata={"comparison_winner": model_a, "comparison_loser": model_b}
                    )
                    langfuse_client.score(
                        trace_id=result_b["minimal_metadata"]["langfuse_trace_id"],
                        name="human_preference",
                        value=0.0,
                        metadata={"comparison_winner": model_a, "comparison_loser": model_b}
                    )
                    st.success(f"{model_a} preference recorded!")

            with col2:
                if st.button(f"👍 Prefer {model_b}", type="primary"):
                    # Record preference in Langfuse
                    langfuse_client = get_langfuse_client()
                    langfuse_client.score(
                        trace_id=result_b["minimal_metadata"]["langfuse_trace_id"],
                        name="human_preference",
                        value=1.0,
                        metadata={"comparison_winner": model_b, "comparison_loser": model_a}
                    )
                    langfuse_client.score(
                        trace_id=result_a["minimal_metadata"]["langfuse_trace_id"],
                        name="human_preference",
                        value=0.0,
                        metadata={"comparison_winner": model_b, "comparison_loser": model_a}
                    )
                    st.success(f"{model_b} preference recorded!")

            with col3:
                if st.button("🤝 Tie/Equal"):
                    # Record tie in Langfuse
                    langfuse_client = get_langfuse_client()
                    for result, model in [(result_a, model_a), (result_b, model_b)]:
                        langfuse_client.score(
                            trace_id=result["minimal_metadata"]["langfuse_trace_id"],
                            name="human_preference",
                            value=0.5,
                            metadata={"comparison_result": "tie", "compared_models": [model_a, model_b]}
                        )
                    st.success("Tie recorded!")

with tab3:
    st.subheader("User Feedback Collection")

    # Load recent generations for feedback
    feedback_dir = st.text_input("Generated Documents Directory", value="./outputs", key="feedback_dir")

    if st.button("Load Recent Generations"):
        if Path(feedback_dir).exists():
            markdown_files = list(Path(feedback_dir).glob("*.md"))
            # Sort by modification time, most recent first
            recent_files = sorted(markdown_files, key=lambda x: x.stat().st_mtime, reverse=True)[:10]
            st.session_state.feedback_files = [str(f) for f in recent_files]
            st.success(f"Loaded {len(recent_files)} recent documents")

    if "feedback_files" in st.session_state:
        selected_file = st.selectbox("Select Document for Feedback", st.session_state.feedback_files)

        if selected_file:
            # Read and display document
            with open(selected_file, 'r', encoding='utf-8') as f:
                content = f.read()

            metadata = read_metadata_from_file(selected_file)

            st.text_area("Document Content", value=content, height=200, disabled=True)

            # Feedback interface
            col1, col2 = st.columns(2)

            with col1:
                overall_rating = st.slider("Overall Quality (1-5)", 1, 5, 3)
                usefulness = st.slider("Usefulness for Forensic Work (1-5)", 1, 5, 3)

            with col2:
                trust_score = st.slider("Trust in Output (1-5)", 1, 5, 3)
                would_use = st.radio("Would you use this in practice?", ["Yes", "No", "With modifications"])

            feedback_text = st.text_area("Detailed Feedback", placeholder="What worked well? What could be improved?")

            if st.button("Submit Feedback", type="primary"):
                try:
                    langfuse_client = get_langfuse_client()
                    langfuse_client.score(
                        trace_id=metadata.get("langfuse_trace_id"),
                        name="user_feedback",
                        value=overall_rating,
                        metadata={
                            "overall_rating": overall_rating,
                            "usefulness": usefulness,
                            "trust_score": trust_score,
                            "would_use": would_use,
                            "feedback_text": feedback_text,
                            "feedback_timestamp": datetime.now().isoformat()
                        }
                    )
                    st.success("Feedback submitted successfully!")
                except Exception as e:
                    st.error(f"Failed to submit feedback: {e}")

with tab4:
    st.subheader("Automated Evaluation (Optional)")
    st.info("Automated evaluation is available but secondary to human evaluation for forensic applications.")

    # Simplified automated evaluation options
    eval_type = st.selectbox("Evaluation Type", ["Basic Quality Checks", "Factual Consistency", "Format Validation"])

    if st.button("Run Automated Evaluation"):
        st.info("This feature can be implemented as needed, but human evaluation takes priority.") 
