# Core Decision Heuristics

## 1. Search vs. Read

- **ALWAYS use `Grep` first** to locate keywords. It is the cheapest operation.
- ONLY use `Read` (full file) if `mcp__long_utils__get_file_info` confirms the file is small (<30k tokens).
- OTHERWISE, use `Read` with `offset`/`limit` to target specific sections found by Grep.

## 2. The "Record & Verify" Loop

- **Rule of Thumb**: If you read it, record it. If you didn't record it in `mcp__long_utils__workspace_update`, the evaluator cannot see it.
- **When to Evaluate**: Only when you believe you have gathered *all* necessary components defined in your `TodoWrite` plan.

## 3. When to Stop

- Stop IMMEDIATELY when evaluation confirms sufficiency (`is_sufficient=true`).
- Do not "double-check" or "read a bit more" just in case. Trust the evaluation result.

## 4. File Reconnaissance First

- ALWAYS call `mcp__long_utils__get_file_info` before reading any file for the first time.
- Check the `reading_strategy` field for guidance on the optimal approach.
- If `needs_normalization=true`, you MUST normalize before any Read/Grep operations.
