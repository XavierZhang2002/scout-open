# Critical Anti-Patterns

The following anti-patterns are **enforced by the system's Hooks mechanism**. Violations will be automatically blocked or warned.

| Anti-Pattern | Description | Enforcement | Hook |
|-------------|-------------|-------------|------|
| Invisible Reader | Reading a file but failing to call `mcp__long_utils__workspace_update`. The information is lost. | Auto-warn after Read without workspace_update | `auto_record_reminder` (PostToolUse) |
| Blind Reader | Calling `Read` on a file without first checking `mcp__long_utils__get_file_info`. **Reminder**: Reading is High Cost. | Block Read on unchecked files | `read_guard` (PreToolUse) |
| Stubborn Reader | Ignoring `needs_normalization=true` and reading/grepping without normalizing first. | Block Read/Grep on unnormalized files | `read_guard` (PreToolUse) |
| Premature Guesser | Answering the user *before* evaluation confirms sufficiency. | Block Stop without evaluation | `eval_guard_stop` (Stop) |
| Lazy Planner | Skipping `TodoWrite` for complex questions. | System warning (prompt-level only) | — |

**DO NOT** attempt to bypass these enforcement mechanisms. They exist to ensure accuracy and efficiency.
