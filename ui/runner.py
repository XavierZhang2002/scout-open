"""
Scout UI — Agent Runner

Bridges query_agent() with the EventEmitter. Creates event callbacks that parse
Agent messages into typed events and broadcast them to WebSocket subscribers.

Manages run lifecycle: start, track, complete/error.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

# Add project root to Python path for imports
PROJECT_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".."
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from event_emitter import EventEmitter
from schemas import AgentPhase, EventType, RunStatus


# ── Run State ─────────────────────────────────────────────────────────────


@dataclass
class RunState:
    """Tracks the state of a single agent run."""

    run_id: str
    query: str
    status: RunStatus = RunStatus.PENDING
    phase: AgentPhase = AgentPhase.IDLE
    current_turn: int = 0
    max_turns: int = 200
    input_tokens: int = 0
    output_tokens: int = 0
    tool_counts: dict[str, int] = field(default_factory=dict)
    result: str = ""
    tiktoken_usage: dict[str, int] = field(default_factory=dict)
    api_usage: Any = None
    num_turns: int = 0
    tool_usage: dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None
    file_path: Optional[str] = None
    workspace_dir: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    step_counter: int = 0


# ── Phase Inference ───────────────────────────────────────────────────────

# Tools that indicate each phase
PLANNING_TOOLS = {"TodoWrite"}
GATHERING_TOOLS = {
    "mcp__long_utils__get_file_info",
    "mcp__long_utils__normalize_document",
    "mcp__long_utils__workspace_update",
    "mcp__long_utils__workspace_search",
    "Read",
    "Grep",
    "Glob",
}
VERIFYING_TOOLS = {
    "mcp__long_utils__workspace_evaluate",
    "evaluator",
}


def _infer_phase(tool_name: str, current_phase: AgentPhase) -> AgentPhase:
    """Infer the agent's execution phase from tool usage.

    Args:
        tool_name: Name of the tool being called
        current_phase: Current phase

    Returns:
        Inferred phase (may be same as current)
    """
    if tool_name in VERIFYING_TOOLS:
        return AgentPhase.VERIFYING
    elif tool_name in GATHERING_TOOLS:
        return AgentPhase.GATHERING
    elif tool_name in PLANNING_TOOLS:
        return AgentPhase.PLANNING
    return current_phase


# ── Agent Runner ──────────────────────────────────────────────────────────


class AgentRunner:
    """Manages agent runs and bridges query_agent() with EventEmitter.

    Usage:
        runner = AgentRunner(emitter)
        run_id = await runner.start_run(query, file_path, config_overrides)
        state = runner.get_run(run_id)
    """

    def __init__(self, emitter: EventEmitter):
        self.emitter = emitter
        self.runs: dict[str, RunState] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def generate_run_id(self) -> str:
        """Generate a unique run ID."""
        return str(uuid.uuid4())[:8]

    async def start_run(
        self,
        query: str,
        file_path: Optional[str] = None,
        config_overrides: Optional[dict[str, Any]] = None,
    ) -> str:
        """Start a new agent run in the background.

        Args:
            query: User's question
            file_path: Optional path to uploaded document
            config_overrides: Optional config field overrides

        Returns:
            run_id: Unique identifier for this run
        """
        run_id = self.generate_run_id()
        state = RunState(run_id=run_id, query=query, file_path=file_path)
        self.runs[run_id] = state

        # Launch the run as a background task
        task = asyncio.create_task(
            self._execute_run(run_id, query, file_path, config_overrides)
        )
        self._tasks[run_id] = task

        return run_id

    async def _execute_run(
        self,
        run_id: str,
        query: str,
        file_path: Optional[str] = None,
        config_overrides: Optional[dict[str, Any]] = None,
    ) -> None:
        """Execute query_agent() and emit events.

        Args:
            run_id: Run identifier
            query: User's question
            file_path: Optional document path
            config_overrides: Optional config overrides
        """
        state = self.runs[run_id]

        try:
            # Import scout modules (lazy import to avoid circular deps)
            from scout.config import load_config, ScoutConfig
            from scout.agent import query_agent
            from scout.mcp_server import get_workspace_dir

            # Build config from config.yaml
            config = load_config()

            # Apply overrides (skip keys that don't exist on ScoutConfig)
            if config_overrides:
                for key, value in config_overrides.items():
                    if hasattr(config, key) and key != "server":
                        try:
                            setattr(config, key, value)
                        except (AttributeError, TypeError):
                            pass

            state.max_turns = config.max_turns

            # NOTE: Do NOT set config.cwd to the upload directory.
            # config.cwd is used as workspace_dir in query_agent() (main.py line 399):
            #   workspace_dir = config.cwd or tempfile.mkdtemp(...)
            # If we set config.cwd = UPLOAD_DIR, ALL runs share the same workspace
            # directory, causing workspace entries from previous runs to persist.
            # By leaving config.cwd empty, query_agent() creates a fresh temp dir
            # per run, ensuring workspace isolation.
            # The prompt includes the absolute file_path, so the agent can still
            # read the uploaded document without needing cwd to point at UPLOAD_DIR.

            # Build the prompt — include file path if provided
            prompt = query
            if file_path:
                prompt = f"Please read the file {file_path}, then answer the following question:\n\n{query}"

            # Update state
            state.status = RunStatus.RUNNING
            state.phase = AgentPhase.PLANNING

            # Emit run_started
            await self.emitter.emit(
                run_id,
                EventType.RUN_STARTED,
                {
                    "run_id": run_id,
                    "query": query,
                    "file_path": file_path,
                    "config": {
                        "model": config.model,
                        "max_turns": config.max_turns,
                    },
                },
            )

            # Create event callback
            callback = self._create_event_callback(run_id)

            # Execute query_agent
            (
                result,
                tiktoken_usage,
                api_usage,
                num_turns,
                tool_usage,
            ) = await query_agent(
                prompt=prompt,
                config=config,
                event_callback=callback,
            )

            # Capture workspace_dir from the ContextVar (still in same Task context)
            try:
                state.workspace_dir = get_workspace_dir()
                logger.info(f"Run {run_id} workspace_dir: {state.workspace_dir}")
            except Exception as e:
                logger.warning(f"Failed to capture workspace_dir: {e}")

            # Update state with results
            state.status = RunStatus.COMPLETED
            state.result = result
            state.tiktoken_usage = tiktoken_usage
            state.api_usage = api_usage
            state.num_turns = num_turns
            state.tool_usage = tool_usage
            state.completed_at = time.time()

            # Emit final workspace_update with all entries
            workspace_entries = self._scan_workspace_files(state.workspace_dir)
            if workspace_entries:
                await self.emitter.emit(
                    run_id,
                    EventType.WORKSPACE_UPDATE,
                    {"entries": workspace_entries},
                )

            # Emit run_completed
            await self.emitter.emit(
                run_id,
                EventType.RUN_COMPLETED,
                {
                    "run_id": run_id,
                    "result": result,
                    "tiktoken_usage": tiktoken_usage,
                    "api_usage": str(api_usage) if api_usage else None,
                    "num_turns": num_turns,
                    "tool_usage": tool_usage,
                },
            )

        except Exception as e:
            logger.exception(f"Run {run_id} failed: {e}")
            state.status = RunStatus.ERROR
            state.error = str(e)
            state.completed_at = time.time()

            await self.emitter.emit(
                run_id,
                EventType.RUN_ERROR,
                {
                    "run_id": run_id,
                    "error": str(e),
                },
            )

    def _create_event_callback(self, run_id: str):
        """Create an event callback for query_agent().

        The callback receives each message from the agent's response stream
        and emits typed WebSocket events.

        Args:
            run_id: The run identifier

        Returns:
            Async callback function compatible with query_agent(event_callback=...)
        """
        state = self.runs[run_id]
        # Track tool_use_id -> tool_name for workspace update detection
        pending_tool_calls: dict[str, str] = {}

        # Workspace tool names that should trigger a workspace_update event
        WORKSPACE_TOOLS = {
            "mcp__long_utils__workspace_update",
            "mcp__long_utils__workspace_view",
            "mcp__long_utils__workspace_search",
            "mcp__long_utils__workspace_evaluate",
        }

        async def callback(message, tracker, tool_tracker):
            """Process a single agent message and emit events.

            Args:
                message: SDK message (UserMessage, AssistantMessage, etc.)
                tracker: TokenTracker instance
                tool_tracker: ToolUsageTracker instance
            """
            # Lazy import SDK types
            from claude_agent_sdk import (
                AssistantMessage,
                ResultMessage,
                TextBlock,
                ThinkingBlock,
                ToolResultBlock,
                ToolUseBlock,
                UserMessage,
            )

            # Update token counts from tracker
            totals = tracker.totals()
            state.input_tokens = totals.get("input_tokens", 0)
            state.output_tokens = totals.get("output_tokens", 0)
            state.tool_counts = tool_tracker.get_counts()

            # Process message blocks based on type
            if isinstance(message, AssistantMessage):
                for block in message.content or []:
                    state.step_counter += 1

                    if isinstance(block, ThinkingBlock) and getattr(
                        block, "thinking", None
                    ):
                        await self.emitter.emit(
                            run_id,
                            EventType.THINKING,
                            {
                                "step": state.step_counter,
                                "content": block.thinking,
                            },
                        )

                    elif isinstance(block, TextBlock) and getattr(block, "text", None):
                        await self.emitter.emit(
                            run_id,
                            EventType.TEXT,
                            {
                                "step": state.step_counter,
                                "content": block.text,
                            },
                        )

                    elif isinstance(block, ToolUseBlock):
                        tool_name = block.name
                        tool_input = block.input or {}
                        call_id = getattr(block, "id", "")

                        # Track this tool call for workspace detection
                        if call_id:
                            pending_tool_calls[call_id] = tool_name

                        # Phase inference
                        new_phase = _infer_phase(tool_name, state.phase)
                        if new_phase != state.phase:
                            state.phase = new_phase
                            await self.emitter.emit(
                                run_id,
                                EventType.PHASE_CHANGE,
                                {
                                    "phase": new_phase.value,
                                },
                            )

                        await self.emitter.emit(
                            run_id,
                            EventType.TOOL_CALL,
                            {
                                "step": state.step_counter,
                                "tool_name": tool_name,
                                "tool_input": _safe_serialize(tool_input),
                                "call_id": call_id,
                            },
                        )

                    elif isinstance(block, ToolResultBlock):
                        content = block.content
                        is_error = getattr(block, "is_error", False)

                        await self.emitter.emit(
                            run_id,
                            EventType.TOOL_RESULT,
                            {
                                "step": state.step_counter,
                                "content": _safe_serialize(content),
                                "is_error": is_error,
                                "call_id": getattr(block, "tool_use_id", ""),
                            },
                        )

            elif isinstance(message, UserMessage):
                # User messages contain tool results
                has_workspace_tool = False
                for block in message.content or []:
                    if isinstance(block, ToolResultBlock):
                        state.step_counter += 1
                        content = block.content
                        is_error = getattr(block, "is_error", False)
                        call_id = getattr(block, "tool_use_id", "")

                        # Check if this result is from a workspace tool
                        tool_name = pending_tool_calls.pop(call_id, "")
                        if tool_name in WORKSPACE_TOOLS and not is_error:
                            has_workspace_tool = True

                        await self.emitter.emit(
                            run_id,
                            EventType.TOOL_RESULT,
                            {
                                "step": state.step_counter,
                                "content": _safe_serialize(content),
                                "is_error": is_error,
                                "call_id": call_id,
                            },
                        )

                # If a workspace tool completed, scan and emit workspace entries
                if has_workspace_tool:
                    try:
                        from scout.mcp_server import get_workspace_dir

                        ws_dir = get_workspace_dir()
                        ws_entries = self._scan_workspace_files(ws_dir)
                        if ws_entries:
                            await self.emitter.emit(
                                run_id,
                                EventType.WORKSPACE_UPDATE,
                                {"entries": ws_entries},
                            )
                    except Exception as e:
                        logger.debug(f"Workspace scan during run failed: {e}")

            # Emit metrics update after every message
            await self.emitter.emit(
                run_id,
                EventType.METRICS_UPDATE,
                {
                    "input_tokens": state.input_tokens,
                    "output_tokens": state.output_tokens,
                    "tool_counts": state.tool_counts,
                    "phase": state.phase.value,
                    "turn": state.step_counter,
                    "max_turns": state.max_turns,
                },
            )

        return callback

    def get_run(self, run_id: str) -> Optional[RunState]:
        """Get the state of a run.

        Args:
            run_id: The run identifier

        Returns:
            RunState if found, None otherwise
        """
        return self.runs.get(run_id)

    def get_workspace_entries(self, run_id: str) -> list[dict]:
        """Get workspace entries for a run.

        Args:
            run_id: The run identifier

        Returns:
            List of workspace entry dicts
        """
        state = self.get_run(run_id)
        if not state:
            return []

        # Use the captured workspace_dir from the run
        if state.workspace_dir:
            return self._scan_workspace_files(state.workspace_dir)

        return []

    def _scan_workspace_files(self, workspace_dir: Optional[str]) -> list[dict]:
        """Scan for workspace JSON files and extract entries.

        Args:
            workspace_dir: Directory to scan for workspace_*.json files

        Returns:
            List of workspace entry dicts
        """
        if not workspace_dir or not os.path.isdir(workspace_dir):
            return []

        entries = []
        try:
            import glob

            for ws_file in glob.glob(os.path.join(workspace_dir, "workspace_*.json")):
                with open(ws_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for entry in data.get("entries", []):
                        entries.append(
                            {
                                "key": entry.get("key", ""),
                                "tags": entry.get("tags", []),
                                "summary": entry.get("summary", ""),
                                "content": entry.get("content", "")[
                                    :500
                                ],  # Truncate for UI
                                "source_file": entry.get("source", ""),
                                "line_range": entry.get("line_range", ""),
                            }
                        )
        except Exception as e:
            logger.warning(f"Failed to scan workspace files: {e}")

        return entries


def _safe_serialize(obj: Any) -> Any:
    """Safely serialize an object for JSON transmission.

    Args:
        obj: Object to serialize

    Returns:
        JSON-safe representation
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(item) for item in obj]
    try:
        return json.loads(json.dumps(obj, default=str, ensure_ascii=False))
    except Exception:
        return str(obj)
