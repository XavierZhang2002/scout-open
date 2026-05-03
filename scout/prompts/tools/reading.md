# Reading Tools Guide

## mcp__long_utils__get_file_info — File Reconnaissance

- **Mandatory first step** for any file you intend to read.
- Returns: file size, estimated tokens, long line detection, and **reading strategy recommendation**.
- **CRITICAL**: If `needs_normalization=true`, you MUST use `mcp__long_utils__normalize_document` immediately. Long lines cause `Grep` and `Read` to fail or return useless data.
- **V3**: Check the `reading_strategy` field for automated guidance:
  - `full_read`: File is small enough to read entirely
  - `grep_then_read`: Use Grep to locate, then Read specific sections
  - `grep_only`: File is very large, use only Grep

## mcp__long_utils__normalize_document — File Normalization

- Run this if `mcp__long_utils__get_file_info` indicates `needs_normalization=true`.
- Function: Splits excessively long lines (e.g., minified code, run-on paragraphs) into natural segments to enable effective searching and reading.
- After normalization, you can safely use Grep and Read on the file.

## Grep — Keyword Search

- Best for locating *where* information is (returns line numbers).
- Try multiple variations: synonyms, different phrasings.
- Most cost-effective way to locate information.
- **Always prefer Grep over Read** for initial information location.

## Read — File Reading (with offset/limit)

- **High Cost Warning**: Reading is expensive. ALWAYS try `Grep` first. Only use `Read` if `Grep` fails to locate specific information.
- For small files (<30k tokens): Use `Read(file_path)` to read entire file.
- For large files: Use `Read(file_path, offset=X, limit=Y)` to read specific sections.
  - `offset`: Starting line number (0-indexed)
  - `limit`: Number of lines to read

## Glob — File Pattern Search

- Use to discover files matching a pattern (e.g., `**/*.txt`, `*.pdf`).
- Useful when you need to find which files exist in the workspace.
