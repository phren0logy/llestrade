#!/usr/bin/env python3
"""Entry point for the Forensic Report Drafter dashboard UI."""


def main() -> None:
    """Launch the new dashboard UI."""
    from main_new import main as new_main

    print("Starting Forensic Report Drafter (Dashboard UI)...")
    return new_main()


if __name__ == "__main__":
    main()
