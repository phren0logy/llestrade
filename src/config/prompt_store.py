"""
Prompt storage and synchronization utilities.

Design:
- Keep all prompts in a user-writable config folder outside the app bundle.
- Maintain two categories:
  - bundled/: copies of prompts shipped with the app (managed by the app)
  - custom/: user-authored prompts (never overwritten)
- On install/update, sync bundled prompts from the app resources into bundled/.
  Custom prompts are untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from .paths import app_prompts_root, app_user_root, get_repo_prompts_dir as _repo_prompts_dir, maybe_migrate_legacy


def get_prompts_root() -> Path:
    maybe_migrate_legacy()
    return app_prompts_root()


def get_bundled_dir() -> Path:
    path = get_prompts_root() / "bundled"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_custom_dir() -> Path:
    path = get_prompts_root() / "custom"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_repo_prompts_dir() -> Path:
    return _repo_prompts_dir()


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_md_files(folder: Path) -> Dict[str, Path]:
    files: Dict[str, Path] = {}
    if not folder.exists():
        return files
    for p in sorted(folder.glob("*.md")):
        if p.is_file():
            files[p.name] = p
    return files


def _manifest_path() -> Path:
    return get_bundled_dir() / ".manifest.json"


def load_manifest() -> dict:
    path = _manifest_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_manifest(payload: dict) -> None:
    path = _manifest_path()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def compute_repo_digest(repo_dir: Path) -> dict:
    files = _collect_md_files(repo_dir)
    entries = {name: _hash_file(path) for name, path in files.items()}
    combined = hashlib.sha256()
    for name in sorted(entries):
        combined.update(name.encode("utf-8"))
        combined.update(entries[name].encode("utf-8"))
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
        "digest": combined.hexdigest(),
    }


def sync_bundled_prompts(*, force: bool = False) -> dict:
    """Sync bundled prompts from the app resources into the user store.

    - Copies new files
    - Updates changed files when force=True; otherwise leaves existing as-is
    - Never touches custom/ directory

    Returns a summary dict with keys: copied, updated, skipped, same
    """
    repo_dir = get_repo_prompts_dir()
    bundled_dir = get_bundled_dir()
    repo_files = _collect_md_files(repo_dir)
    bundled_files = _collect_md_files(bundled_dir)

    manifest = load_manifest()
    repo_digest = compute_repo_digest(repo_dir)

    copied: List[str] = []
    updated: List[str] = []
    skipped: List[str] = []
    same: List[str] = []

    for name, src in repo_files.items():
        dst = bundled_dir / name
        if not dst.exists():
            dst.write_bytes(src.read_bytes())
            copied.append(name)
            continue
        src_hash = _hash_file(src)
        dst_hash = _hash_file(dst)
        if src_hash == dst_hash:
            same.append(name)
        else:
            if force:
                # Overwrite only the managed bundled copy
                dst.write_bytes(src.read_bytes())
                updated.append(name)
            else:
                skipped.append(name)

    save_manifest({
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "repo_digest": repo_digest,
        "copied": copied,
        "updated": updated,
        "skipped": skipped,
        "same": same,
    })

    return {
        "copied": copied,
        "updated": updated,
        "skipped": skipped,
        "same": same,
    }


__all__ = [
    "get_prompts_root",
    "get_bundled_dir",
    "get_custom_dir",
    "get_repo_prompts_dir",
    "sync_bundled_prompts",
    "load_manifest",
    "save_manifest",
]
