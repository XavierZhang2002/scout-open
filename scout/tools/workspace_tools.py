"""
Scout — Workspace Management Tools

- add_workspace_entry: Added tags, summary parameters
- Added search_workspace: In-workspace keyword/tag search
- compile_workspace_text: Output format includes tags/summary

"""

import os
import json
import time
import hashlib
from typing import Dict, Any, List, Optional
from pathlib import Path

from loguru import logger


# ── Workspace Path ────────────────────────────────────────────────────────


def get_workspace_path(workspace_dir: str, workspace_id: str) -> Path:
    """Get the workspace file path."""
    return Path(workspace_dir) / f"workspace_{workspace_id}.json"


# ── Load / Save ──────────────────────────────────────────────────────────


def load_workspace(workspace_dir: str, workspace_id: str) -> Dict[str, Any]:
    """Load workspace data from file."""
    path = get_workspace_path(workspace_dir, workspace_id)
    if not path.exists():
        raise FileNotFoundError(f"Workspace {workspace_id} not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_workspace(workspace_dir: str, workspace_id: str, data: Dict[str, Any]):
    """Save workspace data to file."""
    os.makedirs(workspace_dir, exist_ok=True)
    path = get_workspace_path(workspace_dir, workspace_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Create Workspace ────────────────────────────────────────────────────────


def create_workspace(question: str) -> Dict[str, Any]:
    """Create a new workspace (with unique ID)."""
    question_hash = hashlib.md5(question.encode()).hexdigest()[:8]
    timestamp_us = int(time.time() * 1_000_000)
    workspace_id = f"{question_hash}_{timestamp_us}"

    workspace_data = {
        "id": workspace_id,
        "question": question,
        "created_at": time.time(),
        "updated_at": time.time(),
        "entries": [],
    }

    return workspace_data


# ── Add Entry ──────────────────────────────────────────────


def add_workspace_entry(
    workspace_data: Dict[str, Any],
    content: str,
    source: str,
    action: str = "append",
    tags: Optional[List[str]] = None,
    summary: Optional[str] = None,
) -> tuple[Dict[str, Any], str]:
    """Add or replace a workspace entry.

    - tags: Entry tags (e.g., ["chapter3", "theme", "comparison"]), for categorization and search
    - summary: Entry summary (one-line), for quick review

    Args:
        workspace_data: Workspace data
        content: Entry content
        source: Source (e.g., file path + line number)
        action: "append" or "replace"
        tags: Entry tag list
        summary: One-line summary

    Returns:
        tuple: (updated workspace data, action message)
    """
    new_entry = {
        "content": content,
        "source": source,
        "timestamp": time.time(),
        "tags": tags or [],
        "summary": summary or "",
    }

    if action == "replace":
        workspace_data["entries"] = [new_entry]
        action_msg = "Workspace cleared and new entry added."
    else:
        workspace_data["entries"].append(new_entry)
        action_msg = f"Entry appended. Total: {len(workspace_data['entries'])} entries."

    workspace_data["updated_at"] = time.time()

    return workspace_data, action_msg


# ── Compile Workspace Text ────────────────────────────────────────────────


def compile_workspace_text(workspace_data: Dict[str, Any]) -> str:
    """Compile all entries into a single text.

    Output includes tags and summary information.
    """
    compiled_text = ""
    for idx, entry in enumerate(workspace_data["entries"]):
        header = f"\n--- Entry {idx + 1} (Source: {entry['source']})"

        # Display tags
        tags = entry.get("tags", [])
        if tags:
            header += f" [Tags: {', '.join(tags)}]"

        header += " ---\n"
        compiled_text += header

        # Display summary
        summary = entry.get("summary", "")
        if summary:
            compiled_text += f"Summary: {summary}\n"

        compiled_text += entry["content"] + "\n"

    return compiled_text


# ── Workspace Summary Statistics ────────────────────────────────────────────


def get_workspace_summary(workspace_data: Dict[str, Any]) -> Dict[str, Any]:
    """Get workspace statistics summary."""
    total_text = "\n".join([e["content"] for e in workspace_data["entries"]])

    # Count all used tags
    all_tags = set()
    for entry in workspace_data["entries"]:
        all_tags.update(entry.get("tags", []))

    return {
        "workspace_id": workspace_data["id"],
        "question": workspace_data.get("question", ""),
        "total_entries": len(workspace_data["entries"]),
        "created_at": workspace_data.get("created_at", 0),
        "updated_at": workspace_data.get("updated_at", 0),
        "total_text_length": len(total_text),
        "all_tags": sorted(all_tags),
    }


# ── In-Workspace Search ─────────────────────────────────────


def search_workspace(
    workspace_data: Dict[str, Any],
    keyword: str = "",
    tag: str = "",
    content_preview_length: int = 200,
) -> Dict[str, Any]:
    """Search workspace entries by keyword or tag.

    When the workspace has accumulated many entries, the Agent can use this function
    to quickly retrieve existing notes, avoiding duplicate records.

    Args:
        workspace_data: Workspace data
        keyword: Search keyword (searches in content and summary, case-insensitive)
        tag: Filter by tag
        content_preview_length: Content preview length

    Returns:
        dict: Contains list of matching results

    """
    keyword_lower = keyword.lower() if keyword else ""
    matches = []

    for i, entry in enumerate(workspace_data["entries"]):
        match = True

        # Keyword filter
        if keyword_lower:
            content_lower = entry["content"].lower()
            summary_lower = entry.get("summary", "").lower()
            if (
                keyword_lower not in content_lower
                and keyword_lower not in summary_lower
            ):
                match = False

        # Tag filter
        if tag and tag not in entry.get("tags", []):
            match = False

        if match:
            content = entry["content"]
            preview = (
                content[:content_preview_length] + "..."
                if len(content) > content_preview_length
                else content
            )
            matches.append(
                {
                    "index": i,
                    "source": entry["source"],
                    "summary": entry.get("summary", ""),
                    "tags": entry.get("tags", []),
                    "content_preview": preview,
                }
            )

    return {
        "workspace_id": workspace_data.get("id", ""),
        "query": {"keyword": keyword, "tag": tag},
        "match_count": len(matches),
        "matches": matches,
    }
