# File Location: app.py
# Section: 4.1 Main Application with Auto-Discovery
# Description: Homepage with automatic model discovery and provider status

import asyncio

import streamlit as st

from lib.config import LANGFUSE_CONFIG, discover_available_models
from lib.files import ensure_directories
from lib.llm import get_llm_client
from lib.state import get_session_cost, init_session_state

st.set_page_config(
    page_title="Forensic Report Drafter",
    page_icon="⚖️",
    layout="wide"
)

# Initialize
init_session_state()
ensure_directories()

# Auto-discovery on first load
if "models_discovered" not in st.session_state:
    with st.spinner("🔍 Discovering available models..."):
        st.session_state.available_models = discover_available_models()
        st.session_state.models_discovered = True

st.title("⚖️ Forensic Psych Report Drafter")
st.markdown("*Streamlined LLM-powered document analysis and report generation*")

# Sidebar status with auto-discovered info
with st.sidebar:
    st.header("System Status")

    # Show discovered providers and models
    total_models = 0
    for provider, models in st.session_state.available_models.items():
        st.success(f"✅ {provider.title()}: {len(models)} models")
        total_models += len(models)

        # Show models in expander
        with st.expander(f"View {provider} models"):
            for model in models:
                st.write(f"  • {model.split('/')[-1]}")

    if total_models == 0:
        st.error("❌ No models available")
        st.info("Run setup to configure providers")

    # Langfuse status
    if all(LANGFUSE_CONFIG.values()):
        st.success("✅ Langfuse tracing enabled")
    else:
        st.warning("⚠️ Langfuse disabled")

    st.divider()

    # Session cost tracking
    st.metric("Session Cost", f"${get_session_cost():.4f}")

    # Quick model test
    if st.button("🧪 Test Primary Model"):
        client = get_llm_client()
        if client.primary_model:
            try:
                # Quick test call
                response = asyncio.run(client.generate_simple(
                    client.primary_model,
                    [{"role": "user", "content": "Say 'Test successful'"}]
                ))
                st.success(f"✅ {client.primary_model} working")
            except Exception as e:
                st.error(f"❌ Error: {e}")

# Main content
col1, col2 = st.columns(2)

with col1:
    st.subheader("🔄 Workflow")
    st.markdown("""
    1. **Record Conversion**: Convert PDFs to structured markdown
    2. **Document Summary**: Create document and meta-summaries for analysis preparation
    3. **Report Generation & Refinement**: Generate comprehensive reports from templates and iteratively improve them
    4. **Human Evaluation**: Manual annotation, side-by-side comparison, and feedback collection
    """)

with col2:
    st.subheader("🚀 Quick Start")
    st.markdown("""
    - Upload PDFs in **Record Conversion**
    - Generate summaries in **Summary**
    - Generate and refine reports in **Report Generation**
    - Evaluate outputs with **Human Evaluation**
    """)

# Provider setup help
if total_models == 0:
    st.warning("⚠️ **No LLM providers configured**")
    st.info("""
    **To get started:**
    1. Set environment variables for at least one provider:
       - **Azure OpenAI**: `AZURE_API_KEY`, `AZURE_API_BASE`
       - **Anthropic**: `ANTHROPIC_API_KEY`
       - **Google Gemini**: `GOOGLE_API_KEY`
    2. Optional: Set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` for tracing
    3. Restart the application
    """)

if st.button("Reset Session Cost"):
    from lib.state import reset_session_cost
    reset_session_cost()
    st.rerun() 
