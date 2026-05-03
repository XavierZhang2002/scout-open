"""
Scout — Tool Utility Functions

- Only retained active code: track_tool_error, context variables
- Removed all commented-out COS, Polaris, and other legacy code
- Simplified structure

"""

import time
from typing import Dict, List, Tuple
import contextvars

from loguru import logger


# ── Context Variables (for passing session information) ─────────────────────

current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_session_id", default=""
)
current_query: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_query", default=""
)


# ── Tool Error Tracking ─────────────────────────────────────────────────────

_tool_error_history: Dict[str, List[Tuple[float, str]]] = {}


def track_tool_error(tool_name: str, error_msg: str) -> Tuple[bool, str, str]:
    """Track tool errors; trigger alert if errors are frequent in a short period.

    Args:
        tool_name: Name of the tool
        error_msg: Error message

    Returns:
        tuple: (whether alert is needed, session_id, query)
    """
    current_time = time.time()

    session_id = current_session_id.get("")
    query = current_query.get("")

    if tool_name not in _tool_error_history:
        _tool_error_history[tool_name] = []

    error_history = _tool_error_history[tool_name]

    # Clean up error records older than 5 minutes
    error_history[:] = [
        (timestamp, msg)
        for timestamp, msg in error_history
        if current_time - timestamp < 300
    ]
    logger.debug(f"[error_tracker] {tool_name}: {len(error_history)} recent errors")

    # Add current error
    error_history.append((current_time, error_msg))

    # Check error count within 1 minute
    recent_errors = [
        timestamp for timestamp, _ in error_history if current_time - timestamp < 60
    ]

    should_alert = len(recent_errors) > 1

    if should_alert:
        logger.warning(
            f"Tool {tool_name} has {len(recent_errors)} errors in 1 minute, "
            f"triggering alert (session_id: {session_id}, query: {query[:50]}...)"
        )

    return should_alert, session_id, query


def set_current_session_context(session_id: str, query: str):
    """Set the current session context (for SessionManager use)."""
    current_session_id.set(session_id)
    current_query.set(query)


def get_current_session_context() -> Tuple[str, str]:
    """Get the current session context."""
    return current_session_id.get(""), current_query.get("")


def reset_tool_error_history():
    """Reset error history (for testing)."""
    _tool_error_history.clear()
