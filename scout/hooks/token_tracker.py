"""
Scout — Token Tracker Hook (PostToolUse)

Function: Automatically tracks call counts and output sizes for each tool
Event type: PostToolUse
Matcher: None (matches all tools; matcher=None in SDK means match all)

Actual SDK callback signature:
    async def callback(input: PostToolUseHookInput, session_id: str | None, context: HookContext)
        -> SyncHookJSONOutput

Purposes:
- Performance monitoring
- Cost tracking
- Output statistics reporting

Uses contextvars for concurrency-safe state isolation

"""

import contextvars
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from loguru import logger


@dataclass
class HookTokenTracker:
    """Automatically tracks token consumption and call counts for each tool via Hooks."""

    tool_token_usage: Dict[str, int] = field(default_factory=dict)
    tool_call_count: Dict[str, int] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)

    def record(self, tool_name: str, output_size: int):
        """Record a single tool call."""
        self.tool_call_count[tool_name] = self.tool_call_count.get(tool_name, 0) + 1
        self.tool_token_usage[tool_name] = (
            self.tool_token_usage.get(tool_name, 0) + output_size
        )

    def summary(self) -> Dict[str, Any]:
        """Return a statistics summary."""
        elapsed = time.time() - self.start_time
        total_calls = sum(self.tool_call_count.values())
        total_output_chars = sum(self.tool_token_usage.values())

        return {
            "elapsed_seconds": round(elapsed, 2),
            "total_tool_calls": total_calls,
            "total_output_chars": total_output_chars,
            "tool_calls": dict(self.tool_call_count),
            "tool_output_chars": dict(self.tool_token_usage),
        }

    def reset(self):
        """Reset statistics (for new session or testing)."""
        self.tool_token_usage.clear()
        self.tool_call_count.clear()
        self.start_time = time.time()


# Uses ContextVar for concurrency-safe tracker isolation
# Each asyncio Task (query_agent call) has its own independent HookTokenTracker
_TRACKER_SENTINEL = HookTokenTracker()  # Default sentinel instance
_tracker_var: contextvars.ContextVar[HookTokenTracker] = contextvars.ContextVar(
    "token_tracker",
    default=_TRACKER_SENTINEL,
)


async def token_tracker_hook(
    hook_input: Dict[str, Any],
    session_id: Optional[str],
    context: Any,
) -> Dict[str, Any]:
    """PostToolUse Hook: Records the output size of each tool call.

    Matcher: None (matches all tools)

    Args:
        hook_input: PostToolUseHookInput — contains tool_name, tool_response, etc.
        session_id: Session ID
        context: HookContext

    Returns:
        SyncHookJSONOutput — empty dict (record only, does not intervene with tool behavior)
    """
    tracker = _tracker_var.get()
    tool_name = hook_input.get("tool_name", "unknown")
    tool_response = hook_input.get("tool_response")
    output_size = len(str(tool_response)) if tool_response else 0

    tracker.record(tool_name, output_size)
    logger.debug(
        f"[token_tracker] {tool_name}: {output_size} chars "
        f"(total calls: {tracker.tool_call_count.get(tool_name, 0)})"
    )
    return {}


def get_tracker() -> HookTokenTracker:
    """Get the tracker instance for the current task."""
    return _tracker_var.get()


def reset_tracker():
    """Reset the tracker for the current task (for new session or testing)."""
    _tracker_var.set(HookTokenTracker())
