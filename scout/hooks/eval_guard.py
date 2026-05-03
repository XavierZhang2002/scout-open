"""
Scout — Eval Guard Hook (PostToolUse + Stop)

Addresses anti-pattern:
- Premature Guesser: Agent answers directly without calling workspace_evaluate

Contains three Hook callbacks:
1. track_evaluate (PostToolUse): Tracks whether workspace_evaluate has been called
2. track_reading_tools (PostToolUse): Tracks whether reading/gathering tools were used
3. eval_guard_stop (Stop): Prevents stopping without evaluation

Actual SDK callback signature:
    async def callback(input: HookInput, session_id: str | None, context: HookContext)
        -> SyncHookJSONOutput

Output mechanism:
- PostToolUse: empty dict (only records state)
- Stop: continue_=True + stopReason (blocks stopping and injects reminder)

SDK limitation note:
  Stop hook's continue_=True may not be reliably executed. The root cause is a race condition
  within the SDK: after the CLI sends a Stop hook_callback request, it may send a
  ResultMessage before receiving the SDK response, causing stream_input to close stdin,
  preventing the hook response from being delivered.
  Therefore, eval_guard primarily serves as a monitoring/logging mechanism, not a hard block.
  Mandatory evaluation behavior should be ensured via the system prompt (three-phase strategy: PLAN -> GATHER -> VERIFY).

Uses contextvars for concurrency-safe state isolation

"""

import contextvars
from typing import Any, Dict, Optional, Set

from loguru import logger


# ── State Tracking ──────────────────────────────────────────────────────────
# Uses ContextVar for concurrency safety

# Tracks whether workspace_evaluate has been called
_has_evaluated_var: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "eval_guard_has_evaluated",
    default=False,
)

# Tracks whether reading/gathering tools have been used (indicates a long-text task requiring evaluation)
_has_used_reading_tools_var: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "eval_guard_has_used_reading_tools",
    default=False,
)

# Set of tools requiring evaluation (using these tools means the Agent is performing a long-text reading task)
_READING_TOOLS: Set[str] = {
    "Read",
    "Grep",
    "Glob",
    "mcp__long_utils__normalize_document",
    "mcp__long_utils__get_file_info",
    "mcp__long_utils__workspace_update",
    "mcp__long_utils__workspace_view",
    "normalize_document",
    "get_file_info",
    "workspace_update",
    "workspace_view",
}


def reset_state():
    """Reset state (for new session or testing)."""
    _has_evaluated_var.set(False)
    _has_used_reading_tools_var.set(False)


def has_evaluated() -> bool:
    """Query whether evaluation has been called."""
    return _has_evaluated_var.get()


def has_used_reading_tools() -> bool:
    """Query whether reading/gathering tools have been used."""
    return _has_used_reading_tools_var.get()


# ── PostToolUse Hooks ─────────────────────────────────────────────────────


async def track_evaluate(
    hook_input: Dict[str, Any],
    session_id: Optional[str],
    context: Any,
) -> Dict[str, Any]:
    """PostToolUse Hook: Tracks whether workspace_evaluate / evaluator has been called.

    Matcher: mcp__long_utils__workspace_evaluate|evaluator

    Args:
        hook_input: PostToolUseHookInput — contains tool_name, tool_input, tool_response
        session_id: Session ID
        context: HookContext

    Returns:
        SyncHookJSONOutput — empty dict (record only, no intervention)
    """
    tool_name = hook_input.get("tool_name", "")
    if tool_name in (
        "mcp__long_utils__workspace_evaluate",
        "workspace_evaluate",
        "evaluator",
    ):
        _has_evaluated_var.set(True)
        logger.info("[eval_guard] workspace_evaluate has been called")

    return {}


async def track_reading_tools(
    hook_input: Dict[str, Any],
    session_id: Optional[str],
    context: Any,
) -> Dict[str, Any]:
    """PostToolUse Hook: Tracks whether reading/gathering tools have been used.

    Matcher: None (matches all tools, filters internally)

    When the Agent uses Read/Grep/Glob or MCP reading tools, it is flagged as a
    long-text reading task, and evaluation is required before stopping. If the Agent
    never uses these tools (e.g., for simple calculation problems), it is allowed to
    stop directly.

    Args:
        hook_input: PostToolUseHookInput
        session_id: Session ID
        context: HookContext

    Returns:
        SyncHookJSONOutput — empty dict (record only, no intervention)
    """
    tool_name = hook_input.get("tool_name", "")
    if tool_name in _READING_TOOLS:
        if not _has_used_reading_tools_var.get():
            _has_used_reading_tools_var.set(True)
            logger.info(
                f"[eval_guard] Reading tool used: {tool_name}, evaluation will be required"
            )

    return {}


# ── Stop Hook ─────────────────────────────────────────────────────────────


async def eval_guard_stop(
    hook_input: Dict[str, Any],
    session_id: Optional[str],
    context: Any,
) -> Dict[str, Any]:
    """Stop Hook: Prevents stopping without evaluation.

    Logic:
    - If the Agent has not used reading tools (simple problem), allow stopping
    - If the Agent used reading tools but didn't call workspace_evaluate, return continue_=True
    - If workspace_evaluate has been called, allow stopping

    Note: continue_=True may not reliably block stopping due to SDK race conditions.
    This hook primarily serves for logging/monitoring; actual evaluation enforcement
    is guaranteed by the system prompt.

    Args:
        hook_input: StopHookInput — contains stop_hook_active, etc.
        session_id: Session ID
        context: HookContext

    Returns:
        SyncHookJSONOutput — empty dict (allow) or continue_=True (attempt to block stop)
    """
    # Simple problem: no reading tools used, no evaluation needed
    if not _has_used_reading_tools_var.get():
        logger.debug("[eval_guard] No reading tools used, allowing stop (simple query)")
        return {}

    # Long-text task but not evaluated
    if not _has_evaluated_var.get():
        logger.warning(
            "[eval_guard] Agent used reading tools but stopping without evaluation. "
            "Attempting to block stop (may not succeed due to SDK race condition)."
        )
        return {
            "continue_": True,
            "stopReason": (
                "[Eval Guard] You used reading tools but have not yet called "
                "mcp__long_utils__workspace_evaluate to verify information sufficiency. "
                "Please call workspace_evaluate to assess the completeness of collected information "
                "before outputting the final answer."
            ),
        }

    # Already evaluated, allow stopping
    logger.debug("[eval_guard] Evaluation completed, allowing stop")
    return {}
