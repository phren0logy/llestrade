# Sample Code Implementation

This directory contains the complete sample implementations extracted from the main DESIGN_DOCUMENT.md for better organization and maintainability.

## 📁 Code Organization

### **Core Library Modules (`lib/` directory)**

| File                    | Purpose                          | Key Features                                                 |
| ----------------------- | -------------------------------- | ------------------------------------------------------------ |
| `config.py`             | Multi-provider LLM configuration | Auto-discovery, fallback strategies, environment-based setup |
| `llm.py`                | LLM client with observability    | Multi-provider support, automatic Langfuse tracing, chunking |
| `prompts.py`            | Prompt management                | Langfuse integration, local fallbacks                        |
| `state.py`              | Session state management         | Streamlit state helpers, cost tracking                       |
| `files.py`              | File operations                  | YAML frontmatter, metadata linking                           |
| `ui_components.py`      | Reusable UI components           | Human evaluation, context discovery, analytics               |
| `chunking.py`           | Document chunking                | Header-based splitting, model-aware sizing                   |
| `template_processor.py` | Template processing engine       | Core workflow - local template to LLM prompts                |

### **Streamlit Application Files**

| File                        | Purpose                    | Description                                                        |
| --------------------------- | -------------------------- | ------------------------------------------------------------------ |
| `app.py`                    | Main application           | Homepage with auto-discovery, provider status                      |
| `report_generation_page.py` | Consolidated workflow page | Template-driven report generation and refinement (primary feature) |
| `summary_page.py`           | Document summarization     | Multi-file summary generation                                      |
| `evaluation_page.py`        | Human evaluation           | Annotation, comparison, feedback collection                        |

## 🎯 Key Architecture Decisions

### **Template-Driven Workflow**

- **Local Control**: Users maintain markdown templates in their own directories
- **Section-Based Processing**: Each Header 1 section becomes a focused LLM prompt
- **Professional Standards**: Templates encode established forensic reporting practices

### **Multi-Provider Simplicity**

- **Auto-Discovery**: Automatically detect available models from Azure, Anthropic, Gemini
- **Native Integrations**: LiteLLM → Langfuse automatic tracing
- **Smart Fallbacks**: Graceful degradation when providers unavailable

### **Human-Centric Evaluation**

- **Manual Annotation**: Structured forensic evaluation criteria
- **Side-by-Side Comparison**: Evidence-based model selection
- **Feedback Loop**: Professional usability assessment

## 🔧 Implementation Guidelines

### **File Location Comments**

Each file includes a header comment indicating its intended location in the project structure:

```python
# File Location: lib/config.py
# Section: 3.1 Simplified Multi-Provider Configuration
# Description: Auto-discovery of available models with minimal configuration
```

### **Dependency Management**

- Use `uv` for all Python dependencies
- Never edit `pyproject.toml` directly - use `uv add`/`uv remove` commands
- Core dependencies: `streamlit`, `litellm[langfuse]`, `langchain-text-splitters`

### **Environment Setup**

Required environment variables by provider:

- **Azure OpenAI**: `AZURE_API_KEY`, `AZURE_API_BASE`
- **Anthropic**: `ANTHROPIC_API_KEY`
- **Google Gemini**: `GOOGLE_API_KEY`
- **Langfuse** (optional): `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`

## 📊 Benefits of Extraction

### **Developer Experience**

- **IDE Support**: Proper syntax highlighting and code completion
- **Maintainability**: Independent updates to code samples
- **Modularity**: Clear separation of concerns

### **Documentation Quality**

- **Readability**: Design document focuses on architecture, not implementation details
- **Navigation**: Easy to find specific implementations
- **Size Reduction**: Design document reduced from ~2430 to ~1200 lines (50% reduction)

### **Professional Workflow**

- **Version Control**: Code samples can be tracked and reviewed independently
- **Testing**: Sample implementations can be validated separately
- **Distribution**: Easy to package as starter templates

## 🚀 Usage

To implement the forensic report drafter:

1. **Create Project Structure**: Use the directory layout from the design document
2. **Copy Sample Code**: Place files in their indicated locations
3. **Install Dependencies**: Run `uv add` commands for required packages
4. **Configure Environment**: Set API keys for desired providers
5. **Test Setup**: Run the main app to verify provider auto-discovery

The sample code provides a complete, working implementation following the design document specifications.
