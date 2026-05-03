#!/bin/bash
# Scout Proxy — Claude Code Router One-Click Deployment Script
#
# Usage:
#   cd LTU-agent/proxy
#   bash deploy.bash
#
# Features:
#   Copies .claude-code-router config to ~/ and starts the Claude Code Router service.
#   The service listens on localhost:3456, routing Anthropic Messages API requests to various LLM Providers.
#
# Stop the service:
#   bash stop.bash  (or kill $(cat ~/.claude-code-router/ccr.pid))

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/log"

mkdir -p "$LOG_DIR"

echo "=== Scout Proxy — Claude Code Router Deployment ==="
echo ""

# 1. Copy config to ~/
echo "[1/3] Copying config to ~/.claude-code-router/ ..."
cp -r "$SCRIPT_DIR/.claude-code-router" ~/
echo "  ✓ Config copied"

# 2. Install dependencies
echo "[2/3] Installing dependencies (pnpm install) ..."
cd "$SCRIPT_DIR/claude-code-router"

if ! command -v pnpm &> /dev/null; then
    echo "  pnpm not found, attempting to install..."
    npm install -g pnpm
fi

pnpm install .
echo "  ✓ Dependencies installed"

# 3. Start service
echo "[3/3] Starting Claude Code Router ..."
nohup pnpm run front > "$LOG_DIR/ccr.log" 2>&1 &
CCR_PID=$!
echo "$CCR_PID" > "$LOG_DIR/ccr.pid"

echo ""
echo "=== Deployment Complete ==="
echo "  PID:      $CCR_PID"
echo "  Port:     3456"
echo "  Log:      $LOG_DIR/ccr.log"
echo "  PID file: $LOG_DIR/ccr.pid"
echo ""
echo "  In Scout config.py use:"
echo "    server='local'  →  base_url='http://localhost:3456'"
echo "    model='venus,deepseek-v3.1-terminus'"
echo ""
echo "  Stop service: bash $SCRIPT_DIR/stop.bash"
