# Workspace Tools Guide

## mcp__long_utils__workspace_update — Your Active Notebook

- **Function**: Stores the information you find. **Only info saved here counts.**
- **Usage**: Call this after *every* successful `Read` or `Grep` that yields relevant info.
- **Modes**:
  - **Create**: Provide `question` (leave `workspace_id` empty) to start a new workspace. The question MUST include the full context (question, options, and specific requirements), NOT ONLY the question text.
  - **Append**: Provide `workspace_id`, `content`, `source` to add findings.
  - **Replace**: Use `action='replace'` if you need to correct or overwrite previous notes.
- **V3 Enhancements**:
  - `tags`: Add tags to categorize your entries (e.g., `["chapter3", "key_finding", "comparison"]`). This helps with searching later.
  - `summary`: Add a one-sentence summary of the entry's key finding. Useful for quick workspace review.

## mcp__long_utils__workspace_view — Memory Review

- Returns the full content of your workspace.
- Use this to verify what you have stored before evaluation.
- V3: Shows tags and summaries alongside each entry.

## mcp__long_utils__workspace_search — Quick Lookup (V3 New)

- Search within your workspace entries by keyword or tag.
- Use this to quickly check if you've already collected information on a topic before searching the document again.
- Parameters:
  - `keyword`: Searches in content and summary (case-insensitive)
  - `tag`: Filters by tag name
- Returns matching entries with sources and summaries.

**Best Practice**: Before searching the document for a topic, first check your workspace with `workspace_search` to avoid redundant work.
