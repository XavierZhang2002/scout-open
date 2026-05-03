"""
Scout — External LLM Evaluation Tool (Fallback)

- Not used when Evaluator SubAgent is enabled
- Used as fallback evaluation method when use_evaluator_agent=False
- Code largely unchanged, only minor adjustments to logging and config reading

"""

import os
import re
import json
import ast
import time
from typing import Dict, Any, Optional

from loguru import logger


async def evaluate_sufficiency(
    question: str,
    collected_info: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Call external LLM to evaluate whether collected information is sufficient.

    This function is retained as a fallback. Used when Evaluator SubAgent is disabled.

    Args:
        question: Original question
        collected_info: Collected information
        api_key: API key (falls back to EVAL_API_KEY environment variable)
        base_url: API base URL (falls back to EVAL_API_BASE_URL environment variable)
        model: Model name (falls back to EVAL_MODEL environment variable)

    Returns:
        dict: Evaluation result, containing is_sufficient, reasoning, etc.
    """
    try:
        from openai import OpenAI

        _api_key = api_key or os.getenv("EVAL_API_KEY")
        _base_url = base_url or os.getenv("EVAL_API_BASE_URL")
        _model = model or os.getenv("EVAL_MODEL", "claude-4-5-sonnet-20250929")

        if not _api_key or not _base_url:
            return {
                "is_sufficient": False,
                "reasoning": "Evaluation API not configured (missing EVAL_API_KEY or EVAL_API_BASE_URL)",
            }

        client = OpenAI(api_key=_api_key, base_url=_base_url)

        logger.info(
            f"[fallback] Calling LLM for sufficiency evaluation:\n"
            f"  BASE_URL: {_base_url}\n  MODEL: {_model}"
        )

        prompt = f"""You are a strict Information Auditor.
        
Task: Determine if the provided "Collected Information" is sufficient to answer the "Question" completely and accurately.

### Rules:
1. **Strict Isolation**: You must ONLY use the Collected Information. Do not use outside knowledge.
2. **Completeness**: If the question has multiple parts (e.g., "compare A and B"), you need info for BOTH.
3. **No References**: If the info says "See Section 4 for details" but does not contain the details, it is INSUFFICIENT.
4. **Draft Answer**: If sufficient, provide a concise draft answer derived ONLY from the text.
5. **Multiple Choice**: For multiple choice questions, you must have evidence to support the correct option AND rule out others if necessary, or at least explicitly confirm the correct one.

### Examples:

**Example 1 (Insufficient - Partial Info)**
Question: "What are the revenue and net profit for 2023?"
Collected Info: "The company reported a record revenue of $50M in 2023."
Result:
{{
    "is_sufficient": false,
    "confidence": 0.6,
    "reasoning": "Contains revenue but missing net profit data.",
    "missing_info": "Net profit for 2023"
}}

**Example 2 (Insufficient - Indirect Reference)**
Question: "What are the termination conditions?"
Collected Info: "Termination conditions are outlined in Schedule B of the agreement."
Result:
{{
    "is_sufficient": false,
    "confidence": 0.8,
    "reasoning": "The text refers to Schedule B but does not provide the actual conditions.",
    "missing_info": "Content of Schedule B regarding termination"
}}

**Example 3 (Sufficient - Multiple Choice)**
Question: "Which material is the primary component of the outer shell? A. Aluminum B. Titanium C. Carbon Fiber D. Steel"
Collected Info: "The chassis is built from aluminum, but the outer shell is exclusively manufactured using aerospace-grade Titanium for heat resistance."
Result:
{{
    "is_sufficient": true,
    "confidence": 0.7,
    "reasoning": "Explicitly states the outer shell is made of Titanium, matching Option B.",
    "draft_answer": "Option B (Titanium)"
}}

**Example 4 (Sufficient - Direct Answer)**
Question: "Who is the current CEO?"
Collected Info: "In a press release, the board announced Jane Doe as the new CEO effective immediately."
Result:
{{
    "is_sufficient": true,
    "confidence": 1.0,
    "reasoning": "Explicitly states Jane Doe is the CEO.",
    "draft_answer": "Jane Doe"
}}

### Current Task:

**Question (and requirements/options):** 
{question}

**Collected Information:**
{collected_info}

**Output strictly valid JSON:**
{{
    "is_sufficient": true/false,
    "confidence": 0.0 to 1.0,
    "reasoning": "string explanation",
    "missing_info": "string describing what is missing (if insufficient)",
    "draft_answer": "string (only if sufficient)"
}}
"""

        max_retries = 6
        response = None
        last_error = None

        for attempt in range(max_retries):
            try:
                chat_response = client.chat.completions.create(
                    model=_model,
                    max_tokens=int(os.getenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "4096")),
                    temperature=0,
                    messages=[{"role": "user", "content": prompt}],
                )
                content = chat_response.choices[0].message.content
                response = content
                break
            except Exception as e:
                last_error = e
                logger.warning(
                    f"[fallback] Evaluation attempt {attempt + 1}/{max_retries} failed: {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep(3)

        if response is None:
            if last_error:
                raise last_error
            raise RuntimeError("Evaluation failed with no response and no error")

        # Extract JSON
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                try:
                    return ast.literal_eval(json_str)
                except Exception:
                    pass

        # Fallback return when JSON parsing fails
        return {
            "is_sufficient": False,
            "reasoning": "Failed to parse LLM response (JSON format error)",
            "raw_response": response,
        }

    except Exception as e:
        logger.error(f"[fallback] LLM evaluation error: {e}")
        return {
            "is_sufficient": False,
            "reasoning": f"System error during evaluation: {str(e)}",
        }
