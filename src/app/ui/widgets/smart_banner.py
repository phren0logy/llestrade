"""Reusable smart banner widget for presenting actionable status messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List, Sequence

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class BannerAction:
    """Declarative definition of a banner action button."""

    label: str
    callback: Callable[[], None]
    is_default: bool = False


class SmartBanner(QFrame):
    """Highlight status with optional actions in a compact banner."""

    _ROLE_STYLES = {
        "info": {"bg": "#f5f7fb", "border": "#d5dceb"},
        "warning": {"bg": "#fff6e5", "border": "#f0c36b"},
        "success": {"bg": "#edf8f0", "border": "#8ecf9c"},
        "error": {"bg": "#fdf2f2", "border": "#f5a5a5"},
    }

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SmartBanner")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)

        self._primary_label = QLabel(self)
        primary_font = self._primary_label.font()
        primary_font.setBold(True)
        self._primary_label.setFont(primary_font)
        self._primary_label.setWordWrap(True)

        self._secondary_label = QLabel(self)
        self._secondary_label.setWordWrap(True)
        self._secondary_label.setStyleSheet("color: #4b5563;")

        self._actions_container = QWidget(self)
        self._actions_layout = QHBoxLayout(self._actions_container)
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(8)
        self._actions_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        layout.addWidget(self._primary_label)
        layout.addWidget(self._secondary_label)
        layout.addWidget(self._actions_container)

        self._action_buttons: List[QPushButton] = []
        self._role = "info"
        self._apply_role_style()
        self._actions_container.hide()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_message(self, primary: str, secondary: str | None = None) -> None:
        """Update the banner message."""
        self._primary_label.setText(primary)
        if secondary:
            self._secondary_label.setText(secondary)
            self._secondary_label.show()
        else:
            self._secondary_label.clear()
            self._secondary_label.hide()

    def set_actions(self, actions: Sequence[BannerAction] | Iterable[BannerAction]) -> None:
        """Configure the interactive buttons displayed within the banner."""
        for button in self._action_buttons:
            button.deleteLater()
        self._action_buttons.clear()

        actions_list = list(actions)
        if not actions_list:
            self._actions_container.hide()
            return

        # Remove trailing stretch before populating buttons.
        stretch = self._actions_layout.takeAt(self._actions_layout.count() - 1)
        if stretch is not None:
            del stretch

        for action in actions_list:
            button = QPushButton(action.label, self._actions_container)
            if action.is_default:
                button.setDefault(True)
                button.setStyleSheet("font-weight: 600;")
            button.clicked.connect(action.callback)
            self._actions_layout.addWidget(button)
            self._action_buttons.append(button)

        self._actions_layout.addStretch()
        self._actions_container.show()

    def clear_actions(self) -> None:
        """Remove all configured actions."""
        self.set_actions([])

    def set_role(self, role: str) -> None:
        """Update the visual role (info, warning, success, error)."""
        if role == self._role:
            return
        self._role = role if role in self._ROLE_STYLES else "info"
        self._apply_role_style()

    def reset(self) -> None:
        """Reset the banner to an empty hidden state."""
        self.setVisible(False)
        self.set_message("")
        self.clear_actions()
        self.set_role("info")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _apply_role_style(self) -> None:
        style = self._ROLE_STYLES.get(self._role, self._ROLE_STYLES["info"])
        self.setStyleSheet(
            (
                "QFrame#SmartBanner {"
                f"background-color: {style['bg']};"
                f"border: 1px solid {style['border']};"
                "border-radius: 6px;"
                "}"
                "QFrame#SmartBanner QLabel { color: #1f2933; }"
            )
        )


__all__ = ["BannerAction", "SmartBanner"]

