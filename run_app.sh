#!/bin/bash
# Run the application without debug mode
echo "🚀 Starting Forensic Report Drafter..."
echo "   Use --new-ui flag to test the new interface"
echo ""
uv run main.py "$@"