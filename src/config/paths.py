"""
App paths and cross-platform user directories for Llestrade.

Moves user-visible files from the legacy hidden folder (~/.forensic_report_drafter)
to a visible Documents folder: ~/Documents/llestrade (and platform equivalents).
"""

from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path
from typing import Optional


APP_FOLDER_NAME = "llestrade"
LEGACY_HIDDEN_ROOT = Path.home() / ".forensic_report_drafter"


def _xdg_documents_dir() -> Optional[Path]:
    """Best-effort attempt to read Linux XDG documents directory."""
    try:
        config = Path.home() / ".config" / "user-dirs.dirs"
        if not config.exists():
            return None
        text = config.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("XDG_DOCUMENTS_DIR"):
                parts = line.split("=", 1)
                if len(parts) != 2:
                    continue
                value = parts[1].strip().strip('"')
                # Replace $HOME token
                if value.startswith("$HOME/"):
                    value = str(Path.home() / value.split("/", 1)[1])
                p = Path(value).expanduser()
                return p
    except Exception:
        return None
    return None


def documents_dir() -> Path:
    """Return a user-visible Documents directory across platforms."""
    home = Path.home()
    if sys.platform.startswith("win"):
        candidates = [home / "Documents", home / "My Documents"]
    elif sys.platform == "darwin":
        candidates = [home / "Documents"]
    else:
        xdg = _xdg_documents_dir()
        candidates = [xdg] if xdg else [home / "Documents"]

    for c in candidates:
        if c and c.exists():
            return c
    # Fallback to home if Documents isn't present
    return home


def app_user_root() -> Path:
    root = documents_dir() / APP_FOLDER_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def app_config_dir() -> Path:
    p = app_user_root() / "config"
    p.mkdir(parents=True, exist_ok=True)
    return p


def app_prompts_root() -> Path:
    p = app_user_root() / "prompts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def app_logs_dir() -> Path:
    p = app_user_root() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def app_crashes_dir() -> Path:
    p = app_user_root() / "crashes"
    p.mkdir(parents=True, exist_ok=True)
    return p


def maybe_migrate_legacy() -> None:
    """Move legacy hidden app folder into the new visible Documents root.

    Copies prompts/, config/, logs/, crashes/ subfolders if present and the target
    folders do not yet exist. Legacy folder is left in place to avoid destructive
    behavior; users can remove it after confirming everything is in place.
    """
    if not LEGACY_HIDDEN_ROOT.exists():
        return
    target = app_user_root()
    for name in ("prompts", "config", "logs", "crashes"):
        src = LEGACY_HIDDEN_ROOT / name
        dst = target / name
        try:
            if src.exists() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
        except Exception:
            # Best-effort migration; ignore failures
            continue


__all__ = [
    "documents_dir",
    "app_user_root",
    "app_config_dir",
    "app_prompts_root",
    "app_logs_dir",
    "app_crashes_dir",
    "maybe_migrate_legacy",
]

