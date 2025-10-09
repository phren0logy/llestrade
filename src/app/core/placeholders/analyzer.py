"""Placeholder analysis and highlighting utilities."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

PLACEHOLDER_PATTERN = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def find_placeholders(text: str) -> set[str]:
    """Return all placeholder names referenced in ``text``."""

    return set(match.group(1) for match in PLACEHOLDER_PATTERN.finditer(text or ""))


@dataclass(slots=True)
class PlaceholderUsage:
    """Per-placeholder usage information."""

    name: str
    required: bool
    has_value: bool
    value: str
    used_in_system: bool
    used_in_user: bool


@dataclass(slots=True)
class PlaceholderAnalysis:
    """Aggregated placeholder usage metadata."""

    used: set[str]
    available: set[str]
    missing_required: set[str]
    missing_optional: set[str]
    unused: set[str]
    usages: tuple[PlaceholderUsage, ...]


def analyse_prompts(
    system_template: str,
    user_template: str,
    *,
    available_values: Mapping[str, str],
    required_keys: Iterable[str] | None = None,
    optional_keys: Iterable[str] | None = None,
) -> PlaceholderAnalysis:
    """Inspect prompts and return placeholder usage metadata."""

    required_set = set(required_keys or [])
    optional_set = set(optional_keys or [])
    available_map = {key: (value or "") for key, value in (available_values or {}).items()}

    system_used = find_placeholders(system_template or "")
    user_used = find_placeholders(user_template or "")
    used = system_used | user_used
    available_keys = set(available_map)

    # If optional keys not provided, treat any used-but-not-required as optional
    if not optional_set:
        optional_set = used - required_set

    missing_required = {key for key in required_set if key in used and not available_map.get(key)}
    missing_optional = {key for key in optional_set if key in used and not available_map.get(key)}
    unused_keys = (available_keys | required_set | optional_set) - used

    usages: list[PlaceholderUsage] = []
    for key in sorted(used | unused_keys):
        has_value = bool(available_map.get(key))
        usages.append(
            PlaceholderUsage(
                name=key,
                required=key in required_set,
                has_value=has_value,
                value=available_map.get(key, ""),
                used_in_system=key in system_used,
                used_in_user=key in user_used,
            )
        )

    return PlaceholderAnalysis(
        used=used,
        available=available_keys,
        missing_required=missing_required,
        missing_optional=missing_optional,
        unused=unused_keys,
        usages=tuple(usages),
    )


def highlight_placeholders_raw(text: str, *, values: Mapping[str, str], required: Iterable[str] | None = None) -> str:
    """Return HTML highlighting placeholders in raw templates."""

    required_set = set(required or [])
    values_map = {key: (values or {}).get(key, "") for key in find_placeholders(text or "")}

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        classes = ["placeholder"]
        if values_map.get(key):
            classes.append("ok")
        else:
            classes.append("missing")
        if key in required_set:
            classes.append("required")
        token = html.escape(match.group(0))
        return f"<span class=\"{' '.join(classes)}\">{token}</span>"

    result_parts: list[str] = []
    last = 0
    for match in PLACEHOLDER_PATTERN.finditer(text or ""):
        start, end = match.span()
        result_parts.append(html.escape((text or "")[last:start]))
        result_parts.append(_replace(match))
        last = end
    result_parts.append(html.escape((text or "")[last:]))
    return "".join(result_parts)


def render_preview_html(
    template: str,
    *,
    values: Mapping[str, str],
    required: Iterable[str] | None = None,
) -> str:
    """Return HTML for the preview version with substitutions."""

    required_set = set(required or [])
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = (values or {}).get(key, "")
        classes = ["placeholder"]
        if value:
            classes.append("ok")
            content = html.escape(value)
        else:
            classes.append("missing")
            content = "&nbsp;"  # show red highlight even when empty
        if key in required_set:
            classes.append("required")
        return f"<span class=\"{' '.join(classes)}\">{content}</span>"

    result_parts: list[str] = []
    last = 0
    text = template or ""
    for match in PLACEHOLDER_PATTERN.finditer(text):
        start, end = match.span()
        result_parts.append(html.escape(text[last:start]))
        result_parts.append(_replace(match))
        last = end
    result_parts.append(html.escape(text[last:]))
    return "".join(result_parts)


def build_preview_styles() -> str:
    """Return CSS styles used by prompt preview widgets."""

    return """
<style>
.placeholder {
    padding: 0 2px;
    border-radius: 3px;
}
.placeholder.ok {
    background-color: rgba(46, 204, 113, 0.2);
    color: #0b6b2e;
}
.placeholder.missing {
    background-color: rgba(231, 76, 60, 0.25);
    color: #96281b;
    border-bottom: 1px dotted #c0392b;
}
.placeholder.required {
    font-weight: 600;
}
.placeholder.missing.required {
    background-color: rgba(192, 57, 43, 0.35);
}
pre {
    white-space: pre-wrap;
    font-family: \"JetBrains Mono\", \"Courier New\", monospace;
}
</style>
"""


__all__ = [
    "PlaceholderAnalysis",
    "PlaceholderUsage",
    "analyse_prompts",
    "build_preview_styles",
    "find_placeholders",
    "highlight_placeholders_raw",
    "render_preview_html",
]
