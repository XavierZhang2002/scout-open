"""
Scout — Auto Record Reminder Hook (PostToolUse)

Addresses anti-pattern:
- Invisible Reader: Agent reads information but forgets to record it to workspace

Event type: PostToolUse
Matcher: Read|Grep

Actual SDK callback signature:
    async def callback(input: PostToolUseHookInput, session_id: str | None, context: HookContext)
        -> SyncHookJSONOutput

Output mechanism:
- additionalContext: Injects context reminders after tool execution

Uses contextvars for concurrency-safe state isolation

"""

import contextvars
from typing import Any, Dict, Optional

from loguru import logger


# Tracks whether workspace_update was called after the last Read/Grep
# Uses ContextVar for concurrency safety
_pending_record_var: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "auto_record_pending",
    default=False,
)


def reset_state():
    """Reset state (for new session or testing)."""
    _pending_record_var.set(False)


async def auto_record_post_hook(
    hook_input: Dict[str, Any],
    session_id: Optional[str],
    context: Any,
) -> Dict[str, Any]:
    """PostToolUse Hook: Injects a reminder after Read/Grep returns results.

    Args:
        hook_input: PostToolUseHookInput — contains tool_name, tool_input, tool_response
        session_id: Session ID
        context: HookContext

    Returns:
        SyncHookJSONOutput — empty dict (no action) or containing hookSpecificOutput (inject reminder)
    """
    tool_name = hook_input.get("tool_name", "")
    tool_response = hook_input.get("tool_response")

    # If this is a workspace_update call, clear the pending record flag
    if tool_name in ("mcp__long_utils__workspace_update", "workspace_update"):
        _pending_record_var.set(False)
        return {}

    # If it's Read or Grep, check if there are valid results
    if tool_name in ("Read", "Grep"):
        output_text = str(tool_response) if tool_response else ""

        # Check if output contains valid content (non-empty, not "No matches found")
        if (
            output_text
            and "No matches found" not in output_text
            and len(output_text) > 50
        ):
            _pending_record_var.set(True)
            logger.debug(
                f"[auto_record_reminder] Injecting reminder after {tool_name} "
                f"(output: {len(output_text)} chars)"
            )
            reminder = (
                f"[Auto Record Reminder] You just retrieved information via {tool_name}. "
                "If it contains content relevant to the question, please immediately call "
                "mcp__long_utils__workspace_update to record it. "
                "Information not recorded to the workspace will not be visible during evaluation."
            )
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": reminder,
                },
            }

    return {}
