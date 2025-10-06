"""Helpers for validation of report user prompt files."""

from __future__ import annotations

from pathlib import Path


def _read_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_refinement_prompt(path: Path) -> str:
    """Return the raw refinement user prompt content."""

    return _read_prompt(path)


def validate_refinement_prompt(content: str) -> None:
    """Ensure required refinement placeholders exist."""

    missing = [p for p in ("{draft_report}", "{template}") if p not in content]
    if missing:
        raise ValueError(
            "Refinement prompt file must include the following placeholder(s): "
            + ", ".join(missing)
        )


def read_generation_prompt(path: Path) -> str:
    """Return the raw generation user prompt content."""

    return _read_prompt(path)


def validate_generation_prompt(content: str) -> None:
    """Ensure required generation placeholders exist."""

    required_placeholders = ["{template_section}", "{transcript}", "{additional_documents}"]
    missing = [p for p in required_placeholders if p not in content]
    if missing:
        raise ValueError(
            "Generation prompt file must include the following placeholder(s): "
            + ", ".join(missing)
        )


__all__ = [
    "read_refinement_prompt",
    "validate_refinement_prompt",
    "read_generation_prompt",
    "validate_generation_prompt",
]
