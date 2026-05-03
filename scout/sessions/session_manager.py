"""
Scout — Session Management Module

Provides checkpoint/resume capabilities for long-running sessions.
- SessionState: Session state snapshot dataclass
- SessionManager: Session lifecycle management (create/resume/complete/interrupt/cleanup)

Disabled by default (ScoutConfig.use_sessions=False), enabled in Sprint 3.

"""

import os
import json
import time
import shutil
import random
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger


# ── Default Session Storage Directory ──────────────────────────────────────

SESSIONS_DIR = Path(__file__).parent / "data"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


# ── SessionState ──────────────────────────────────────────────────────────


@dataclass
class SessionState:
    """Session state snapshot."""

    session_id: str
    query: str  # User's original question
    workspace_id: Optional[str]  # Associated workspace ID
    workspace_dir: str  # Directory where workspace files are stored
    status: str = "active"  # active / completed / interrupted
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    turns_used: int = 0
    max_turns: int = 200
    metadata: dict = field(default_factory=dict)  # Additional metadata

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "query": self.query,
            "workspace_id": self.workspace_id,
            "workspace_dir": self.workspace_dir,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turns_used": self.turns_used,
            "max_turns": self.max_turns,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        """Deserialize from dictionary."""
        return cls(**data)


# ── SessionManager ────────────────────────────────────────────────────────


class SessionManager:
    """Session Manager.

    Responsibilities:
    1. Save/restore session state
    2. Manage workspace directory lifecycle (no longer auto-cleaned)
    3. Support session resumption
    """

    def __init__(self, sessions_dir: Optional[str] = None):
        self.sessions_dir = Path(sessions_dir) if sessions_dir else SESSIONS_DIR
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def create_session(
        self,
        query: str,
        workspace_dir: str,
        max_turns: int = 200,
    ) -> SessionState:
        """Create a new session.

        Args:
            query: User's original question
            workspace_dir: Workspace file directory
            max_turns: Maximum number of turns

        Returns:
            SessionState: Newly created session state
        """
        session_id = (
            f"scout_{int(time.time())}_{os.getpid()}_{random.randint(1000, 9999)}"
        )
        state = SessionState(
            session_id=session_id,
            query=query,
            workspace_id=None,
            workspace_dir=workspace_dir,
            max_turns=max_turns,
        )
        self._save_state(state)
        logger.info(f"Created session: {session_id}")
        return state

    def resume_session(self, session_id: str) -> Optional[SessionState]:
        """Resume a session.

        Args:
            session_id: Session ID to resume

        Returns:
            SessionState or None: Resumed session state, None if not found
        """
        state_file = self.sessions_dir / f"{session_id}.json"
        if not state_file.exists():
            logger.warning(f"Session {session_id} not found")
            return None

        data = json.loads(state_file.read_text(encoding="utf-8"))
        state = SessionState.from_dict(data)
        state.status = "active"
        state.updated_at = time.time()
        self._save_state(state)
        logger.info(f"Resumed session: {session_id}")
        return state

    def update_session(self, state: SessionState, **kwargs):
        """Update session state.

        Args:
            state: Session state object
            **kwargs: Fields to update
        """
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
        state.updated_at = time.time()
        self._save_state(state)

    def complete_session(self, state: SessionState):
        """Mark session as completed."""
        state.status = "completed"
        state.updated_at = time.time()
        self._save_state(state)
        logger.info(f"Completed session: {state.session_id}")

    def interrupt_session(self, state: SessionState):
        """Mark session as interrupted (recoverable)."""
        state.status = "interrupted"
        state.updated_at = time.time()
        self._save_state(state)
        logger.info(f"Interrupted session: {state.session_id}")

    def list_sessions(self, status: Optional[str] = None) -> list[SessionState]:
        """List sessions.

        Args:
            status: Filter by status (None means all)

        Returns:
            List of sessions sorted by update time in descending order
        """
        sessions = []
        for f in self.sessions_dir.glob("scout_*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                state = SessionState.from_dict(data)
                if status is None or state.status == status:
                    sessions.append(state)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Skipping invalid session file {f}: {e}")
                continue
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)

    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Clean up completed sessions older than the retention period.

        Args:
            max_age_hours: Retention period (hours)
        """
        cutoff = time.time() - max_age_hours * 3600
        cleaned = 0

        for state in self.list_sessions(status="completed"):
            if state.updated_at < cutoff:
                # Clean up workspace directory
                if os.path.exists(state.workspace_dir):
                    shutil.rmtree(state.workspace_dir)
                    logger.debug(f"Cleaned workspace: {state.workspace_dir}")

                # Delete session file
                state_file = self.sessions_dir / f"{state.session_id}.json"
                state_file.unlink(missing_ok=True)
                cleaned += 1

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} old sessions (>{max_age_hours}h)")

    def _save_state(self, state: SessionState):
        """Persist session state."""
        state_file = self.sessions_dir / f"{state.session_id}.json"
        state_file.write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
