"""Scout — Tools Module"""

from .workspace_tools import (
    load_workspace,
    save_workspace,
    create_workspace,
    add_workspace_entry,
    compile_workspace_text,
    get_workspace_summary,
    search_workspace,
)

from .file_tools import (
    get_file_metadata,
    check_long_lines,
    normalize_file_lines,
    estimate_tokens_from_sample,
    suggest_reading_strategy,
    count_tokens,
    LINE_MAX_LENGTH,
    SMALL_FILE_TOKEN_THRESHOLD,
    LARGE_FILE_TOKEN_THRESHOLD,
)

from .llm_eval_tools import evaluate_sufficiency
from .utils import (
    track_tool_error,
    set_current_session_context,
    get_current_session_context,
    reset_tool_error_history,
)
from .native_tools import glob_tool, grep_tool, read_tool, todo_write_tool

__all__ = [
    # workspace_tools
    "load_workspace",
    "save_workspace",
    "create_workspace",
    "add_workspace_entry",
    "compile_workspace_text",
    "get_workspace_summary",
    "search_workspace",
    # file_tools
    "get_file_metadata",
    "check_long_lines",
    "normalize_file_lines",
    "estimate_tokens_from_sample",
    "suggest_reading_strategy",
    "count_tokens",
    "LINE_MAX_LENGTH",
    "SMALL_FILE_TOKEN_THRESHOLD",
    "LARGE_FILE_TOKEN_THRESHOLD",
    # llm_eval_tools
    "evaluate_sufficiency",
    # utils
    "track_tool_error",
    "set_current_session_context",
    "get_current_session_context",
    "reset_tool_error_history",
    # native_tools
    "glob_tool",
    "grep_tool",
    "read_tool",
    "todo_write_tool",
]
