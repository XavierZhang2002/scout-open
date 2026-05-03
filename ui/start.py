#!/usr/bin/env python3
"""
Scout UI — Uvicorn Launch Script

Usage:
    # Default (port 8080, all interfaces)
    python -m ui.start

    # Or directly
    cd Scout/ui && python start.py

    # Custom port
    python start.py --port 9000

    # Development mode (auto-reload)
    python start.py --reload
"""

import argparse
import os
import sys

# Ensure project root is in Python path (for `from scout.xxx` imports)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def main():
    """Parse args and launch uvicorn server."""
    parser = argparse.ArgumentParser(description="Scout Agent UI Server")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)",
    )

    args = parser.parse_args()

    import uvicorn

    print(f"Starting Scout Agent UI on http://{args.host}:{args.port}")
    print(f"  Static files: {os.path.join(SCRIPT_DIR, 'static')}")
    print(f"  Project root: {PROJECT_ROOT}")
    print()

    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
        log_level="info",
    )


if __name__ == "__main__":
    main()
