#!/usr/bin/env python3
"""
SCOUT Skill — Workspace Manager

Manages a JSON-based workspace for the SCOUT reading strategy.
The workspace stores information collected during document analysis,
enabling decoupled epistemic state tracking.

Usage:
    python3 workspace.py create --question "..." --cwd /path/to/docs
    python3 workspace.py append --content "..." --source "file:L100" [--tags t1,t2] [--summary "..."]
    python3 workspace.py view
    python3 workspace.py search --keyword "..." [--tag "..."]
    python3 workspace.py summary
    python3 workspace.py file-info --path /path/to/file
    python3 workspace.py normalize --path /path/to/file
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Constants ─────────────────────────────────────────────────────────────

WORKSPACE_DIR_NAME = ".scout-workspace"
WORKSPACE_FILE = "workspace.json"
LINE_MAX_LENGTH = 2000
SMALL_FILE_TOKEN_THRESHOLD = 30000
LARGE_FILE_TOKEN_THRESHOLD = 100000
CHARS_PER_TOKEN_ESTIMATE = 3.5  # rough estimate for mixed CJK/English


# ── Workspace Path Resolution ─────────────────────────────────────────────


def _resolve_workspace_dir(cwd: Optional[str] = None) -> Path:
    """Resolve workspace directory. Uses CWD env or argument."""
    base = cwd or os.environ.get("SCOUT_CWD", os.getcwd())
    ws_dir = Path(base) / WORKSPACE_DIR_NAME
    ws_dir.mkdir(parents=True, exist_ok=True)
    return ws_dir


def _workspace_path(cwd: Optional[str] = None) -> Path:
    """Full path to workspace.json."""
    return _resolve_workspace_dir(cwd) / WORKSPACE_FILE


# ── Workspace CRUD ────────────────────────────────────────────────────────


def create_workspace(question: str, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Create a new workspace."""
    ws_path = _workspace_path(cwd)

    # Generate unique ID
    q_hash = hashlib.md5(question.encode()).hexdigest()[:8]
    ts = int(time.time() * 1_000_000)
    workspace_id = f"{q_hash}_{ts}"

    data = {
        "id": workspace_id,
        "question": question,
        "created_at": time.time(),
        "updated_at": time.time(),
        "entries": [],
    }

    with open(ws_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return data


def load_workspace(cwd: Optional[str] = None) -> Dict[str, Any]:
    """Load existing workspace."""
    ws_path = _workspace_path(cwd)
    if not ws_path.exists():
        print("ERROR: No workspace found. Create one first with 'create' command.", file=sys.stderr)
        sys.exit(1)
    with open(ws_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_workspace(data: Dict[str, Any], cwd: Optional[str] = None):
    """Save workspace to disk."""
    ws_path = _workspace_path(cwd)
    data["updated_at"] = time.time()
    with open(ws_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def append_entry(
    content: str,
    source: str,
    tags: Optional[List[str]] = None,
    summary: str = "",
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """Append a new entry to the workspace."""
    data = load_workspace(cwd)
    entry = {
        "content": content,
        "source": source,
        "tags": tags or [],
        "summary": summary,
        "timestamp": time.time(),
    }
    data["entries"].append(entry)
    save_workspace(data, cwd)
    return data


def view_workspace(cwd: Optional[str] = None) -> str:
    """View workspace contents in formatted text."""
    data = load_workspace(cwd)
    lines = []
    lines.append(f"Question: {data['question']}")
    lines.append(f"Entries: {len(data['entries'])}")
    lines.append("=" * 60)

    for i, entry in enumerate(data["entries"]):
        header = f"\n--- Entry {i + 1} (Source: {entry['source']})"
        if entry.get("tags"):
            header += f" [Tags: {', '.join(entry['tags'])}]"
        header += " ---"
        lines.append(header)

        if entry.get("summary"):
            lines.append(f"Summary: {entry['summary']}")

        lines.append(entry["content"])

    return "\n".join(lines)


def search_workspace(
    keyword: str = "",
    tag: str = "",
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """Search workspace entries by keyword or tag."""
    data = load_workspace(cwd)
    keyword_lower = keyword.lower() if keyword else ""
    matches = []

    for i, entry in enumerate(data["entries"]):
        match = True

        if keyword_lower:
            content_lower = entry["content"].lower()
            summary_lower = entry.get("summary", "").lower()
            if keyword_lower not in content_lower and keyword_lower not in summary_lower:
                match = False

        if tag and tag not in entry.get("tags", []):
            match = False

        if match:
            content = entry["content"]
            preview = content[:200] + "..." if len(content) > 200 else content
            matches.append({
                "index": i + 1,
                "source": entry["source"],
                "summary": entry.get("summary", ""),
                "tags": entry.get("tags", []),
                "content_preview": preview,
            })

    return {
        "query": {"keyword": keyword, "tag": tag},
        "match_count": len(matches),
        "total_entries": len(data["entries"]),
        "matches": matches,
    }


def workspace_summary(cwd: Optional[str] = None) -> Dict[str, Any]:
    """Get workspace statistics."""
    data = load_workspace(cwd)
    total_chars = sum(len(e["content"]) for e in data["entries"])
    all_tags = set()
    for entry in data["entries"]:
        all_tags.update(entry.get("tags", []))

    return {
        "workspace_id": data["id"],
        "question": data["question"],
        "total_entries": len(data["entries"]),
        "total_chars": total_chars,
        "estimated_tokens": int(total_chars / CHARS_PER_TOKEN_ESTIMATE),
        "all_tags": sorted(all_tags),
        "created_at": data.get("created_at", 0),
        "updated_at": data.get("updated_at", 0),
    }


# ── File Tools ────────────────────────────────────────────────────────────


def file_info(file_path: str) -> Dict[str, Any]:
    """Get file metadata and reading strategy recommendation."""
    path = Path(file_path)

    if not path.exists():
        return {"error": f"File does not exist: {file_path}"}

    file_size = path.stat().st_size
    estimated_tokens = int(file_size / CHARS_PER_TOKEN_ESTIMATE)

    # Check for long lines
    needs_normalization = False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if len(line) > LINE_MAX_LENGTH:
                    needs_normalization = True
                    break
                if i >= 5000:
                    break
    except Exception:
        pass

    # Determine reading strategy
    if estimated_tokens < SMALL_FILE_TOKEN_THRESHOLD:
        approach = "full_read"
        recommendation = "File is small enough to Read entirely."
    elif estimated_tokens < LARGE_FILE_TOKEN_THRESHOLD:
        approach = "grep_then_read"
        recommendation = "Use Grep to locate key sections, then Read(offset, limit) for targeted reading."
    else:
        approach = "grep_only"
        recommendation = f"File is very large (~{estimated_tokens} tokens). Use only Grep for keyword search."

    warnings = []
    if needs_normalization:
        warnings.append("File contains lines >2000 chars. Run 'normalize' before Grep/Read.")

    return {
        "file_path": file_path,
        "file_size_bytes": file_size,
        "file_size_kb": round(file_size / 1024, 1),
        "estimated_tokens": estimated_tokens,
        "needs_normalization": needs_normalization,
        "reading_strategy": {
            "approach": approach,
            "recommendation": recommendation,
            "warnings": warnings,
        },
    }


def normalize_file(file_path: str) -> Dict[str, Any]:
    """Split excessively long lines in a file (in-place)."""
    path = Path(file_path)

    if not path.exists():
        return {"success": False, "error": f"File not found: {file_path}"}

    temp_path = str(path) + ".tmp_normalized"
    modified = False

    try:
        with (
            open(path, "r", encoding="utf-8", errors="replace") as f_in,
            open(temp_path, "w", encoding="utf-8") as f_out,
        ):
            for line in f_in:
                line = line.rstrip()
                if not line:
                    f_out.write("\n")
                    continue

                if len(line) <= LINE_MAX_LENGTH:
                    f_out.write(line + "\n")
                else:
                    modified = True
                    pos = 0
                    total = len(line)

                    while pos < total:
                        end = min(pos + LINE_MAX_LENGTH, total)
                        chunk = line[pos:end]

                        if end == total:
                            f_out.write(chunk + "\n")
                            break

                        # Find natural break point in last 20%
                        lookback = int(LINE_MAX_LENGTH * 0.2)
                        search_area = chunk[-lookback:]
                        split_offset = -1

                        # Priority 1: sentence endings
                        match = re.search(r"[.!?。？！](\s|$)", search_area)
                        if match:
                            split_offset = (len(chunk) - lookback) + match.end()
                        else:
                            # Priority 2: spaces/commas
                            match = re.search(r"[,\s]", search_area)
                            if match:
                                split_offset = (len(chunk) - lookback) + match.end()

                        if split_offset != -1:
                            actual_end = pos + split_offset
                            f_out.write(line[pos:actual_end].strip() + "\n")
                            pos = actual_end
                        else:
                            f_out.write(chunk + "\n")
                            pos += LINE_MAX_LENGTH

        if not modified:
            os.remove(temp_path)
            return {
                "success": True,
                "modified": False,
                "message": f"No lines exceed {LINE_MAX_LENGTH} chars. No normalization needed.",
            }

        shutil.move(temp_path, str(path))
        return {
            "success": True,
            "modified": True,
            "message": f"Normalized {file_path}. Long lines have been split.",
        }

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return {"success": False, "error": str(e)}


# ── CLI Entry Point ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="SCOUT Workspace Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # create
    p_create = subparsers.add_parser("create", help="Create a new workspace")
    p_create.add_argument("--question", "-q", required=True, help="The full question to research")
    p_create.add_argument("--cwd", help="Working directory (document root)")

    # append
    p_append = subparsers.add_parser("append", help="Append entry to workspace")
    p_append.add_argument("--content", "-c", required=True, help="Information content")
    p_append.add_argument("--source", "-s", required=True, help="Source (e.g., 'file.txt:L100-120')")
    p_append.add_argument("--tags", "-t", default="", help="Comma-separated tags")
    p_append.add_argument("--summary", default="", help="One-line summary")
    p_append.add_argument("--cwd", help="Working directory")

    # view
    p_view = subparsers.add_parser("view", help="View workspace contents")
    p_view.add_argument("--cwd", help="Working directory")

    # search
    p_search = subparsers.add_parser("search", help="Search workspace entries")
    p_search.add_argument("--keyword", "-k", default="", help="Search keyword")
    p_search.add_argument("--tag", default="", help="Filter by tag")
    p_search.add_argument("--cwd", help="Working directory")

    # summary
    p_summary = subparsers.add_parser("summary", help="Workspace statistics")
    p_summary.add_argument("--cwd", help="Working directory")

    # file-info
    p_fi = subparsers.add_parser("file-info", help="Get file metadata and reading strategy")
    p_fi.add_argument("--path", "-p", required=True, help="Path to file")

    # normalize
    p_norm = subparsers.add_parser("normalize", help="Normalize file (split long lines)")
    p_norm.add_argument("--path", "-p", required=True, help="Path to file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    if args.command == "create":
        data = create_workspace(args.question, args.cwd)
        result = {
            "status": "created",
            "workspace_id": data["id"],
            "question": data["question"],
            "path": str(_workspace_path(args.cwd)),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "append":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        data = append_entry(args.content, args.source, tags, args.summary, args.cwd)
        result = {
            "status": "appended",
            "total_entries": len(data["entries"]),
            "latest_source": args.source,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "view":
        output = view_workspace(args.cwd)
        print(output)

    elif args.command == "search":
        if not args.keyword and not args.tag:
            print("ERROR: At least one of --keyword or --tag is required.", file=sys.stderr)
            sys.exit(1)
        result = search_workspace(args.keyword, args.tag, args.cwd)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "summary":
        result = workspace_summary(args.cwd)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "file-info":
        result = file_info(args.path)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "normalize":
        result = normalize_file(args.path)
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
