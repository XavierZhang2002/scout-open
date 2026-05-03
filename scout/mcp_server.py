"""
Scout — MCP Tool Server


from claude_agent_sdk import tool, create_sdk_mcp_server
from typing import Dict, Any
import contextvars
import tempfile
import json
import os
import time

from loguru import logger

# Import tool implementations
from .tools.workspace_tools import (
    load_workspace,
    save_workspace,
    create_workspace,
    add_workspace_entry,
    compile_workspace_text,
    get_workspace_summary,
    search_workspace,
)
from .tools.file_tools import (
    get_file_metadata,
    check_long_lines,
    normalize_file_lines,
    estimate_tokens_from_sample,
    suggest_reading_strategy,
    count_tokens,
    LINE_MAX_LENGTH,
)
from .tools.llm_eval_tools import evaluate_sufficiency
from .tools.utils import track_tool_error


# ── Workspace Directory Management ────────────────────────────────────────
# Uses ContextVar for concurrency-safe workspace directory isolation.
# Each query_agent() call sets its own workspace directory via set_workspace_dir(),
# so different concurrent tasks do not interfere with each other.

WORKSPACE_ROOT = os.path.join(os.path.dirname(__file__), "workspace")
os.makedirs(WORKSPACE_ROOT, exist_ok=True)

# Default shared workspace directory (process-level, used as fallback when ContextVar is not set)
_DEFAULT_WORKSPACE_DIR = tempfile.mkdtemp(prefix="scout_ws_", dir=WORKSPACE_ROOT)

# Concurrency-safe workspace directory (each asyncio Task can set independently)
_workspace_dir_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "workspace_dir",
    default=_DEFAULT_WORKSPACE_DIR,
)

# Automatically tracks current workspace_id, eliminating the need for Agent to remember long IDs.
# Each asyncio Task has an independent workspace_id. When Agent calls workspace_update/view/search/evaluate
# and omits workspace_id, it automatically uses the most recently created/used workspace.
_current_workspace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_workspace_id",
    default="",
)


def set_workspace_dir(workspace_dir: str):
    """Set the workspace directory for the current task (concurrency-safe).

    Uses ContextVar so each asyncio Task has an independent workspace directory
    and they do not overwrite each other.
    """
    os.makedirs(workspace_dir, exist_ok=True)
    _workspace_dir_var.set(workspace_dir)


def get_workspace_dir() -> str:
    """Get the workspace directory for the current task (concurrency-safe)."""
    return _workspace_dir_var.get()


def _set_current_workspace_id(workspace_id: str):
    """Set the active workspace_id for the current task (concurrency-safe)."""
    _current_workspace_id_var.set(workspace_id)


def _get_current_workspace_id() -> str:
    """Get the active workspace_id for the current task (concurrency-safe)."""
    return _current_workspace_id_var.get()


def _resolve_workspace_id(args: Dict[str, Any], required: bool = True) -> str:
    """Resolve workspace_id: prefer the value from args, otherwise fall back to auto-tracked value.

    Args:
        args: Tool arguments dictionary
        required: Whether workspace_id is required (returns empty string or raises error if not found)

    Returns:
        Resolved workspace_id
    """
    workspace_id = args.get("workspace_id", "")
    if workspace_id:
        return workspace_id
    # Auto-fallback to the most recently used workspace
    auto_id = _get_current_workspace_id()
    if auto_id:
        logger.debug(f"[workspace] Auto-resolved workspace_id to {auto_id}")
        return auto_id
    if required:
        logger.warning(
            "[workspace] No workspace_id provided and no active workspace found"
        )
    return ""


# ── Error Handling ──────────────────────────────────────────────────────────


def handle_tool_error(tool_name: str, error: Exception) -> None:
    """Common method for handling tool errors.

    Args:
        tool_name: Name of the tool
        error: Exception object
    """
    error_msg = str(error)
    should_alert, session_id, query = track_tool_error(tool_name, error_msg)
    logger.error(
        f"{tool_name} failed, error: {error_msg}, "
        f"session_id: {session_id}, query: {query}, should_alert: {should_alert}"
    )
    if should_alert:
        _send_alert_message(tool_name, session_id, query, error_msg)


def _send_alert_message(
    tool_name: str,
    session_id: str,
    query: str,
    error_msg: str,
):
    """Send tool error alert message."""
    try:
        markdown_text = (
            f"#### {tool_name} tool error\n"
            f'> sessionId: <font color="comment">{session_id}</font>\n'
            f'> query: <font color="info">{query}</font>\n'
            f'> Error message: <font color="warning">{error_msg}</font>\n'
            f'> Trigger reason: <font color="warning">More than 3 errors per minute</font>\n'
        )
        logger.info("Sending tool error alert message:")
        logger.info(markdown_text)
    except Exception as e:
        logger.error(f"Failed to send tool error alert message: {str(e)}", exc_info=True)


# ══════════════════════════════════════════════════════════════════════════
#  MCP Tools Registration
# ══════════════════════════════════════════════════════════════════════════


# ── 1. get_file_info ────────────────────────


@tool(
    "get_file_info",
    """Get metadata about a file to help decide the reading strategy.

    Returns:
    - file_size_bytes: Size of the file in bytes
    - file_size_kb: Size of the file in kilobytes
    - estimated_tokens: Estimated number of tokens in the file
    - needs_normalization: Boolean indicating if the file contains excessively long lines.
    - reading_strategy: Recommended approach (full_read / grep_then_read / grep_only)

    Use this BEFORE attempting to read large files to plan your approach.
    """,
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the file"},
        },
        "required": ["file_path"],
    },
)
async def get_file_info(args: Dict[str, Any]):
    """Get file metadata and reading strategy recommendation."""
    try:
        file_path = args["file_path"]

        # Get file metadata
        metadata = get_file_metadata(file_path)
        if not metadata.get("exists", False):
            return {
                "content": [
                    {"type": "text", "text": f"Error: File {file_path} does not exist."}
                ],
                "is_error": True,
            }

        file_size = metadata["file_size_bytes"]

        # Check for long lines
        needs_normalization = check_long_lines(file_path, LINE_MAX_LENGTH)

        # Estimate tokens
        estimated_total_tokens = estimate_tokens_from_sample(file_path)

        # Generate reading strategy recommendation
        strategy = suggest_reading_strategy(estimated_total_tokens, needs_normalization)

        result = {
            "status": "success",
            "file_path": file_path,
            "file_size_bytes": file_size,
            "file_size_kb": metadata["file_size_kb"],
            "estimated_tokens": estimated_total_tokens,
            "needs_normalization": needs_normalization,
            "reading_strategy": strategy,
        }
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, ensure_ascii=False),
                }
            ],
            "metadata": {
                "file_path": file_path,
                "file_size": file_size,
                "estimated_tokens": estimated_total_tokens,
                "needs_normalization": needs_normalization,
                "approach": strategy.get("approach", ""),
            },
        }

    except Exception as e:
        handle_tool_error("get_file_info", e)
        return {
            "content": [
                {"type": "text", "text": f"Failed to get file info, error: {str(e)}"}
            ],
            "is_error": True,
        }


# ── 2. normalize_document ────────────────────────────────────────────────


@tool(
    "normalize_document",
    """Pre-process a document that has excessively long lines (e.g., minified code or single-line text files).

    This tool scans the file and splits lines longer than the threshold into smaller, natural segments (sentences).
    It overwrites the original file with the normalized content.

    Use this if 'Grep' returns huge chunks of text or if 'Read' is difficult due to lack of line breaks.

    Returns:
    - Confirmation that the file has been normalized in-place.
    """,
    {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the original file.",
            },
            "max_length": {
                "type": "integer",
                "default": LINE_MAX_LENGTH,
                "description": "Maximum characters per line before splitting.",
            },
        },
        "required": ["file_path"],
    },
)
async def normalize_document(args: Dict[str, Any]):
    """Normalize file by splitting long lines in-place."""
    try:
        source_path = args["file_path"]
        max_len = args.get("max_length", LINE_MAX_LENGTH)

        result = normalize_file_lines(source_path, max_len)

        if not result["success"]:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: {result.get('error', 'Unknown error')}",
                    }
                ],
                "is_error": True,
            }

        if not result["modified"]:
            return {"content": [{"type": "text", "text": result["message"]}]}

        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Successfully normalized file in-place.\n\n"
                        f"File: {source_path}\n\n"
                        f"You can now use 'Grep' and 'Read' on this file normally."
                    ),
                }
            ],
            "metadata": {"file_path": source_path, "status": "normalized"},
        }

    except Exception as e:
        handle_tool_error("normalize_document", e)
        return {
            "content": [
                {"type": "text", "text": f"Failed to normalize document: {str(e)}"}
            ],
            "is_error": True,
        }


# ── 3. workspace_update ───────────────────────


@tool(
    "workspace_update",
    """Manage the information workspace. Use this to store relevant information found during reading.

    Functionality:
    1. Create a new workspace (provide 'question', leave 'workspace_id' empty).
    2. Add new findings (provide 'workspace_id', 'content', action='append').
    3. Overwrite/Refine findings (provide 'workspace_id', 'content', action='replace').

    - tags: Categorize entries with labels for easy retrieval via workspace_search.
    - summary: One-line summary of the entry for quick review.
    - workspace_id is optional: if omitted, automatically uses the most recently created/used workspace.

    The workspace acts as your "notebook". Only information stored here will be available for the final evaluation.
    """,
    {
        "type": "object",
        "properties": {
            "workspace_id": {
                "type": "string",
                "description": "ID of the workspace. Leave empty to create a NEW workspace. If omitted for an existing workspace, auto-resolves to the most recently used workspace.",
            },
            "question": {
                "type": "string",
                "description": "The complete original query (including question, options, and requirements). Required only when creating a NEW workspace.",
            },
            "content": {
                "type": "string",
                "description": "The information to add or update.",
            },
            "source": {
                "type": "string",
                "description": "Source of the information (e.g., 'Grep: search_term', 'Read: lines 100-200').",
            },
            "action": {
                "type": "string",
                "enum": ["append", "replace"],
                "default": "append",
                "description": "'append' adds to existing info; 'replace' clears previous info and sets new content.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Labels for categorization and search (e.g., ['chapter3', 'theme', 'evidence']).",
            },
            "summary": {
                "type": "string",
                "description": "One-line summary of this entry for quick review.",
            },
        },
        "required": ["content", "source"],
    },
)
async def workspace_update_tool(args: Dict[str, Any]):
    """Create or update workspace content."""
    try:
        workspace_id = _resolve_workspace_id(args, required=False)
        question = args.get("question")
        content = args["content"]
        source = args["source"]
        action = args.get("action", "append")
        tags = args.get("tags", [])
        summary = args.get("summary", "")

        # 1. Create New Workspace
        if not workspace_id:
            if not question:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "Error: 'question' is required when creating a new workspace.",
                        }
                    ],
                    "is_error": True,
                }

            workspace_data = create_workspace(question)
            workspace_id = workspace_data["id"]
            _set_current_workspace_id(workspace_id)
        else:
            # 2. Load Existing Workspace
            try:
                workspace_data = load_workspace(get_workspace_dir(), workspace_id)
                _set_current_workspace_id(workspace_id)
            except FileNotFoundError:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error: Workspace {workspace_id} not found.",
                        }
                    ],
                    "is_error": True,
                }

        # 3. Apply Action (pass tags and summary)
        workspace_data, action_msg = add_workspace_entry(
            workspace_data,
            content,
            source,
            action,
            tags=tags,
            summary=summary,
        )

        # 4. Save
        save_workspace(get_workspace_dir(), workspace_id, workspace_data)

        # 5. Calculate Stats
        total_text = "\n".join([e["content"] for e in workspace_data["entries"]])
        token_count = count_tokens(total_text)

        # 6. Structured Output
        result = {
            "status": "success",
            "message": action_msg,
            "workspace_id": workspace_id,
            "total_entries": len(workspace_data["entries"]),
            "current_token_count": token_count,
        }

        return {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            "metadata": result,
        }

    except Exception as e:
        handle_tool_error("workspace_update", e)
        return {
            "content": [
                {"type": "text", "text": f"Failed to update workspace: {str(e)}"}
            ],
            "is_error": True,
        }


# ── 4. workspace_view ────────────────────────────────────────────────────


@tool(
    "workspace_view",
    """View the current contents of the workspace.

    Returns the full accumulated text and metadata. Use this to review what you have collected before evaluating.

    workspace_id is optional: if omitted, automatically uses the most recently created/used workspace.
    """,
    {
        "type": "object",
        "properties": {
            "workspace_id": {
                "type": "string",
                "description": "The workspace ID. If omitted, auto-resolves to the most recently used workspace.",
            },
        },
        "required": [],
    },
)
async def workspace_view_tool(args: Dict[str, Any]):
    """Read workspace content."""
    try:
        workspace_id = _resolve_workspace_id(args)
        workspace_data = load_workspace(get_workspace_dir(), workspace_id)

        # Compile content (includes tags/summary)
        compiled_text = compile_workspace_text(workspace_data)

        result = {
            "workspace_id": workspace_id,
            "question": workspace_data["question"],
            "entry_count": len(workspace_data["entries"]),
            "full_content": compiled_text,
        }

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, ensure_ascii=False),
                }
            ],
            "metadata": {
                "workspace_id": workspace_id,
                "token_count": count_tokens(compiled_text),
            },
        }

    except Exception as e:
        handle_tool_error("workspace_view", e)
        return {
            "content": [
                {"type": "text", "text": f"Failed to view workspace: {str(e)}"}
            ],
            "is_error": True,
        }


# ── 5. workspace_search ───────────────────────────────────


@tool(
    "workspace_search",
    """Search within workspace entries by keyword and/or tag.

    Use this when the workspace has many entries and you need to quickly find
    specific information without viewing the full workspace content.

    workspace_id is optional: if omitted, automatically uses the most recently created/used workspace.

    Returns matching entries with content previews.
    """,
    {
        "type": "object",
        "properties": {
            "workspace_id": {
                "type": "string",
                "description": "The workspace ID to search in. If omitted, auto-resolves to the most recently used workspace.",
            },
            "keyword": {
                "type": "string",
                "description": "Keyword to search for in entry content and summaries (case-insensitive).",
            },
            "tag": {
                "type": "string",
                "description": "Tag to filter entries by (exact match).",
            },
        },
        "required": [],
    },
)
async def workspace_search_tool(args: Dict[str, Any]):
    """Search workspace entries by keyword or tag."""
    try:
        workspace_id = _resolve_workspace_id(args)
        keyword = args.get("keyword", "")
        tag = args.get("tag", "")

        if not keyword and not tag:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Error: At least one of 'keyword' or 'tag' is required.",
                    }
                ],
                "is_error": True,
            }

        workspace_data = load_workspace(get_workspace_dir(), workspace_id)
        results = search_workspace(workspace_data, keyword=keyword, tag=tag)

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(results, indent=2, ensure_ascii=False),
                }
            ],
            "metadata": {
                "workspace_id": workspace_id,
                "match_count": results["match_count"],
            },
        }

    except FileNotFoundError:
        resolved_id = _resolve_workspace_id(args, required=False) or args.get(
            "workspace_id", ""
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error: Workspace {resolved_id} not found.",
                }
            ],
            "is_error": True,
        }
    except Exception as e:
        handle_tool_error("workspace_search", e)
        return {
            "content": [
                {"type": "text", "text": f"Failed to search workspace: {str(e)}"}
            ],
            "is_error": True,
        }


# ── 6. workspace_evaluate (fallback) ──────────────────────


@tool(
    "workspace_evaluate",
    """Evaluate if the collected information is sufficient to answer the question.

    This tool calls an external evaluator (LLM) to judge the workspace content.
    NOTE: When Evaluator SubAgent is enabled, prefer using the evaluator agent instead.

    CRITICAL: The evaluator looks ONLY at the workspace content. If the answer exists in the file but is not in the workspace, the result will be 'insufficient'.

    workspace_id is optional: if omitted, automatically uses the most recently created/used workspace.

    Returns:
    - is_sufficient: boolean
    - reasoning: why it is/isn't sufficient
    - missing_info: specific details to look for next
    """,
    {
        "type": "object",
        "properties": {
            "workspace_id": {
                "type": "string",
                "description": "The workspace ID to evaluate. If omitted, auto-resolves to the most recently used workspace.",
            },
        },
        "required": [],
    },
)
async def workspace_evaluate_tool(args: Dict[str, Any]):
    """Check sufficiency using external LLM (fallback)."""
    try:
        workspace_id = _resolve_workspace_id(args)
        workspace_data = load_workspace(get_workspace_dir(), workspace_id)

        question = workspace_data["question"]

        # Compile content for the evaluator
        compiled_text = ""
        for entry in workspace_data["entries"]:
            compiled_text += (
                f"Source: {entry['source']}\nContent: {entry['content']}\n\n"
            )

        if not compiled_text.strip():
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "is_sufficient": False,
                                "reasoning": "Workspace is empty.",
                                "missing_info": "All information.",
                            }
                        ),
                    }
                ],
                "metadata": {"is_sufficient": False},
            }

        # Call LLM evaluator
        evaluation = await evaluate_sufficiency(question, compiled_text)

        # Save evaluation result to workspace
        workspace_data.setdefault("evaluations", []).append(
            {"timestamp": time.time(), "result": evaluation}
        )
        save_workspace(get_workspace_dir(), workspace_id, workspace_data)

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(evaluation, indent=2, ensure_ascii=False),
                }
            ],
            "metadata": {
                "is_sufficient": evaluation["is_sufficient"],
                "confidence": evaluation.get("confidence", 0),
            },
        }

    except Exception as e:
        handle_tool_error("workspace_evaluate", e)
        return {
            "content": [{"type": "text", "text": f"Failed to evaluate: {str(e)}"}],
            "is_error": True,
        }


# ══════════════════════════════════════════════════════════════════════════
#  MCP Server Instantiation
# ══════════════════════════════════════════════════════════════════════════

# Tool registration list:
# - Removed count_tokens (merged into internal function)
# - Added workspace_search
# - Retained workspace_evaluate as fallback
long_utils = create_sdk_mcp_server(
    name="long_utils",
    version="3.0.0",
    tools=[
        get_file_info,
        normalize_document,
        workspace_update_tool,
        workspace_view_tool,
        workspace_search_tool,
        workspace_evaluate_tool,  # fallback
    ],
)
