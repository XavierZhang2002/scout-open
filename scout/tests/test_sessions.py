"""
Scout — tests/test_sessions.py

Tests for SessionManager and SessionState.
"""

import pytest

from scout.sessions.session_manager import SessionManager, SessionState


class TestSessionState:
    """Test SessionState serialization"""

    def test_to_dict(self):
        state = SessionState(
            session_id="test_123",
            query="what is X?",
            workspace_id="ws_001",
            workspace_dir="/tmp/ws",
            turns_used=42,
        )
        d = state.to_dict()
        assert d["session_id"] == "test_123"
        assert d["turns_used"] == 42
        assert d["status"] == "active"

    def test_from_dict(self):
        data = {
            "session_id": "test_456",
            "query": "test query",
            "workspace_id": None,
            "workspace_dir": "/tmp/ws",
            "status": "completed",
            "created_at": 1000.0,
            "updated_at": 2000.0,
            "turns_used": 10,
            "max_turns": 100,
            "metadata": {"key": "value"},
        }
        state = SessionState.from_dict(data)
        assert state.session_id == "test_456"
        assert state.status == "completed"
        assert state.metadata == {"key": "value"}

    def test_roundtrip(self):
        original = SessionState(
            session_id="rt_001",
            query="roundtrip test",
            workspace_id="ws_rt",
            workspace_dir="/tmp/rt",
            turns_used=5,
        )
        restored = SessionState.from_dict(original.to_dict())
        assert restored.session_id == original.session_id
        assert restored.query == original.query
        assert restored.turns_used == original.turns_used


class TestSessionManager:
    """Test SessionManager lifecycle management"""

    def test_create_session(self, tmp_workspace):
        mgr = SessionManager(sessions_dir=tmp_workspace)
        state = mgr.create_session("test query", "/tmp/ws", max_turns=100)
        assert state.query == "test query"
        assert state.status == "active"
        assert state.max_turns == 100

    def test_resume_session(self, tmp_workspace):
        mgr = SessionManager(sessions_dir=tmp_workspace)
        state = mgr.create_session("resume test", "/tmp/ws")
        resumed = mgr.resume_session(state.session_id)
        assert resumed is not None
        assert resumed.query == "resume test"
        assert resumed.status == "active"

    def test_resume_nonexistent_returns_none(self, tmp_workspace):
        mgr = SessionManager(sessions_dir=tmp_workspace)
        result = mgr.resume_session("nonexistent_session")
        assert result is None

    def test_complete_session(self, tmp_workspace):
        mgr = SessionManager(sessions_dir=tmp_workspace)
        state = mgr.create_session("complete test", "/tmp/ws")
        mgr.complete_session(state)
        assert state.status == "completed"

    def test_interrupt_session(self, tmp_workspace):
        mgr = SessionManager(sessions_dir=tmp_workspace)
        state = mgr.create_session("interrupt test", "/tmp/ws")
        mgr.interrupt_session(state)
        assert state.status == "interrupted"

    def test_list_sessions_by_status(self, tmp_workspace):
        mgr = SessionManager(sessions_dir=tmp_workspace)
        s1 = mgr.create_session("q1", "/tmp/ws1")
        s2 = mgr.create_session("q2", "/tmp/ws2")
        mgr.complete_session(s1)

        active = mgr.list_sessions(status="active")
        completed = mgr.list_sessions(status="completed")
        assert len(active) == 1
        assert len(completed) == 1
        assert active[0].query == "q2"
        assert completed[0].query == "q1"

    def test_list_all_sessions(self, tmp_workspace):
        mgr = SessionManager(sessions_dir=tmp_workspace)
        mgr.create_session("q1", "/tmp/ws1")
        mgr.create_session("q2", "/tmp/ws2")
        all_sessions = mgr.list_sessions()
        assert len(all_sessions) == 2

    def test_update_session(self, tmp_workspace):
        mgr = SessionManager(sessions_dir=tmp_workspace)
        state = mgr.create_session("update test", "/tmp/ws")
        mgr.update_session(state, turns_used=42, workspace_id="ws_updated")
        assert state.turns_used == 42
        assert state.workspace_id == "ws_updated"
