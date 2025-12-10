"""Shared checkpoint helpers for bulk map/reduce workers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Optional


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CheckpointManager:
    """Lightweight checkpoint IO for map and reduce stages."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    # ---------------------------
    # Generic helpers
    # ---------------------------
    def _read_json(self, path: Path) -> Optional[dict]:
        try:
            raw = path.read_text(encoding="utf-8")
            return json.loads(raw)
        except Exception:
            return None

    def _write_json(self, path: Path, payload: Dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _read_text(self, path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return None

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _safe_doc_path(self, relative_path: str) -> Path:
        return Path(relative_path).as_posix()

    # ---------------------------
    # Map checkpoints
    # ---------------------------
    def map_chunk_path(self, document_rel: str, index: int) -> Path:
        safe_rel = Path(self._safe_doc_path(document_rel))
        return self.base_dir / "map" / safe_rel / f"chunk_{index}.json"

    def load_map_chunk(self, document_rel: str, index: int) -> Optional[dict]:
        return self._read_json(self.map_chunk_path(document_rel, index))

    def save_map_chunk(self, document_rel: str, index: int, content: str, input_checksum: str) -> None:
        payload = {"input_checksum": input_checksum, "content": content, "content_checksum": _sha256(content)}
        self._write_json(self.map_chunk_path(document_rel, index), payload)

    def clear_map_document(self, document_rel: str) -> None:
        path = self.base_dir / "map" / Path(self._safe_doc_path(document_rel))
        if path.exists():
            for child in sorted(path.rglob("*"), reverse=True):
                try:
                    child.unlink()
                except IsADirectoryError:
                    try:
                        child.rmdir()
                    except Exception:
                        pass
                except Exception:
                    pass
            try:
                path.rmdir()
            except Exception:
                pass

    # ---------------------------
    # Reduce checkpoints
    # ---------------------------
    def reduce_chunk_path(self, index: int) -> Path:
        return self.base_dir / "reduce" / "chunks" / f"chunk_{index}.json"

    def load_reduce_chunk(self, index: int) -> Optional[dict]:
        return self._read_json(self.reduce_chunk_path(index))

    def save_reduce_chunk(self, index: int, content: str, input_checksum: str) -> None:
        payload = {"input_checksum": input_checksum, "content": content, "content_checksum": _sha256(content)}
        self._write_json(self.reduce_chunk_path(index), payload)

    def reduce_batch_path(self, level: int, batch_index: int) -> Path:
        return self.base_dir / "reduce" / "batches" / f"level_{level}_batch_{batch_index}.json"

    def load_reduce_batch(self, level: int, batch_index: int) -> Optional[dict]:
        return self._read_json(self.reduce_batch_path(level, batch_index))

    def save_reduce_batch(self, level: int, batch_index: int, content: str, input_checksum: str) -> None:
        payload = {"input_checksum": input_checksum, "content": content, "content_checksum": _sha256(content)}
        self._write_json(self.reduce_batch_path(level, batch_index), payload)

    def clear_reduce(self) -> None:
        reduce_root = self.base_dir / "reduce"
        if not reduce_root.exists():
            return
        for child in sorted(reduce_root.rglob("*"), reverse=True):
            try:
                child.unlink()
            except IsADirectoryError:
                try:
                    child.rmdir()
                except Exception:
                    pass
            except Exception:
                pass
        try:
            reduce_root.rmdir()
        except Exception:
            pass

    def clear_all(self) -> None:
        if not self.base_dir.exists():
            return
        for child in sorted(self.base_dir.rglob("*"), reverse=True):
            try:
                child.unlink()
            except IsADirectoryError:
                try:
                    child.rmdir()
                except Exception:
                    pass
            except Exception:
                pass
        try:
            self.base_dir.rmdir()
        except Exception:
            pass


__all__ = ["CheckpointManager", "_sha256"]

