"""
Scout UI — FastAPI Server

Main web server providing REST API endpoints and WebSocket handler
for the Scout Agent UI.

Endpoints:
    GET  /                           Serve frontend SPA
    GET  /api/config                 Get current config
    PUT  /api/config                 Update config fields
    GET  /api/config/servers         List server presets
    POST /api/upload                 Upload a file
    POST /api/query                  Start a query run
    GET  /api/runs/{run_id}/status   Get run status
    GET  /api/runs/{run_id}/result   Get run result
    GET  /api/runs/{run_id}/workspace Get workspace entries
    WS   /ws/events/{run_id}         Real-time event stream
"""

import os
import sys
import shutil
import tempfile
from typing import Any

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

# Add project root to Python path
PROJECT_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".."
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from event_emitter import EventEmitter
from runner import AgentRunner
from schemas import (
    AgentPhase,
    ConfigResponse,
    ConfigUpdate,
    QueryRequest,
    QueryResponse,
    RunResultResponse,
    RunStatus,
    RunStatusResponse,
    UploadResponse,
    WorkspaceEntry,
    WorkspaceResponse,
)


# ── App State ─────────────────────────────────────────────────────────────

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
UPLOAD_DIR = tempfile.mkdtemp(prefix="scout_uploads_")

# Global config state (mutable, shared across runs)
_config_state: dict[str, Any] = {
    "server": "local",
    "model": "venus,deepseek-v3.1-terminus",
    "max_turns": 200,
    "use_planner_agent": True,
    "use_evaluator_agent": True,
    "permission_mode": "dontAsk",
    "tokenizer_model": "deepseek-chat",
    "large_file_token_threshold": 30000,
    "huge_file_token_threshold": 100000,
}


