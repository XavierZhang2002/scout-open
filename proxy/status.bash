#!/bin/bash
# Check Claude Code Router service status

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/log/ccr.pid"

echo "=== Claude Code Router Status ==="

# Check PID file
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "  Status: Running ✓"
        echo "  PID:    $PID"
    else
        echo "  Status: Stopped (stale PID file)"
    fi
else
    echo "  Status: Not deployed (no PID file)"
fi

# Check port
PORT_PID=$(lsof -ti:3456 2>/dev/null || true)
if [ -n "$PORT_PID" ]; then
    echo "  Port:   3456 occupied (PID: $PORT_PID)"
else
    echo "  Port:   3456 available"
fi

# Health check
echo ""
echo "  Health check:"
HEALTH=$(curl -s --connect-timeout 2 http://localhost:3456/health 2>/dev/null || echo "FAIL")
if echo "$HEALTH" | grep -q "ok"; then
    echo "  GET /health → ✓ $HEALTH"
else
    echo "  GET /health → ✗ Service not responding"
fi

# Recent log lines
LOG_FILE="$SCRIPT_DIR/log/ccr.log"
if [ -f "$LOG_FILE" ]; then
    echo ""
    echo "  Recent logs (last 5 lines):"
    tail -5 "$LOG_FILE" | sed 's/^/    /'
fi
