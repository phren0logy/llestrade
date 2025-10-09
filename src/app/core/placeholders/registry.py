"""Registry for bundled/custom placeholder sets."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from src.config.placeholder_store import (
    get_placeholder_bundled_dir,
    get_placeholder_custom_dir,
)

from .parser import PlaceholderParseError, parse_placeholder_file

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PlaceholderSetDescriptor:
    """Describe a parsed placeholder set."""

    name: str
    path: Path
    origin: str  # "custom" or "bundled"
    keys: Sequence[str]


class PlaceholderSetRegistry:
    """Discover and cache available placeholder sets."""

    def __init__(
        self,
        *,
        custom_dir: Path | None = None,
        bundled_dir: Path | None = None,
    ) -> None:
        self._custom_dir = custom_dir or get_placeholder_custom_dir()
        self._bundled_dir = bundled_dir or get_placeholder_bundled_dir()
        self._cache: Dict[str, PlaceholderSetDescriptor] = {}

    def refresh(self) -> None:
        """Rebuild the registry cache from disk."""

        entries: Dict[str, PlaceholderSetDescriptor] = {}

        def _register(paths: Iterable[Path], origin: str) -> None:
            for path in paths:
                name = path.stem
                try:
                    parsed = parse_placeholder_file(path)
                except PlaceholderParseError as exc:
                    LOGGER.warning("Skipping placeholder set %s (%s): %s", path, origin, exc)
                    continue
                if name in entries:
                    # Custom sets override bundled ones
                    if origin == "custom":
                        LOGGER.debug("Overriding bundled placeholder set '%s' with custom copy", name)
                    else:
                        LOGGER.debug("Ignoring duplicate placeholder set '%s' from %s", name, origin)
                        continue
                entries[name] = PlaceholderSetDescriptor(
                    name=name,
                    path=path,
                    origin=origin,
                    keys=parsed.keys,
                )

        custom_paths = sorted(self._custom_dir.glob("*.md"))
        bundled_paths = sorted(self._bundled_dir.glob("*.md"))
        _register(bundled_paths, "bundled")
        _register(custom_paths, "custom")

        self._cache = entries

    def all_sets(self) -> List[PlaceholderSetDescriptor]:
        if not self._cache:
            self.refresh()
        return sorted(self._cache.values(), key=lambda item: (item.origin != "custom", item.name))

    def get(self, name: str) -> Optional[PlaceholderSetDescriptor]:
        if not self._cache:
            self.refresh()
        return self._cache.get(name)

    def names(self) -> List[str]:
        return [descriptor.name for descriptor in self.all_sets()]


__all__ = ["PlaceholderSetDescriptor", "PlaceholderSetRegistry"]
