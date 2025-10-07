"""Qt item-flag helpers shared across workspace widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt


def qt_flag(*names: str) -> int:
    """Return the first matching Qt ItemFlag, handling API differences."""

    item_flag_container = getattr(Qt, "ItemFlag", None)
    for name in names:
        if item_flag_container is not None and hasattr(item_flag_container, name):
            return getattr(item_flag_container, name)
        if hasattr(Qt, name):
            return getattr(Qt, name)
    # Fallback to zero-value flag
    if item_flag_container is not None:
        return item_flag_container(0)
    return 0


ITEM_IS_USER_CHECKABLE = qt_flag("ItemIsUserCheckable")
ITEM_IS_TRISTATE = qt_flag("ItemIsTristate", "ItemIsAutoTristate")
ITEM_IS_ENABLED = qt_flag("ItemIsEnabled")

