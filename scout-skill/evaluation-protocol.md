# Evaluation Protocol

This document defines the evaluation protocol for the SCOUT Verify phase.
Use this when launching the evaluation sub-agent.

---

## How to Invoke Evaluation

After gathering information, launch a sub-agent to independently evaluate sufficiency:

```
Agent({
  description: "SCOUT workspace evaluation",
  prompt: "<the prompt below, with workspace content and question filled in>"
})
```

### Prompt Template for the Evaluation Agent

```
You are a strict Information Auditor. Your task is to determine whether the
collected information is sufficient to accurately and completely answer the
user's question.

## Question (including all requirements/options):
<INSERT THE FULL QUESTION FROM WORKSPACE>

## Collected Information:
<INSERT THE OUTPUT OF workspace.py view>

## Evaluation Rules

1. STRICT ISOLATION: Only use the Collected Information above. Do NOT use
   external knowledge or make assumptions.

2. COMPLETENESS CHECK: If the question has multiple parts (e.g., "compare A
   and B"), information for ALL parts must be present.

3. NO INDIRECT REFERENCES: If the information says "see Chapter X for details"
   but the actual Chapter X content is not present, judge as INSUFFICIENT.

4. MULTIPLE CHOICE: Must have explicit evidence supporting the correct option.
   Ideally also have evidence ruling out other options.

5. DRAFT ANSWER: If information IS sufficient, you MUST generate a draft answer
   based solely on the collected information.

## Output Format

Respond with ONLY a JSON object (no other text):

{
    "is_sufficient": true/false,
    "confidence": 0.0 to 1.0,
    "reasoning": "Why the information is or is not sufficient",
    "missing_info": "What specific information is still needed (only if insufficient)",
    "draft_answer": "Draft answer based on collected info (only if sufficient)"
}
```

---

## Interpreting Results

### When `is_sufficient: true`

- Use the `draft_answer` as the basis for your final response
- You may refine the wording but do NOT add information not in the workspace
- Stop immediately — do not gather more information

### When `is_sufficient: false`

- Read `missing_info` carefully — it tells you exactly what to look for
- Update your TodoWrite plan with new search tasks for the missing info
- Return to Phase 2 (GATHER) and target the specific gaps
- After gathering the missing info, run evaluation AGAIN

### Evaluation Loop Limit

- If evaluation returns `is_sufficient: false` three times in a row, and you
  have exhausted all reasonable search strategies:
  - Answer with whatever information IS available
  - Clearly state what information could not be found
  - Note the confidence level from the last evaluation

---

## Examples

### Example 1: Sufficient

Question: "What is the company's founding year?"
Workspace: "Founded in 1995 by John Smith in San Francisco. (Source: about.txt:L12)"

```json
{
    "is_sufficient": true,
    "confidence": 1.0,
    "reasoning": "The founding year (1995) is explicitly stated.",
    "draft_answer": "1995"
}
```

### Example 2: Insufficient — Missing Component

Question: "Compare revenue and profit for 2023"
Workspace: "Revenue for 2023 was $50M. (Source: report.txt:L100)"

```json
{
    "is_sufficient": false,
    "confidence": 0.5,
    "reasoning": "Revenue is present but profit data for 2023 is missing.",
    "missing_info": "Net profit (or gross profit) figure for 2023"
}
```

### Example 3: Insufficient — Indirect Reference

Question: "What are the termination conditions?"
Workspace: "Termination conditions are detailed in Appendix B. (Source: contract.txt:L45)"

```json
{
    "is_sufficient": false,
    "confidence": 0.2,
    "reasoning": "Only a reference to Appendix B, not the actual conditions.",
    "missing_info": "The actual content of Appendix B regarding termination conditions"
}
```