# ── App Factory ───────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app with all routes registered
    """
    app = FastAPI(
        title="Scout Agent UI",
        description="Web interface for the Scout Long Text Understanding Agent",
        version="1.0.0",
    )

    # Initialize event emitter and runner
    emitter = EventEmitter()
    runner = AgentRunner(emitter)

    # Store on app state for access in route handlers
    app.state.emitter = emitter
    app.state.runner = runner

    # ── Static files ──────────────────────────────────────────────────

    @app.get("/", response_class=FileResponse)
    async def serve_index():
        """Serve the main SPA page."""
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    # ── Config endpoints ──────────────────────────────────────────────

    @app.get("/api/config", response_model=ConfigResponse)
    async def get_config():
        """Get current agent configuration."""
        return ConfigResponse(
            server=_config_state.get("server"),
            model=_config_state.get("model"),
            max_turns=_config_state.get("max_turns", 200),
            use_planner_agent=_config_state.get("use_planner_agent", True),
            use_evaluator_agent=_config_state.get("use_evaluator_agent", True),
            permission_mode=_config_state.get("permission_mode", "dontAsk"),
            tokenizer_model=_config_state.get("tokenizer_model", "deepseek-chat"),
            large_file_token_threshold=_config_state.get(
                "large_file_token_threshold", 30000
            ),
            huge_file_token_threshold=_config_state.get(
                "huge_file_token_threshold", 100000
            ),
            available_servers=["tencent", "deepseek", "local"],
        )

    @app.put("/api/config")
    async def update_config(update: ConfigUpdate):
        """Update agent configuration fields.

        Only provided (non-None) fields are updated.
        """
        update_dict = update.model_dump(exclude_none=True)
        _config_state.update(update_dict)
        logger.info(f"Config updated: {update_dict}")
        return {"status": "ok", "updated": list(update_dict.keys())}

    @app.get("/api/config/servers")
    async def list_servers():
        """List available server presets (legacy — config.yaml based now)."""
        return {
            "servers": ["local"],
            "current": _config_state.get("server", "local"),
        }

    # ── File upload ───────────────────────────────────────────────────

    @app.post("/api/upload", response_model=UploadResponse)
    async def upload_file(file: UploadFile = File(...)):
        """Upload a document for the agent to read.

        Saves the file to a temp directory and returns the path.
        """
        # Validate file extension
        allowed_extensions = {
            ".txt",
            ".pdf",
            ".md",
            ".json",
            ".jsonl",
            ".csv",
            ".html",
            ".xml",
            ".log",
        }
        _, ext = os.path.splitext(file.filename or "unknown")
        if ext.lower() not in allowed_extensions:
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(allowed_extensions))}"
                },
            )

        # Save file
        file_path = os.path.join(UPLOAD_DIR, file.filename or "uploaded_file")
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        logger.info(
            f"File uploaded: {file.filename} ({len(content)} bytes) -> {file_path}"
        )

        return UploadResponse(
            file_path=file_path,
            file_name=file.filename or "uploaded_file",
            file_size=len(content),
        )

    # ── Query / Run management ────────────────────────────────────────

    @app.post("/api/query", response_model=QueryResponse)
    async def start_query(request: QueryRequest):
        """Start a new agent query run.

        Returns immediately with a run_id. Connect to /ws/events/{run_id}
        to receive real-time execution events.
        """
        # Build config overrides from current state + request overrides
        config_overrides = dict(_config_state)
        if request.config_overrides:
            config_overrides.update(request.config_overrides)

        run_id = await runner.start_run(
            query=request.query,
            file_path=request.file_path,
            config_overrides=config_overrides,
        )

        logger.info(f"Query started: run_id={run_id}, query={request.query[:100]}...")

        return QueryResponse(run_id=run_id, status=RunStatus.PENDING)

    @app.get("/api/runs/{run_id}/status", response_model=RunStatusResponse)
    async def get_run_status(run_id: str):
        """Get the current status of a run."""
        state = runner.get_run(run_id)
        if not state:
            return JSONResponse(
                status_code=404, content={"error": f"Run {run_id} not found"}
            )

        return RunStatusResponse(
            run_id=run_id,
            status=state.status,
            phase=state.phase,
            current_turn=state.step_counter,
            max_turns=state.max_turns,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            tool_counts=state.tool_counts,
            error=state.error,
        )

    @app.get("/api/runs/{run_id}/result", response_model=RunResultResponse)
    async def get_run_result(run_id: str):
        """Get the final result of a completed run."""
        state = runner.get_run(run_id)
        if not state:
            return JSONResponse(
                status_code=404, content={"error": f"Run {run_id} not found"}
            )

        if state.status not in (RunStatus.COMPLETED, RunStatus.ERROR):
            return JSONResponse(
                status_code=409, content={"error": "Run not yet completed"}
            )

        return RunResultResponse(
            run_id=run_id,
            result=state.result,
            tiktoken_usage=state.tiktoken_usage,
            api_usage=str(state.api_usage) if state.api_usage else None,
            num_turns=state.num_turns,
            tool_usage=state.tool_usage,
        )

    @app.get("/api/runs/{run_id}/workspace", response_model=WorkspaceResponse)
    async def get_run_workspace(run_id: str):
        """Get workspace entries for a run."""
        state = runner.get_run(run_id)
        if not state:
            return JSONResponse(
                status_code=404, content={"error": f"Run {run_id} not found"}
            )

        entries_data = runner.get_workspace_entries(run_id)
        entries = [WorkspaceEntry(**e) for e in entries_data]

        return WorkspaceResponse(run_id=run_id, entries=entries)

    # ── WebSocket ─────────────────────────────────────────────────────

    @app.websocket("/ws/events/{run_id}")
    async def websocket_events(websocket: WebSocket, run_id: str):
        """WebSocket endpoint for real-time run events.

        Clients connect here after starting a query via POST /api/query.
        Events are pushed as JSON messages matching the WSEvent schema.
        """
        await websocket.accept()
        await emitter.subscribe(run_id, websocket)
        logger.info(f"WebSocket connected for run {run_id}")

        try:
            # Keep connection alive until client disconnects
            while True:
                # Wait for any message from client (ping/pong or close)
                data = await websocket.receive_text()
                # Client can send "ping" to keep alive
                if data == "ping":
                    await websocket.send_text('{"type": "pong"}')
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for run {run_id}")
        except Exception as e:
            logger.warning(f"WebSocket error for run {run_id}: {e}")
        finally:
            await emitter.unsubscribe(run_id, websocket)

    # ── Mount static files (must be after all routes) ─────────────────

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


# ── Module-level app instance ─────────────────────────────────────────────

app = create_app()
