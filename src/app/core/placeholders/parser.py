"""Markdown placeholder parsing utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*+]|[\d]+[.)])\s*")
SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class PlaceholderParseError(ValueError):
    """Raised when a placeholder list contains invalid entries."""


@dataclass(frozen=True)
class ParsedPlaceholderSet:
    """Container for parsed keys."""

    keys: List[str]


def parse_placeholder_markdown(text: str) -> ParsedPlaceholderSet:
    """Parse placeholder keys from markdown text.

    Each non-empty line optionally prefixed with a bullet is treated as a key.
    Keys must use ``snake_case`` and be unique within the file.
    """

    keys: List[str] = []
    seen: set[str] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        line = BULLET_PREFIX_RE.sub("", line, count=1).strip()
        if not line:
            continue

        if ":" in line:
            raise PlaceholderParseError(f"Invalid placeholder entry '{raw_line}': default values are not supported.")

        if not SNAKE_CASE_RE.fullmatch(line):
            raise PlaceholderParseError(f"Invalid placeholder key '{line}'. Keys must be snake_case.")

        if line in seen:
            raise PlaceholderParseError(f"Duplicate placeholder key '{line}'.")

        seen.add(line)
        keys.append(line)

    return ParsedPlaceholderSet(keys=keys)


def parse_placeholder_file(path: Path) -> ParsedPlaceholderSet:
    """Load and parse a placeholder markdown file."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem failure
        raise PlaceholderParseError(f"Failed to read placeholder file '{path}': {exc}") from exc
    return parse_placeholder_markdown(text)


__all__ = ["ParsedPlaceholderSet", "PlaceholderParseError", "parse_placeholder_markdown", "parse_placeholder_file"]
