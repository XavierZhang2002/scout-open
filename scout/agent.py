"""
Scout — Core Agent Module

Contains the query_agent() function and supporting classes for token/tool tracking.
This is the main entry point for programmatic usage.

Usage:
    from scout.agent import query_agent
    from scout.config import load_config

    config = load_config()
    result, tiktoken_usage, api_usage, num_turns, tool_usage = await query_agent(
        "What is the main finding?",
        config=config,
    )
"""

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from loguru import logger
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    UserMessage,
    AssistantMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    SystemMessage,
    ResultMessage,
    ThinkingBlock,
    HookMatcher,
)

from .config import ScoutConfig
from .mcp_server import long_utils, set_workspace_dir
from .prompts.prompt_builder import PromptBuilder
from .hooks import (
    read_guard,
    auto_record_post_hook,
    track_evaluate,
    track_reading_tools,
    eval_guard_stop,
    token_tracker_hook,
    reset_all_hooks,
)
from .agents import planner_agent, evaluator_agent
from .permissions.permission_callback import create_permission_callback


# -- Logging -------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
log_dir = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(log_dir, exist_ok=True)
logger.add(os.path.join(log_dir, "scout.log"), level="DEBUG")


# -- Token / Tool Tracking ----------------------------------------------------


def _get_encoder(model_name: str):
    """Get tiktoken encoder."""
    import tiktoken

    try:
        return tiktoken.encoding_for_model(model_name)
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str, model: str) -> int:
    """Local token counting."""
    if text is None:
        return 0
    enc = _get_encoder(model)
    return len(enc.encode(text, disallowed_special=()))


