# File Location: lib/state.py
# Section: 3.4 Simple State Management
# Description: Following Streamlit 2025 patterns

import streamlit as st


def init_session_state():
    """Initialize session state with defaults"""
    defaults = {
        "total_cost": 0.0,
        "selected_model": None,
        "conversation_history": []
    }

    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

def get_session_cost() -> float:
    """Get current session cost"""
    return st.session_state.get("total_cost", 0.0)

def reset_session_cost():
    """Reset session cost tracking"""
    st.session_state.total_cost = 0.0 
