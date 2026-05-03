"""
Scout UI — Pydantic schemas for API and WebSocket events

Defines all API request/response models and WebSocket event types.
"""

import time
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Event Types ───────────────────────────────────────────────────────────


class EventType(str, Enum):
    """WebSocket event types"""

    # Agent lifecycle
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_ERROR = "run_error"

    # Message stream (trajectory blocks)
    THINKING = "thinking"
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"

    # Phase tracking (inferred)
    PHASE_CHANGE = "phase_change"

    # Dashboard metrics
    METRICS_UPDATE = "metrics_update"

    # Workspace updates
    WORKSPACE_UPDATE = "workspace_update"


class RunStatus(str, Enum):
    """Run lifecycle states"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class AgentPhase(str, Enum):
    """Inferred agent execution phase"""

    IDLE = "idle"
    PLANNING = "planning"
    GATHERING = "gathering"
    VERIFYING = "verifying"


# ── WebSocket Event Models ────────────────────────────────────────────────


class WSEvent(BaseModel):
    """Base WebSocket event"""

    type: EventType
    timestamp: float = Field(default_factory=time.time)
    data: dict[str, Any] = Field(default_factory=dict)


# ── API Request Models ────────────────────────────────────────────────────


class QueryRequest(BaseModel):
    """POST /api/query request body"""

    query: str
    file_path: Optional[str] = None
    config_overrides: Optional[dict[str, Any]] = None


class ConfigUpdate(BaseModel):
    """PUT /api/config request body"""

    model: Optional[str] = None
    max_turns: Optional[int] = None
    use_planner_agent: Optional[bool] = None
    use_evaluator_agent: Optional[bool] = None
    permission_mode: Optional[str] = None
    tokenizer_model: Optional[str] = None
    large_file_token_threshold: Optional[int] = None
    huge_file_token_threshold: Optional[int] = None


# ── API Response Models ───────────────────────────────────────────────────


class QueryResponse(BaseModel):
    """POST /api/query response"""

    run_id: str
    status: RunStatus = RunStatus.PENDING


class RunStatusResponse(BaseModel):
    """GET /api/runs/{run_id}/status response"""

    run_id: str
    status: RunStatus
    phase: AgentPhase = AgentPhase.IDLE
    current_turn: int = 0
    max_turns: int = 200
    input_tokens: int = 0
    output_tokens: int = 0
    tool_counts: dict[str, int] = Field(default_factory=dict)
    error: Optional[str] = None


class RunResultResponse(BaseModel):
    """GET /api/runs/{run_id}/result response"""

    run_id: str
    result: str = ""
    tiktoken_usage: dict[str, int] = Field(default_factory=dict)
    api_usage: Optional[Any] = None
    num_turns: int = 0
    tool_usage: dict[str, int] = Field(default_factory=dict)


class ConfigResponse(BaseModel):
    """GET /api/config response"""

    model: Optional[str] = None
    max_turns: int = 200
    use_planner_agent: bool = True
    use_evaluator_agent: bool = True
    permission_mode: str = "bypassPermissions"
    tokenizer_model: str = "deepseek-chat"
    large_file_token_threshold: int = 30000
    huge_file_token_threshold: int = 100000


class UploadResponse(BaseModel):
    """POST /api/upload response"""

    file_path: str
    file_name: str
    file_size: int


class WorkspaceEntry(BaseModel):
    """Single workspace entry"""

    key: str = ""
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    content: str = ""
    source_file: str = ""
    line_range: str = ""


class WorkspaceResponse(BaseModel):
    """GET /api/runs/{run_id}/workspace response"""

    run_id: str
    entries: list[WorkspaceEntry] = Field(default_factory=list)
