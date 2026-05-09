# Workspace Operations Guide

Complete reference for using `workspace.py` to manage the SCOUT workspace.

The workspace is stored at `<CWD>/.scout-workspace/workspace.json`.

---

## Commands

### create — Initialize a New Workspace

**Must be called once before any other workspace operation.**

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/workspace.py create \
  --question "The COMPLETE question including all options and requirements" \
  --cwd "<document-directory>"
```

**Important**: The `--question` field must include the FULL question context — not just the core question, but any options (A/B/C/D), sub-questions, and specific requirements. The evaluator uses this to judge sufficiency.

Output:
```json
{"status": "created", "workspace_id": "abc12345_1234567890", "path": "..."}
```

---

### append — Record a Finding

**Call this IMMEDIATELY after every Read/Grep that yields relevant info.**

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/workspace.py append \
  --content "The actual information extracted from the document" \
  --source "filename.txt:L45-L60" \
  --tags "tag1,tag2,tag3" \
  --summary "One-line description of what this entry contains" \
  --cwd "<document-directory>"
```

Parameters:
| Param | Required | Description |
|-------|----------|-------------|
| `--content` | Yes | The extracted information (quote or paraphrase) |
| `--source` | Yes | File and line reference (e.g., `report.txt:L100-120`) |
| `--tags` | No | Comma-separated categorization tags |
| `--summary` | No | One-line entry summary for quick review |
| `--cwd` | No | Working directory (uses env or current dir if omitted) |

**Best practices for `--content`:**
- Include enough context to understand without re-reading the source
- For quotes: use exact text
- For data: include numbers, units, dates
- For references: note what they point to

---

### view — Review Workspace Contents

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/workspace.py view --cwd "<document-directory>"
```

Returns all entries formatted with sources, tags, and summaries. Use this:
- Before evaluation (to review what you have)
- When synthesizing a final answer
- To check if something was already recorded

---

### search — Find Within Workspace

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/workspace.py search \
  --keyword "revenue" \
  --tag "financial" \
  --cwd "<document-directory>"
```

At least one of `--keyword` or `--tag` is required. Use this:
- Before searching a document for a topic (avoid duplicates)
- When you need to find a specific piece of previously recorded info
- To check coverage of a specific tag/topic

---

### summary — Workspace Statistics

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/workspace.py summary --cwd "<document-directory>"
```

Returns: entry count, total size, all tags used, timestamps. Useful for gauging progress.

---

### file-info — File Reconnaissance

**MANDATORY before first Read of any file.**

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/workspace.py file-info --path "<file-path>"
```

Returns:
```json
{
  "file_size_bytes": 1234567,
  "estimated_tokens": 35000,
  "needs_normalization": false,
  "reading_strategy": {
    "approach": "grep_then_read",
    "recommendation": "Use Grep to locate, then Read(offset, limit)",
    "warnings": []
  }
}
```

**Decision rules based on approach:**
- `full_read` → safe to Read entire file
- `grep_then_read` → MUST use Grep first, then Read specific sections
- `grep_only` → DO NOT Read; use only Grep searches

---

### normalize — Fix Long-Line Files

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/workspace.py normalize --path "<file-path>"
```

Only needed when `file-info` reports `needs_normalization: true`. Splits lines >2000 chars at natural break points (sentences, spaces). Modifies the file in-place.

---

## Workflow Example

```bash
# 1. Initialize
python3 workspace.py create --question "What is the net profit for 2023?" --cwd /docs

# 2. Check file before reading
python3 workspace.py file-info --path /docs/annual_report.txt

# 3. After finding relevant info via Grep+Read:
python3 workspace.py append \
  --content "Net profit for fiscal year 2023 was $12.5M, a 15% increase from 2022." \
  --source "annual_report.txt:L1425-L1430" \
  --tags "financial,2023,profit" \
  --summary "2023 net profit: $12.5M (+15% YoY)" \
  --cwd /docs

# 4. Review before evaluation
python3 workspace.py view --cwd /docs

# 5. Check if something was already recorded
python3 workspace.py search --keyword "profit" --cwd /docs
```
