"""Helpers for loading combined refinement instructions/prompt files."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple


def load_refinement_prompt(path: Path) -> Tuple[str, str]:
    """Return (instructions, prompt_template) from a markdown refinement file.

    Expected format:

        ## Instructions
        ...instructions markdown...

        ## Prompt
        ...prompt template with placeholders...

    Section headers are case-insensitive. If the instructions section is missing,
    an empty string is returned. If the prompt section is missing, the entire file
    content is treated as the prompt template.
    """

    text = path.read_text(encoding="utf-8")

    sections = {"instructions": "", "prompt": ""}
    current: str | None = None
    buffer: list[str] = []

    def _flush(target: str | None) -> None:
        if target and buffer:
            sections[target] = "\n".join(buffer).strip()
            buffer.clear()

    for line in text.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("## instructions") or lower.startswith("# instructions"):
            _flush(current)
            current = "instructions"
            continue
        if lower.startswith("## prompt") or lower.startswith("# prompt"):
            _flush(current)
            current = "prompt"
            continue
        if current:
            buffer.append(line)
        else:
            # Lines before any header belong to the prompt by default
            sections["prompt"] += ("\n" if sections["prompt"] else "") + line

    _flush(current)

    if not sections["prompt"].strip():
        sections["prompt"] = text.strip()

    return sections["instructions"].strip(), sections["prompt"].strip()


__all__ = ["load_refinement_prompt"]
