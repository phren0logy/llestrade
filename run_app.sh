#!/bin/bash
# Run the application without debug mode
echo "🚀 Starting Forensic Report Drafter..."
echo "   Use --new-ui to preview the dashboard (beta)"
echo "   Use --legacy to force the classic UI when USE_NEW_UI is set"
echo ""
uv run main.py "$@"
