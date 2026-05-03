"""
Scout — Permission Callback Module

Implements the canUseTool callback for runtime permission guards.

Four layers of protection:
- Layer 1: disallowed_tools (static blocklist — CLI may not enforce)
- Layer 2: allowed_tools (static allowlist — CLI may not enforce)
- Layer 3: canUseTool (runtime callback) <- This module (hard-coded blocklist + path safety)
- Layer 4: Hooks (behavior guards)

"""

import os
from typing import Any, Dict, Optional, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from config import ScoutConfig


def create_permission_callback(config: "ScoutConfig"):
    """Create a permission check callback.

    Args:
        config: ScoutConfig instance (for obtaining cwd and other security boundary parameters)

    Returns:
        Callback function with signature: (tool_name, tool_input, session_info) -> dict
    """

    # Hard-coded blocklist — even if disallowed_tools is not enforced by CLI, this will block
    # Reference: InfiniteBench analysis — Task sub-Agent short-circuits the three-phase loop,
    # causing kv_retrieval/math_find accuracy degradation
    _HARD_BLOCKED_TOOLS = {"Task"}

    def scout_permission_callback(
        tool_name: str,
        tool_input: Dict[str, Any],
        session_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Runtime permission guard.

        Responsibilities:
        0. Hard-coded tool blocklist: Block Task and other known harmful tools (in case CLI disallowed_tools doesn't take effect)
        1. Path safety: Ensure Read/Grep/Glob only access allowed directories
        2. MCP tool path check: Path safety for get_file_info / normalize_document
        3. Default allow for all other tool calls
        """
        # 0. Hard-coded tool blocklist
        if tool_name in _HARD_BLOCKED_TOOLS:
            logger.warning(
                f"Permission denied: {tool_name} is hard-blocked. "
                f"Sub-agents bypass the 3-phase reading loop and degrade accuracy."
            )
            return {
                "type": "deny",
                "message": (
                    f"Tool {tool_name} is disabled. "
                    "Please do not use sub-agents to execute tasks. Use Read/Grep/workspace_update and other tools directly to complete reading and analysis."
                ),
            }

        # 1. Native tool path safety check
        if tool_name in ("Read", "Grep", "Glob"):
            path = tool_input.get("file_path") or tool_input.get("path") or ""
            if path and not _is_safe_path(path, config.cwd):
                logger.warning(
                    f"Permission denied: {tool_name} tried to access {path} "
                    f"(allowed root: {config.cwd})"
                )
                return {
                    "type": "deny",
                    "message": f"Path violation: {path} is not within the allowed working directory {config.cwd}",
                }

        # 2. MCP tool path check — get_file_info
        if tool_name == "mcp__long_utils__get_file_info":
            file_path = tool_input.get("file_path", "")
            if file_path and not _is_safe_path(file_path, config.cwd):
                logger.warning(f"Permission denied: get_file_info for {file_path}")
                return {
                    "type": "deny",
                    "message": f"Path violation: {file_path}",
                }

        # 3. MCP tool path check — normalize_document
        if tool_name == "mcp__long_utils__normalize_document":
            file_path = tool_input.get("file_path", "")
            if file_path and not _is_safe_path(file_path, config.cwd):
                logger.warning(f"Permission denied: normalize_document for {file_path}")
                return {
                    "type": "deny",
                    "message": f"Not allowed to normalize files outside the working directory: {file_path}",
                }

        # 4. Default allow
        return {"type": "allow"}

    return scout_permission_callback


def _is_safe_path(path: str, allowed_root: str) -> bool:
    """Check if a path is within the allowed directory.

    Args:
        path: Path to check
        allowed_root: Allowed root directory

    Returns:
        bool: True indicates the path is safe
    """
    if not path:
        return True  # Empty path is handled by the tool itself

    if not allowed_root:
        return True  # Allow all paths when no working directory restriction is set

    try:
        real_path = os.path.realpath(path)
        real_root = os.path.realpath(allowed_root)
        return real_path.startswith(real_root)
    except (OSError, ValueError):
        return False
