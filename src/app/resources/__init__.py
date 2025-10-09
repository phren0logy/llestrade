"""Resource helpers for the dashboard application."""

from __future__ import annotations

from importlib import resources
from pathlib import Path


def prompts_dir() -> Path:
    """Return the filesystem path to bundled prompt templates."""
    return Path(resources.files(__name__).joinpath("prompts"))


def templates_dir() -> Path:
    """Return the filesystem path to bundled report templates."""
    return Path(resources.files(__name__).joinpath("templates"))


def placeholder_sets_dir() -> Path:
    """Return the filesystem path to bundled placeholder set markdown files."""
    return Path(resources.files(__name__).joinpath("placeholder_sets"))


__all__ = ["prompts_dir", "templates_dir", "placeholder_sets_dir"]
