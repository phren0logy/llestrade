# File Location: lib/prompts.py
# Section: 3.3 Streamlined Prompt Management
# Description: Using Langfuse native patterns with simple fallbacks

import os

import streamlit as st
from langfuse import Langfuse

from .config import LANGFUSE_CONFIG


@st.cache_resource
def get_langfuse_client():
    """Get cached Langfuse client"""
    return Langfuse(
        public_key=LANGFUSE_CONFIG["public_key"],
        secret_key=LANGFUSE_CONFIG["secret_key"],
        host=LANGFUSE_CONFIG["host"]
    )

@st.cache_data(ttl=300)  # Cache prompts for 5 minutes
def get_prompt(name: str, label: str = "production"):
    """Get prompt with caching and simple fallback"""
    try:
        client = get_langfuse_client()
        return client.get_prompt(name, label=label)
    except Exception as e:
        st.warning(f"Could not fetch prompt '{name}' from Langfuse: {e}")
        # Simple fallback to local file
        fallback_path = f"templates/{name}.md"
        if os.path.exists(fallback_path):
            with open(fallback_path) as f:
                content = f.read()
                # Simple fallback object that mimics Langfuse prompt
                class FallbackPrompt:
                    def __init__(self, content):
                        self.prompt = content
                        self.name = name
                        self.type = "text"
                    def compile(self, **kwargs):
                        result = self.prompt
                        for key, value in kwargs.items():
                            result = result.replace(f"{{{{{key}}}}}", str(value))
                        return result
                return FallbackPrompt(content)
        raise Exception(f"No prompt found for {name} (neither in Langfuse nor local fallback)") 
