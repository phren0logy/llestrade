# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for packaging the Llestrade dashboard."""

from __future__ import annotations

import atexit
import inspect
import shutil
import sys
from pathlib import Path

from PyInstaller.building.build_main import Analysis, BUNDLE, COLLECT, EXE, PYZ
from PyInstaller.config import CONF
from PyInstaller.utils.hooks import collect_submodules
from PySide6.QtCore import QLibraryInfo

block_cipher = None

spec_path = Path(inspect.getframeinfo(inspect.currentframe()).filename).resolve()
project_root = spec_path.parents[1]
src_dir = project_root / "src"
resources_dir = src_dir / "app" / "resources"
icons_dir = project_root / "assets" / "icons"

dist_dir = project_root / "dist" / sys.platform
work_dir = project_root / "build" / sys.platform / "build_dashboard"

dist_dir.mkdir(parents=True, exist_ok=True)
work_dir.mkdir(parents=True, exist_ok=True)

CONF["distpath"] = str(dist_dir)
CONF["workpath"] = str(work_dir)

distpath = str(dist_dir)
workpath = str(work_dir)

if sys.platform == "darwin":
    icon_path = icons_dir / "llestrade.icns"
    if not icon_path.exists():
        raise FileNotFoundError(
            f"Expected macOS icon at {icon_path}. Generate it via packaging/macos/build_iconset.sh."
        )
else:
    icon_path = None


def collect_tree(root: Path, prefix: str) -> list[tuple[str, str]]:
    if not root.exists():
        return []
    entries: list[tuple[str, str]] = []
    for path in root.rglob("*"):
        if path.is_file():
            rel = path.relative_to(root)
            dest_dir = Path(prefix) / rel.parent if rel.parent != Path('.') else Path(prefix)
            entries.append((str(path), str(dest_dir)))
    return entries

# ---------------------------------------------------------------------------
# Data files (resources + Qt plugins/translations)
# ---------------------------------------------------------------------------

datas = collect_tree(resources_dir, "app/resources")

qt_plugins_path = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
if sys.platform == "darwin":
    plugin_subdirs = ["platforms", "styles", "imageformats"]
elif sys.platform.startswith("win"):
    plugin_subdirs = ["platforms", "styles", "imageformats"]
else:
    plugin_subdirs = ["platforms", "imageformats", "xcbglintegrations"]

for subdir in plugin_subdirs:
    datas += collect_tree(qt_plugins_path / subdir, f"PySide6/Qt/plugins/{subdir}")

qt_translations_path = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
datas += collect_tree(qt_translations_path, "PySide6/Qt/translations")

# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------

hiddenimports = [
    "shiboken6",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtPrintSupport",
    "PySide6.QtConcurrent",
]
hiddenimports += collect_submodules("src.common.llm.providers")

# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root), str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="llestrade",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(icon_path) if icon_path else None,
)
collect_target = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="llestrade",
)

if sys.platform == "darwin":
    app = BUNDLE(
        collect_target,
        name="Llestrade.app",
        icon=str(icon_path),
        bundle_identifier="com.llestrade.dashboard",
        info_plist={
            "CFBundleDisplayName": "Llestrade",
            "CFBundleName": "Llestrade",
            "CFBundleIdentifier": "com.llestrade.dashboard",
            "NSHighResolutionCapable": True,
        },
    )
    def _remove_onedir():
        leftover_dir = Path(collect_target.name)
        if leftover_dir.exists():
            shutil.rmtree(leftover_dir)

    atexit.register(_remove_onedir)
