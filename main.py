#!/usr/bin/env python3
"""Entry point for the Llestrade dashboard UI."""


def main() -> int:
    """Launch the dashboard UI."""
    from src.app import run

    print("Starting Llestrade (Dashboard UI)...")
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
