"""Helpers for validation of refinement prompt files."""

from __future__ import annotations

from pathlib import Path


def read_refinement_prompt(path: Path) -> str:
    """Return the raw refinement prompt content."""

    return path.read_text(encoding="utf-8")


def validate_refinement_prompt(content: str) -> None:
    """Ensure required placeholders exist."""

    missing = []
    for required in ("{draft_report}", "{template}"):
        if required not in content:
            missing.append(required)
    if missing:
        raise ValueError(
            "Refinement prompt file must include the following placeholder(s): "
            + ", ".join(missing)
        )


__all__ = ["read_refinement_prompt", "validate_refinement_prompt"]
