# Evaluation Flow (SubAgent Mode)

## How Evaluation Works in V3

In V3, evaluation is handled by a dedicated **Evaluator SubAgent** that automatically reviews your workspace when you indicate you're ready to answer.

### Workflow

1. Gather information and record it to workspace using `mcp__long_utils__workspace_update`.
2. When you believe you have sufficient information, the system will automatically trigger evaluation.
3. The Evaluator SubAgent will review your workspace and determine:
   - **Sufficient** (`is_sufficient=true`): You may proceed to generate the final answer.
   - **Insufficient** (`is_sufficient=false`): The evaluator will provide `missing_info` — update your plan and continue searching.

### Key Rules

- You MUST have called `mcp__long_utils__workspace_evaluate` at least once before generating a final answer.
- The evaluator **ONLY** sees what is in the workspace. If you read something but didn't save it with `mcp__long_utils__workspace_update`, the evaluator cannot see it.
- Trust the evaluation result. If it says sufficient, proceed. If insufficient, follow the `missing_info` guidance.
- Do not attempt to answer without evaluation confirmation.
