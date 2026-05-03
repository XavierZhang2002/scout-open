"""
Scout — Native Tool Implementations

Contains: Glob, Grep, Read, TodoWrite

Agent calls these functions via SDK native tools.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from loguru import logger
from glob import glob as python_glob


# ═══════════════════════════════════════════════════════════════════════════
# Glob Tool
# ═══════════════════════════════════════════════════════════════════════════


def glob_tool(pattern: str, path: Optional[str] = None) -> Dict[str, Any]:
    """Execute glob file search.

    Args:
        pattern: Glob pattern (e.g., "**/*.py", "*.txt")
        path: Search directory; uses current working directory if not specified

    Returns:
        dict: Contains success, files, count, message
    """
    try:
        if path:
            search_dir = os.path.abspath(path)
            if not os.path.exists(search_dir):
                return {
                    "success": False,
                    "error": f"Directory does not exist: {path}",
                    "files": [],
                    "count": 0,
                }
            if not os.path.isdir(search_dir):
                return {
                    "success": False,
                    "error": f"Path is not a directory: {path}",
                    "files": [],
                    "count": 0,
                }
        else:
            search_dir = os.getcwd()

        original_cwd = os.getcwd()
        try:
            os.chdir(search_dir)
            matches = python_glob(pattern, recursive=True)
            file_matches = [m for m in matches if os.path.isfile(m)]
            absolute_paths = [
                os.path.abspath(os.path.join(search_dir, m)) for m in file_matches
            ]
            files_with_mtime = [(f, os.path.getmtime(f)) for f in absolute_paths]
            files_with_mtime.sort(key=lambda x: x[1], reverse=True)
            sorted_files = [f[0] for f in files_with_mtime]
        finally:
            os.chdir(original_cwd)

        count = len(sorted_files)
        message = f"Found {count} file(s) matching pattern '{pattern}'"
        if path:
            message += f" in directory '{path}'"

        return {
            "success": True,
            "files": sorted_files,
            "count": count,
            "message": message,
        }

    except Exception as e:
        logger.error(f"Glob tool error: {str(e)}")
        return {"success": False, "error": str(e), "files": [], "count": 0}


# ═══════════════════════════════════════════════════════════════════════════
# Grep Tool
# ═══════════════════════════════════════════════════════════════════════════


def _is_command_available(command: str) -> bool:
    """Check if a system command is available."""
    try:
        if os.name == "nt":
            result = subprocess.run(["where", command], capture_output=True, text=True)
        else:
            result = subprocess.run(["which", command], capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False


def _run_ripgrep(
    pattern: str,
    search_path: str,
    glob: Optional[str] = None,
    output_mode: str = "files_with_matches",
    case_insensitive: bool = True,
    context_before: int = 0,
    context_after: int = 0,
    show_line_numbers: bool = True,
    multiline: bool = False,
) -> Tuple[bool, str, str]:
    """Run ripgrep command."""
    cmd = ["rg"]

    if case_insensitive:
        cmd.append("-i")
    if multiline:
        cmd.extend(["-U", "--multiline-dotall"])

    if output_mode == "files_with_matches":
        cmd.append("-l")
    elif output_mode == "count":
        cmd.append("-c")
    else:
        if show_line_numbers:
            cmd.append("-n")
        if context_before > 0:
            cmd.extend(["-B", str(context_before)])
        if context_after > 0:
            cmd.extend(["-A", str(context_after)])

    if glob:
        cmd.extend(["-g", glob])

    cmd.append(pattern)
    cmd.append(search_path)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return True, result.stdout, ""
        elif result.returncode == 1:
            return True, "", "No matches found"
        else:
            return False, "", result.stderr or "Unknown error"
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def _run_system_grep(
    pattern: str,
    search_path: str,
    glob: Optional[str] = None,
    case_insensitive: bool = True,
) -> Tuple[bool, str, str]:
    """Run system grep command (fallback)."""
    cmd = ["grep", "-r", "-n", "-H", "-E"]

    if case_insensitive:
        cmd.append("-i")

    for exclude_dir in [".git", "__pycache__", "node_modules", ".venv", "venv"]:
        cmd.append(f"--exclude-dir={exclude_dir}")

    if glob:
        cmd.append(f"--include={glob}")

    cmd.append(pattern)
    cmd.append(search_path)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return True, result.stdout, ""
        elif result.returncode == 1:
            return True, "", "No matches found"
        else:
            return False, "", result.stderr or "Unknown error"
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def _parse_grep_output(
    output: str,
    output_mode: str,
    head_limit: Optional[int] = None,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Parse grep output into structured format."""
    if not output:
        return []

    lines = output.strip().split("\n")

    if offset > 0:
        lines = lines[offset:]
    if head_limit is not None:
        lines = lines[:head_limit]

    results = []

    if output_mode == "files_with_matches":
        for line in lines:
            if line:
                results.append({"file": line.strip()})

    elif output_mode == "count":
        for line in lines:
            if ":" in line:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    results.append(
                        {
                            "file": parts[0].strip(),
                            "count": int(parts[1].strip())
                            if parts[1].strip().isdigit()
                            else 0,
                        }
                    )

    else:  # content mode
        for line in lines:
            if line and ":" in line:
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    results.append(
                        {
                            "file": parts[0].strip(),
                            "line_number": int(parts[1].strip())
                            if parts[1].strip().isdigit()
                            else 0,
                            "content": parts[2],
                        }
                    )

    return results


