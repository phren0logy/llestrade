#!/bin/bash
# Run the new simplified UI
echo "🆕 Starting Forensic Report Drafter (New UI)..."
echo "================================================"
echo ""
echo "This will launch the new simplified interface."
echo "The new UI is currently under development."
echo ""

# Set environment variable and run
export USE_NEW_UI=true
uv run main.py "$@"