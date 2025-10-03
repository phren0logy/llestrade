#!/bin/bash
# Run the new simplified UI with Phoenix observability
echo "🆕 Starting Llestrade (New UI)..."
echo "================================================"
echo ""
echo "This will launch the new simplified interface with Phoenix observability."
echo ""
echo "🔍 Phoenix Observability: ENABLED"
echo "📊 Phoenix UI will be available at: http://localhost:6006"
echo "📁 Project: llestrade"
echo ""
echo "Starting application..."
echo ""

# Enable Phoenix observability
export PHOENIX_ENABLED=true
export PHOENIX_PORT=6006
export PHOENIX_PROJECT=llestrade
export PHOENIX_EXPORT_FIXTURES=false

# Run dashboard UI directly
uv run -m src.app