def grep_tool(
    pattern: str,
    path: Optional[str] = None,
    glob: Optional[str] = None,
    output_mode: str = "files_with_matches",
    case_insensitive: bool = True,
    context_before: int = 0,
    context_after: int = 0,
    show_line_numbers: bool = True,
    head_limit: Optional[int] = None,
    offset: int = 0,
    multiline: bool = False,
    file_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute grep regex search.

    Args:
        pattern: Regex pattern
        path: Search directory
        glob: File filter pattern (e.g., "*.py")
        output_mode: "content", "files_with_matches", or "count"
        case_insensitive: Whether to ignore case
        context_before: Number of context lines before match
        context_after: Number of context lines after match
        show_line_numbers: Whether to show line numbers
        head_limit: Limit output line count
        offset: Skip first N results
        multiline: Whether to enable multiline matching
        file_type: File type filter (e.g., "py", "js")

    Returns:
        dict: Search results
    """
    try:
        if path:
            search_path = os.path.abspath(path)
            if not os.path.exists(search_path):
                return {
                    "success": False,
                    "error": f"Path does not exist: {path}",
                    "results": [],
                }
        else:
            search_path = os.getcwd()

        if file_type and not glob:
            glob = f"*.{file_type}"

        has_rg = _is_command_available("rg")

        if has_rg:
            success, output, error = _run_ripgrep(
                pattern,
                search_path,
                glob,
                output_mode,
                case_insensitive,
                context_before,
                context_after,
                show_line_numbers,
                multiline,
            )
            strategy = "ripgrep"
        else:
            has_grep = _is_command_available("grep")
            if has_grep:
                success, output, error = _run_system_grep(
                    pattern,
                    search_path,
                    glob,
                    case_insensitive,
                )
                strategy = "system grep"
                output_mode = "content"
            else:
                return {
                    "success": False,
                    "error": "Neither ripgrep (rg) nor grep is available on this system",
                    "results": [],
                }

        if not success:
            return {
                "success": False,
                "error": error,
                "results": [],
                "strategy": strategy,
            }

        results = _parse_grep_output(output, output_mode, head_limit, offset)

        message = f"Found {len(results)} match(es) for pattern '{pattern}'"
        if path:
            message += f" in '{path}'"
        if glob:
            message += f" (filtered by '{glob}')"

        return {
            "success": True,
            "results": results,
            "count": len(results),
            "message": message,
            "strategy": strategy,
        }

    except Exception as e:
        logger.error(f"Grep tool error: {str(e)}")
        return {"success": False, "error": str(e), "results": []}


# ═══════════════════════════════════════════════════════════════════════════
# Read Tool
# ═══════════════════════════════════════════════════════════════════════════


def read_tool(
    file_path: str,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Read file content (optionally specify line range).

    Args:
        file_path: Absolute file path
        offset: Starting line number (0-indexed)
        limit: Number of lines to read

    Returns:
        dict: Contains success, content, total_lines, lines_shown, truncated, message
    """
    max_line_length = 5000
    default_limit = 2000

    try:
        abs_path = os.path.abspath(file_path)

        if not os.path.exists(abs_path):
            return {
                "success": False,
                "error": f"File does not exist: {file_path}",
                "content": "",
            }

        if not os.path.isfile(abs_path):
            return {
                "success": False,
                "error": f"Path is not a file: {file_path}",
                "content": "",
            }

        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return {
                "success": False,
                "error": f"Error reading file: {str(e)}",
                "content": "",
            }

        total_lines = len(lines)

        start_line = offset if offset is not None else 0
        if limit is not None:
            end_line = min(start_line + limit, total_lines)
        else:
            end_line = min(start_line + default_limit, total_lines)

        selected_lines = lines[start_line:end_line]

        formatted_lines = []
        for i, line in enumerate(selected_lines, start=start_line + 1):
            line = line.rstrip("\n\r")
            if len(line) > max_line_length:
                line = line[:max_line_length] + "... [line truncated]"
            if line.strip():
                formatted_lines.append(f"  {i}→{line}")
            else:
                formatted_lines.append(f"  {i}→")

        content = "\n".join(formatted_lines)

        truncated = end_line < total_lines or any(
            len(line.rstrip("\n\r")) > max_line_length for line in selected_lines
        )

        if truncated:
            message = (
                f"File: {file_path}\n"
                f"Showing lines {start_line + 1}-{end_line} of {total_lines} total lines.\n"
                f"To read more, use offset: {end_line}"
            )
        else:
            message = f"File: {file_path}\nShowing all {total_lines} lines."

        return {
            "success": True,
            "content": content,
            "total_lines": total_lines,
            "lines_shown": (start_line + 1, end_line),
            "truncated": truncated,
            "message": message,
            "file_path": abs_path,
        }

    except Exception as e:
        logger.error(f"Read tool error: {str(e)}")
        return {"success": False, "error": str(e), "content": ""}


# ═══════════════════════════════════════════════════════════════════════════
# TodoWrite Tool
# ═══════════════════════════════════════════════════════════════════════════


def todo_write_tool(todos: List[Dict[str, str]]) -> Dict[str, Any]:
    """Update the task list.

    Args:
        todos: Task list, each item contains:
            - content: Task description
            - status: "pending", "in_progress", or "completed"
            - activeForm: Active form description (e.g., "Running tests")

    Returns:
        dict: Contains success, todos, message
    """
    try:
        valid_statuses = {"pending", "in_progress", "completed"}

        for i, todo in enumerate(todos):
            if not isinstance(todo, dict):
                return {"success": False, "error": f"Todo item {i} is not a dictionary"}

            if (
                "content" not in todo
                or "status" not in todo
                or "activeForm" not in todo
            ):
                return {
                    "success": False,
                    "error": f"Todo item {i} missing required fields (content, status, activeForm)",
                }

            if todo["status"] not in valid_statuses:
                return {
                    "success": False,
                    "error": f"Todo item {i} has invalid status: {todo['status']}",
                }

            if not todo["content"].strip():
                return {"success": False, "error": f"Todo item {i} has empty content"}

            if not todo["activeForm"].strip():
                return {
                    "success": False,
                    "error": f"Todo item {i} has empty activeForm",
                }

        in_progress_count = sum(1 for todo in todos if todo["status"] == "in_progress")
        if in_progress_count > 1:
            return {
                "success": False,
                "error": f"Only one task can be in_progress at a time, found {in_progress_count}",
            }

        if not todos:
            message = "Todo list cleared."
        else:
            todo_strings = []
            for i, todo in enumerate(todos, 1):
                status_symbol = {
                    "pending": "[ ]",
                    "in_progress": "[>]",
                    "completed": "[x]",
                }.get(todo["status"], "[?]")
                todo_strings.append(
                    f"{i}. {status_symbol} [{todo['status']}] {todo['content']}"
                )

            message = f"Updated todo list ({len(todos)} items):\n" + "\n".join(
                todo_strings
            )

        return {
            "success": True,
            "todos": todos,
            "count": len(todos),
            "message": message,
        }

    except Exception as e:
        logger.error(f"TodoWrite tool error: {str(e)}")
        return {"success": False, "error": str(e)}


# ── Tool Registry ────────────────────────────────────────────────────────

TOOLS = {
    "Glob": glob_tool,
    "Grep": grep_tool,
    "Read": read_tool,
    "TodoWrite": todo_write_tool,
}
