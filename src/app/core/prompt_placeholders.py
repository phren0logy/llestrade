"""Central utilities for LLM prompt placeholders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Sequence


class MissingPlaceholdersError(ValueError):
    """Raised when a prompt template is missing required placeholders."""

    def __init__(self, prompt_key: str, missing: Sequence[str]) -> None:
        formatted = ", ".join(f"{{{name}}}" for name in missing)
        super().__init__(
            f"Prompt '{prompt_key}' is missing required placeholder(s): {formatted}"
        )
        self.prompt_key = prompt_key
        self.missing = tuple(missing)


@dataclass(frozen=True)
class PromptPlaceholderSpec:
    """Placeholder requirements and optional fields for a prompt template."""

    key: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    description: str | None = None

    def all_placeholders(self) -> tuple[str, ...]:
        """Return all defined placeholder names."""
        return self.required + self.optional


def _sorted(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(values)))


_PROMPT_SPECS: Dict[str, PromptPlaceholderSpec] = {}


def register_prompt_spec(spec: PromptPlaceholderSpec) -> None:
    """Register or replace a prompt placeholder specification."""

    _PROMPT_SPECS[spec.key] = spec


def get_prompt_spec(prompt_key: str) -> PromptPlaceholderSpec | None:
    """Return the placeholder specification for the prompt key, if known."""

    return _PROMPT_SPECS.get(prompt_key)


def ensure_required_placeholders(prompt_key: str, template: str) -> None:
    """Validate that the template contains the required placeholders."""

    spec = get_prompt_spec(prompt_key)
    if not spec:
        return

    missing = [
        name for name in spec.required if f"{{{name}}}" not in template
    ]
    if missing:
        raise MissingPlaceholdersError(prompt_key, missing)


def format_prompt(template: str, context: Mapping[str, object] | None = None) -> str:
    """Format a template with placeholder fallbacks for missing keys."""

    class _Fallback(dict):
        def __missing__(self, key: str) -> str:  # noqa: D401 - placeholder fallback
            return "{" + key + "}"

    safe_context = _Fallback()
    if context:
        for key, value in context.items():
            safe_context[key] = "" if value is None else str(value)
    return template.format_map(safe_context)


def placeholder_summary(prompt_key: str) -> str:
    """Return a human-readable summary of placeholders for UI tooltips."""

    spec = get_prompt_spec(prompt_key)
    if not spec:
        return "This prompt does not declare placeholder requirements."

    parts: list[str] = []
    if spec.required:
        formatted = ", ".join(f"{{{name}}}" for name in spec.required)
        parts.append(f"Required placeholders: {formatted}")
    if spec.optional:
        formatted = ", ".join(f"{{{name}}}" for name in spec.optional)
        parts.append(f"Optional placeholders: {formatted}")
    if not parts:
        parts.append("This prompt does not use placeholders.")
    return "\n".join(parts)


def all_prompt_specs() -> tuple[PromptPlaceholderSpec, ...]:
    """Return all registered placeholder specifications."""

    return tuple(_PROMPT_SPECS.values())


def _register_defaults() -> None:
    register_prompt_spec(
        PromptPlaceholderSpec(
            key="document_analysis_system_prompt",
            required=(),
            optional=_sorted(("subject_name", "subject_dob", "case_info")),
            description="System prompt for bulk analysis runs.",
        )
    )
    register_prompt_spec(
        PromptPlaceholderSpec(
            key="document_bulk_analysis_prompt",
            required=("document_content",),
            optional=_sorted(
                ("subject_name", "subject_dob", "case_info", "document_name", "chunk_index", "chunk_total")
            ),
            description="User prompt for per-document bulk analysis.",
        )
    )
    register_prompt_spec(
        PromptPlaceholderSpec(
            key="integrated_analysis_prompt",
            required=("document_content",),
            optional=_sorted(("subject_name", "subject_dob", "case_info")),
            description="Prompt for combining multiple document analyses.",
        )
    )
    register_prompt_spec(
        PromptPlaceholderSpec(
            key="report_generation_user_prompt",
            required=("template_section", "transcript", "additional_documents"),
            optional=_sorted(("section_title", "document_content")),
            description="User prompt for report section generation.",
        )
    )
    register_prompt_spec(
        PromptPlaceholderSpec(
            key="refinement_prompt",
            required=("draft_report", "template"),
            optional=_sorted(("transcript",)),
            description="Prompt for refining the generated report draft.",
        )
    )
    register_prompt_spec(
        PromptPlaceholderSpec(
            key="report_generation_instructions",
            required=("template_section", "transcript"),
            optional=_sorted(()),
            description="Instructions fragment for section generation.",
        )
    )
    register_prompt_spec(
        PromptPlaceholderSpec(
            key="report_generation_system_prompt",
            required=(),
            optional=_sorted(()),
            description="System prompt for report section generation.",
        )
    )
    register_prompt_spec(
        PromptPlaceholderSpec(
            key="report_refinement_system_prompt",
            required=(),
            optional=_sorted(()),
            description="System prompt for report refinement.",
        )
    )
    register_prompt_spec(
        PromptPlaceholderSpec(
            key="section_processing",
            required=(),
            optional=_sorted(()),
            description="Legacy section processing prompt.",
        )
    )
    register_prompt_spec(
        PromptPlaceholderSpec(
            key="system_prompt",
            required=(),
            optional=_sorted(()),
            description="Default global system prompt.",
        )
    )


_register_defaults()

__all__ = [
    "MissingPlaceholdersError",
    "PromptPlaceholderSpec",
    "all_prompt_specs",
    "ensure_required_placeholders",
    "format_prompt",
    "get_prompt_spec",
    "placeholder_summary",
    "register_prompt_spec",
]
