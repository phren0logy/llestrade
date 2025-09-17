#!/usr/bin/env python3
"""
Smart launcher for Forensic Report Drafter.
Routes to legacy or new UI based on environment/flags.
"""

import os
import sys


def _pop_flag(flag: str) -> None:
    """Remove a CLI flag if present to avoid leaking to downstream launchers."""
    try:
        sys.argv.remove(flag)
    except ValueError:
        pass


def _is_truthy(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "yes", "on"}


def main():
    """Determine which UI to launch and run it."""
    # Priority order:
    #   1. Explicit CLI request ("--legacy" or "--new-ui")
    #   2. Environment overrides
    #   3. Default to legacy UI while the dashboard work is in progress

    legacy_override = "--legacy" in sys.argv or _is_truthy(os.getenv("FORCE_LEGACY_UI"))
    new_ui_requested = "--new-ui" in sys.argv or _is_truthy(os.getenv("USE_NEW_UI"))

    if "--legacy" in sys.argv:
        _pop_flag("--legacy")
    if "--new-ui" in sys.argv:
        _pop_flag("--new-ui")

    use_new_ui = False
    if legacy_override:
        use_new_ui = False
    elif new_ui_requested:
        use_new_ui = True

    if use_new_ui:
        try:
            from main_new import main as new_main
        except ImportError:
            print("Warning: New UI not yet available, falling back to legacy UI")
        else:
            print("Starting Forensic Report Drafter (New UI)...")
            return new_main()

    from main_legacy import main as legacy_main
    print("Starting Forensic Report Drafter (Legacy UI)...")
    return legacy_main()


if __name__ == "__main__":
    main()