@dataclass
class TokenTracker:
    """Local tiktoken-estimated token usage."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    def add_input(self, text: str, note: str = ""):
        n = _count_tokens(text or "", self.model)
        self.input_tokens += n

    def add_output(self, text: str, note: str = ""):
        n = _count_tokens(text or "", self.model)
        self.output_tokens += n

    def totals(self) -> dict:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens}

    def compute_cost(
        self,
        input_price_per_token: float,
        output_price_per_token: float,
    ) -> float:
        return (
            self.input_tokens * input_price_per_token
            + self.output_tokens * output_price_per_token
        )


@dataclass
class ToolUsageTracker:
    """Tool call count tracker."""

    tool_counts: dict = field(default_factory=dict)

    def add_tool_call(self, tool_name: str):
        self.tool_counts[tool_name] = self.tool_counts.get(tool_name, 0) + 1

    def get_counts(self) -> dict:
        return self.tool_counts.copy()


# -- Message Display -----------------------------------------------------------


def display_message(
    msg,
    tracker: TokenTracker,
    tool_tracker: Optional[ToolUsageTracker] = None,
) -> None:
    """Display message content and update token counts."""
    try:
        if isinstance(msg, UserMessage):
            tracker.add_input("User: ", "role_marker")
        elif isinstance(msg, AssistantMessage):
            tracker.add_input("Assistant: ", "role_marker")
        elif isinstance(msg, SystemMessage):
            tracker.add_input("System: ", "role_marker")

        if isinstance(msg, UserMessage):
            for block in msg.content or []:
                if isinstance(block, TextBlock) and getattr(block, "text", None) is not None:
                    logger.info(f"User: {block.text}")
                    tracker.add_input(block.text, "user")
                elif isinstance(block, ToolResultBlock):
                    full_result = {
                        "type": "tool_result",
                        "content": block.content,
                        "metadata": getattr(block, "metadata", {}),
                    }
                    content_text = json.dumps(full_result, ensure_ascii=False)
                    logger.info(f"Tool Result: {content_text}")
                    tracker.add_input(content_text, "tool_result")
                else:
                    block_dict = block.__dict__
                    repr_text = json.dumps(block_dict, ensure_ascii=False)
                    logger.info(f"User block (other): {repr_text}")
                    tracker.add_input(repr_text, "user_block_other")

        elif isinstance(msg, AssistantMessage):
            for block in msg.content or []:
                if isinstance(block, TextBlock) and getattr(block, "text", None) is not None:
                    logger.info(f"Agent: {block.text}")
                    tracker.add_output(block.text, "assistant_text")
                elif isinstance(block, ThinkingBlock) and getattr(block, "thinking", None) is not None:
                    logger.info(f"Thinking: {block.thinking}")
                    tracker.add_output(block.thinking, "assistant_thinking")
                elif isinstance(block, ToolUseBlock):
                    if tool_tracker is not None:
                        tool_tracker.add_tool_call(block.name)
                    tool_call = {
                        "name": block.name,
                        "input": block.input or {},
                        "metadata": getattr(block, "metadata", {}),
                    }
                    input_serial = json.dumps(tool_call, ensure_ascii=False)
                    logger.info(f"Using tool: {block.name}")
                    if block.input:
                        logger.info(f"  Input: {block.input}")
                    tracker.add_output(input_serial, f"tool_call:{block.name}")
                elif isinstance(block, ToolResultBlock):
                    full_result = {
                        "type": "tool_result",
                        "content": block.content,
                        "metadata": getattr(block, "metadata", {}),
                    }
                    content_text = json.dumps(full_result, ensure_ascii=False)
                    logger.info(f"Tool Result (assistant side): {content_text}")
                    tracker.add_input(content_text, "tool_result")
                else:
                    block_dict = block.__dict__
                    repr_text = json.dumps(block_dict, ensure_ascii=False)
                    logger.info(f"Assistant block (other): {repr_text}")
                    tracker.add_output(repr_text, "assistant_block_other")

        elif isinstance(msg, SystemMessage):
            if hasattr(msg, "content"):
                tracker.add_input(str(msg.content), "system_message")

        elif isinstance(msg, ResultMessage):
            result_dict = {
                "result": msg.result,
                "is_error": msg.is_error,
                "metadata": getattr(msg, "metadata", {}),
            }
            result_text = json.dumps(result_dict, ensure_ascii=False)
            tracker.add_output(result_text, "final_result")
            logger.info("Result ended")
        else:
            msg_dict = msg.__dict__
            msg_text = json.dumps(msg_dict, ensure_ascii=False)
            logger.info(f"Unknown message type: {type(msg)}")
            tracker.add_input(msg_text, "unknown_message")

    except Exception as e:
        logger.exception("display_message failed: %s", e)


# -- Hooks Builder -------------------------------------------------------------


def _build_hooks() -> dict:
    """Build Hooks dict for ClaudeAgentOptions."""
    return {
        "PreToolUse": [
            HookMatcher(matcher="Read|Grep", hooks=[read_guard]),
        ],
        "PostToolUse": [
            HookMatcher(matcher="Read|Grep", hooks=[auto_record_post_hook]),
            HookMatcher(
                matcher="mcp__long_utils__workspace_evaluate|evaluator",
                hooks=[track_evaluate],
            ),
            HookMatcher(matcher=None, hooks=[track_reading_tools]),
            HookMatcher(matcher=None, hooks=[token_tracker_hook]),
        ],
        "Stop": [
            HookMatcher(matcher=None, hooks=[eval_guard_stop]),
        ],
    }


# -- SubAgents Builder ---------------------------------------------------------


def _build_subagents(config: ScoutConfig) -> Optional[dict]:
    """Build SubAgents dict based on config."""
    agents = {}
    if config.use_planner_agent:
        agents["planner"] = planner_agent
    if config.use_evaluator_agent:
        agents["evaluator"] = evaluator_agent
    return agents if agents else None


# -- Core Query Function -------------------------------------------------------


async def query_agent(
    prompt: str,
    model: Optional[str] = None,
    server: Optional[str] = None,
    cache_path_one_run: Optional[str] = None,
    config: Optional[ScoutConfig] = None,
    event_callback: Optional[Callable] = None,
) -> tuple:
    """Core query entry point.

    Args:
        prompt: User question
        model: Model name override
        server: (deprecated, ignored) Use config.yaml instead
        cache_path_one_run: Working directory override
        config: ScoutConfig instance (if None, uses load_config())
        event_callback: Optional async callback for UI event streaming

    Returns:
        tuple: (result, tiktoken_usages, api_usage, num_turns, tool_usage)
    """
    # 1. Build config if not provided
    if config is None:
        from .config import load_config
        config = load_config()

    # Apply explicit overrides
    if model:
        config.model = model
    if cache_path_one_run:
        config.cwd = cache_path_one_run

    logger.info(config.summary())

    # 2. Sync environment variables
    if config.model:
        os.environ["ANTHROPIC_MODEL"] = config.model
    if config.base_url:
        os.environ["ANTHROPIC_BASE_URL"] = config.base_url
    if config.auth_token:
        os.environ["ANTHROPIC_AUTH_TOKEN"] = config.auth_token

    # 3. Set workspace directory
    workspace_dir = config.cwd or tempfile.mkdtemp(
        prefix="scout_ws_",
        dir=config.workspace_dir,
    )
    set_workspace_dir(workspace_dir)

    # 4. Reset hook state
    reset_all_hooks()

    # 5. Build system prompt
    builder = PromptBuilder()
    system_prompt = builder.build_with_config(config)

    # 6. Build hooks
    hooks = _build_hooks()

    # 7. Build subagents
    agents_dict = _build_subagents(config)

    # 8. Build permission callback
    permission_callback = create_permission_callback(config)

    # 9. Build ClaudeAgentOptions
    options = ClaudeAgentOptions(
        mcp_servers={"long_utils": long_utils},
        disallowed_tools=config.disallowed_tools,
        allowed_tools=config.allowed_tools,
        permission_mode=config.permission_mode,
        can_use_tool=permission_callback,
        env=config.env_dict,
        model=config.model or os.getenv("ANTHROPIC_MODEL"),
        cwd=config.cwd,
        system_prompt=system_prompt,
        max_turns=config.max_turns,
        hooks=hooks,
        agents=agents_dict,
    )

    # 10. Initialize trackers
    tracker = TokenTracker(model=options.model or "deepseek-chat")
    tool_tracker = ToolUsageTracker()
    tracker.add_input(options.system_prompt, "system_prompt")

    input_price = config.price_input_per_token
    output_price = config.price_output_per_token

    # 11. Execute query
    api_usage = None
    num_turns = 0

    async with ClaudeSDKClient(options=options) as client:
        logger.info(f"query: {prompt}")
        tracker.add_input(prompt, "user_query")
        result = ""
        await client.query(prompt)
        async for message in client.receive_response():
            display_message(message, tracker, tool_tracker)

            if event_callback is not None:
                try:
                    await event_callback(message, tracker, tool_tracker)
                except Exception as e:
                    logger.warning(f"event_callback failed: {e}")

            if isinstance(message, ResultMessage):
                if message.is_error:
                    logger.error(f"Agent returned error: {message.result}")
                    result = f"[Error] {message.result}"
                else:
                    result = message.result
                    logger.info(f"Final Message: {message}")
                api_usage = getattr(message, "usage", None)
                num_turns = getattr(message, "num_turns", 0)

    tiktoken_usages = tracker.totals()
    cost = tracker.compute_cost(input_price, output_price)
    tool_usage = tool_tracker.get_counts()
    logger.info(f"Tiktoken Usage: {tiktoken_usages}, estimated cost: {cost}")
    logger.info(f"Tool Usage: {tool_usage}")

    return result, tiktoken_usages, api_usage, num_turns, tool_usage
