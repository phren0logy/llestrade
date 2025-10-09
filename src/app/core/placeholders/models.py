"""Project placeholder data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence


@dataclass(slots=True)
class PlaceholderEntry:
    """Represent a single placeholder key/value pair."""

    key: str
    value: str = ""
    read_only: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {"key": self.key, "value": self.value, "read_only": self.read_only}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "PlaceholderEntry":
        return cls(
            key=str(payload.get("key", "")),
            value=str(payload.get("value", "")),
            read_only=bool(payload.get("read_only", False)),
        )


@dataclass
class ProjectPlaceholders:
    """Container for project placeholder entries."""

    entries: List[PlaceholderEntry] = field(default_factory=list)

    def to_list(self) -> List[Dict[str, object]]:
        return [entry.to_dict() for entry in self.entries]

    @classmethod
    def from_list(cls, payload: Iterable[Mapping[str, object]]) -> "ProjectPlaceholders":
        entries = [PlaceholderEntry.from_dict(item) for item in payload]
        return cls(entries=entries)

    def as_mapping(self, *, include_read_only: bool = True) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for entry in self.entries:
            if not include_read_only and entry.read_only:
                continue
            mapping[entry.key] = entry.value
        return mapping

    def set_value(self, key: str, value: str, *, read_only: bool = False) -> None:
        entry = self._find_entry(key)
        if entry:
            entry.value = value
            if read_only:
                entry.read_only = True
            return
        self.entries.append(PlaceholderEntry(key=key, value=value, read_only=read_only))

    def remove(self, key: str) -> None:
        self.entries = [entry for entry in self.entries if entry.key != key]

    def ensure_keys(self, keys: Sequence[str], *, read_only: bool = False) -> None:
        existing = {entry.key: entry for entry in self.entries}
        for key in keys:
            if key in existing:
                if read_only:
                    existing[key].read_only = True
                continue
            self.entries.append(PlaceholderEntry(key=key, read_only=read_only))

    def merge_with(self, additional: Mapping[str, str], *, mark_read_only: bool = False) -> None:
        for key, value in additional.items():
            entry = self._find_entry(key)
            if entry:
                entry.value = value
                if mark_read_only:
                    entry.read_only = True
            else:
                self.entries.append(PlaceholderEntry(key=key, value=value, read_only=mark_read_only))

    def merged_mapping(self, *maps: Mapping[str, str]) -> Dict[str, str]:
        result = self.as_mapping()
        for mapping in maps:
            result.update(mapping)
        return result

    def _find_entry(self, key: str) -> PlaceholderEntry | None:
        for entry in self.entries:
            if entry.key == key:
                return entry
        return None


__all__ = ["PlaceholderEntry", "ProjectPlaceholders"]
