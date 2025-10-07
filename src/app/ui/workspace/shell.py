"""Workspace shell coordinating dashboard tabs.

This module initially provides scaffolding for a future refactor where the
existing :class:`ProjectWorkspace` QWidget will be decomposed into focused tab
widgets. For now the shell exposes a minimal interface so call sites can be
progressively migrated without large-scale rewrites.
"""

from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget


class WorkspaceShell(QWidget):
    """Thin container that will own the tab widget for the dashboard."""

    home_requested = Signal()

    def __init__(self, *, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tabs = QTabWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tabs)

    def add_tab(self, widget: QWidget, title: str) -> None:
        """Attach a new tab to the shell."""

        self._tabs.addTab(widget, title)

    def set_current_tab(self, index: int) -> None:
        """Switch to the requested tab index if it exists."""

        if 0 <= index < self._tabs.count():
            self._tabs.setCurrentIndex(index)

    def iter_tabs(self) -> Iterable[QWidget]:
        """Yield tab widgets in order."""

        for idx in range(self._tabs.count()):
            widget = self._tabs.widget(idx)
            if widget is not None:
                yield widget

    def shutdown(self) -> None:
        """Proxy shutdown events to child tabs when present."""

        for widget in self.iter_tabs():
            shutdown = getattr(widget, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:  # pragma: no cover - defensive cleanup
                    continue

