#!/usr/bin/env python3
"""
SCOUT Skill — Environment Check Script

Executed via dynamic context injection (!`) when the skill loads.
Parses user arguments and validates the document environment.

Outputs a structured context block that gets injected into the skill prompt.
"""

import os
import sys
from pathlib import Path
from collections import Counter


def parse_arguments(raw_args: str) -> dict:
    """Parse skill arguments: <query> --cwd <dir> [--max-turns N]"""
    parts = raw_args.strip().split()
    result = {"query": "", "cwd": "", "max_turns": "", "flags": []}

    if not parts:
        return result

    # Extract --flags
    i = 0
    query_parts = []
    while i < len(parts):
        if parts[i] == "--cwd" and i + 1 < len(parts):
            result["cwd"] = parts[i + 1]
            i += 2
        elif parts[i] == "--max-turns" and i + 1 < len(parts):
            result["max_turns"] = parts[i + 1]
            i += 2
        elif parts[i] in ("--no-planner", "--no-evaluator"):
            result["flags"].append(parts[i])
            i += 1
        else:
            query_parts.append(parts[i])
            i += 1

    # Join remaining parts as query (strip surrounding quotes)
    query = " ".join(query_parts)
    if query and query[0] in ('"', "'") and query[-1] == query[0]:
        query = query[1:-1]
    result["query"] = query

    return result


def scan_directory(dir_path: str) -> dict:
    """Scan document directory for readable files."""
    path = Path(dir_path)
    if not path.exists():
        return {"error": f"Directory does not exist: {dir_path}"}
    if not path.is_dir():
        return {"error": f"Not a directory: {dir_path}"}

    # Common document extensions
    doc_extensions = {
        ".txt", ".md", ".json", ".csv", ".html", ".xml",
        ".log", ".yaml", ".yml", ".toml", ".ini", ".cfg",
        ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h",
        ".pdf", ".rst", ".tex",
    }

    files = []
    ext_counter = Counter()
    total_size = 0

    for f in path.rglob("*"):
        if f.is_file() and not any(p.startswith(".") for p in f.relative_to(path).parts):
            ext = f.suffix.lower()
            size = f.stat().st_size
            if ext in doc_extensions or size < 10_000_000:  # include if <10MB
                files.append({"name": str(f.relative_to(path)), "size": size, "ext": ext})
                ext_counter[ext or "(no ext)"] += 1
                total_size += size

    return {
        "total_files": len(files),
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "extensions": dict(ext_counter.most_common(10)),
        "sample_files": [f["name"] for f in sorted(files, key=lambda x: -x["size"])[:15]],
    }


def main():
    raw_args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    parsed = parse_arguments(raw_args)

    # Output structured context
    print("<scout-env>")

    if not parsed["query"]:
        print("STATUS: ERROR")
        print("MESSAGE: No query provided. Usage: /scout \"<question>\" --cwd <document-directory>")
        print("</scout-env>")
        return

    if not parsed["cwd"]:
        print("STATUS: ERROR")
        print("MESSAGE: No --cwd provided. You must specify the document directory.")
        print(f"QUERY: {parsed['query']}")
        print("</scout-env>")
        return

    # Expand path
    cwd = os.path.expanduser(parsed["cwd"])
    cwd = os.path.abspath(cwd)

    print(f"STATUS: OK")
    print(f"QUERY: {parsed['query']}")
    print(f"CWD: {cwd}")
    if parsed["max_turns"]:
        print(f"MAX_TURNS: {parsed['max_turns']}")
    if parsed["flags"]:
        print(f"FLAGS: {' '.join(parsed['flags'])}")

    # Scan directory
    scan = scan_directory(cwd)
    if "error" in scan:
        print(f"DIR_STATUS: ERROR - {scan['error']}")
    else:
        print(f"DIR_STATUS: OK")
        print(f"TOTAL_FILES: {scan['total_files']}")
        print(f"TOTAL_SIZE: {scan['total_size_mb']} MB")
        print(f"FILE_TYPES: {scan['extensions']}")
        if scan["sample_files"]:
            print(f"SAMPLE_FILES:")
            for fname in scan["sample_files"][:10]:
                print(f"  - {fname}")

    print("</scout-env>")


if __name__ == "__main__":
    main()
