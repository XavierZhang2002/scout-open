#!/bin/bash
# Stop the Claude Code Router service

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/log/ccr.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping Claude Code Router (PID: $PID) ..."
        kill "$PID"
        rm -f "$PID_FILE"
        echo "✓ Stopped"
    else
        echo "Process $PID no longer exists, cleaning up PID file"
        rm -f "$PID_FILE"
    fi
else
    echo "PID file not found, attempting to find process by port..."
    PID=$(lsof -ti:3456 2>/dev/null || true)
    if [ -n "$PID" ]; then
        echo "Found process occupying port 3456: $PID"
        kill "$PID"
        echo "✓ Stopped"
    else
        echo "No running CCR service found"
    fi
fi
