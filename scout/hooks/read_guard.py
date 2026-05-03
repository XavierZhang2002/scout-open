"""
Scout — Read Guard Hook (PreToolUse)

Addresses anti-patterns:
- Blind Reader: Agent reads large files without checking file size
- Stubborn Reader: Agent ignores needs_normalization=true

Event type: PreToolUse
Matcher: Read (also matches Grep)

Actual SDK callback signature:
    async def callback(input: PreToolUseHookInput, session_id: str | None, context: HookContext)
        -> SyncHookJSONOutput

Output mechanism:
- additionalContext: Injects context reminders before tool execution

Uses contextvars for concurrency-safe state isolation

"""

import contextvars
from typing import Any, Dict, Optional

from loguru import logger


# Maintains a cache of checked files (no repeat checks within the same session)
# Uses ContextVar for concurrency safety
_CACHE_SENTINEL: Dict[str, Dict[str, Any]] = {}  # Sentinel value, only used for default
_file_info_cache_var: contextvars.ContextVar[Dict[str, Dict[str, Any]]] = (
    contextvars.ContextVar("read_guard_file_info_cache", default=_CACHE_SENTINEL)
)


def _get_cache() -> Dict[str, Dict[str, Any]]:
    """Get the file info cache for the current task (lazy initialization)."""
    cache = _file_info_cache_var.get()
    if cache is _CACHE_SENTINEL:
        cache = {}
        _file_info_cache_var.set(cache)
    return cache


def reset_cache():
    """Reset the file info cache (for new session or testing)."""
    _file_info_cache_var.set({})


def mark_file_checked(file_path: str, info: Dict[str, Any]):
    """Manually mark a file as checked (for use after mcp_server's get_file_info call)."""
    cache = _get_cache()
    cache[file_path] = info


async def read_guard(
    hook_input: Dict[str, Any],
    session_id: Optional[str],
    context: Any,
) -> Dict[str, Any]:
    """PreToolUse Hook: Automatically checks file metadata before Read/Grep.

    Args:
        hook_input: PreToolUseHookInput — contains tool_name, tool_input, etc.
        session_id: Session ID
        context: HookContext — contains signal field

    Returns:
        SyncHookJSONOutput — empty dict (allow) or containing hookSpecificOutput (inject reminder)
    """
    tool_input = hook_input.get("tool_input", {})

    file_path = tool_input.get("file_path") or tool_input.get("filePath")
    if not file_path:
        return {}

    cache = _get_cache()

    # If the file has not been checked yet, automatically get info and cache it
    if file_path not in cache:
        try:
            from tools.file_tools import (
                get_file_metadata,
                check_long_lines,
                estimate_tokens_from_sample,
                count_tokens,
                LINE_MAX_LENGTH,
            )

            metadata = get_file_metadata(file_path)
            if metadata.get("exists"):
                needs_norm = check_long_lines(file_path, LINE_MAX_LENGTH)
                est_tokens = estimate_tokens_from_sample(
                    file_path, lambda t: count_tokens(t, "deepseek-chat")
                )
                cache[file_path] = {
                    "size_bytes": metadata["file_size_bytes"],
                    "est_tokens": est_tokens,
                    "needs_normalization": needs_norm,
                }
            else:
                return {}  # File does not exist, let Read report the error
        except Exception as e:
            logger.warning(f"[read_guard] Failed to check file info: {e}")
            return {}

    info = cache[file_path]
    messages = []

    # Check if normalization is needed
    if info.get("needs_normalization"):
        messages.append(
            "WARNING: This file contains excessively long lines (>2000 chars). "
            "You must call mcp__long_utils__normalize_document to preprocess it first, "
            "otherwise Grep/Read results may be inaccurate."
        )

    # Check if it's a large file but offset/limit is not used
    has_offset = tool_input.get("offset") is not None
    has_limit = tool_input.get("limit") is not None
    est_tokens = info.get("est_tokens", 0)

    if est_tokens > 30000 and not has_offset and not has_limit:
        messages.append(
            f"COST WARNING: This file is estimated at {est_tokens} tokens (>30k). "
            f"Consider using offset/limit parameters for chunked reading, or use Grep first to locate key line numbers."
        )

    if messages:
        combined = "[Read Guard] " + " | ".join(messages)
        logger.info(
            f"[read_guard] Injecting {len(messages)} warning(s) for {file_path}"
        )
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": combined,
            },
        }

    return {}
