# Evaluation Flow (V1 Compatible Mode)

## Sufficiency Verification

Use `mcp__long_utils__workspace_evaluate` as the **critical gatekeeper** before generating your final answer.

### Workflow

1. Gather info → `mcp__long_utils__workspace_update`
2. Call `mcp__long_utils__workspace_evaluate(workspace_id="...")`
3. If `is_sufficient=true`: You have the green light. Proceed to generate the final answer based *only* on the workspace content.
4. If `is_sufficient=false`:
   - Read the `missing_info` field from the tool output.
   - Update your `TodoWrite` with new tasks to find that missing info.
   - Loop back to Phase 2 (GATHER & RECORD).

### Key Rules

- The evaluator **ONLY** sees what is in the workspace. If you read the answer but didn't save it with `mcp__long_utils__workspace_update`, the evaluator will say "Insufficient".
- Stop IMMEDIATELY when `workspace_evaluate` returns `is_sufficient=true`.
- Do not "double-check" or "read a bit more" just in case. Trust the evaluator.
- You MUST call `workspace_evaluate` at least once before generating a final answer.
