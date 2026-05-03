"""
Scout — tests/test_hooks.py

Tests for the 4 Hook modules' async callbacks and state management.
Uses pytest-asyncio auto mode.
"""

import pytest

from scout.hooks import (
    read_guard,
    auto_record_post_hook,
    track_evaluate,
    track_reading_tools,
    eval_guard_stop,
    token_tracker_hook,
    reset_all_hooks,
    has_evaluated,
    has_used_reading_tools,
    get_tracker,
)


# ── Helper Functions ─────────────────────────────────────────────────────


def _make_post_tool_input(tool_name: str, tool_response: str = "output") -> dict:
    """Construct PostToolUseHookInput."""
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": {},
        "tool_response": tool_response,
        "session_id": "test_session",
        "transcript_path": "/tmp/transcript",
        "cwd": "/tmp",
        "tool_use_id": "test_id",
    }


def _make_pre_tool_input(tool_name: str, tool_input: dict = None) -> dict:
    """Construct PreToolUseHookInput."""
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input or {},
        "session_id": "test_session",
        "transcript_path": "/tmp/transcript",
        "cwd": "/tmp",
        "tool_use_id": "test_id",
    }


def _make_stop_input() -> dict:
    """Construct StopHookInput."""
    return {
        "hook_event_name": "Stop",
        "stop_hook_active": True,
        "session_id": "test_session",
        "transcript_path": "/tmp/transcript",
        "cwd": "/tmp",
    }


_context = {"signal": None}


# ── EvalGuard Tests ──────────────────────────────────────────────────────


class TestEvalGuard:
    """Test eval_guard: track_evaluate + track_reading_tools + eval_guard_stop"""

    async def test_stop_allowed_without_reading_tools(self):
        """Stop hook should allow when no reading tools used (simple problem)"""
        result = await eval_guard_stop(_make_stop_input(), None, _context)
        assert result == {}

    async def test_stop_blocked_after_reading_without_evaluation(self):
        """Stop hook should return continue_=True when reading tools used but not evaluated"""
        # First mark reading tools as used
        await track_reading_tools(
            _make_post_tool_input("Read", "long content"),
            None,
            _context,
        )
        assert has_used_reading_tools() is True

        result = await eval_guard_stop(_make_stop_input(), None, _context)
        assert result.get("continue_") is True
        assert "workspace_evaluate" in result.get("stopReason", "")

    async def test_stop_allowed_after_evaluation(self):
        """After evaluation, Stop hook should return empty dict (allow)"""
        # First use reading tools
        await track_reading_tools(
            _make_post_tool_input("Read", "content"),
            None,
            _context,
        )
        # Then call evaluation
        await track_evaluate(
            _make_post_tool_input("mcp__long_utils__workspace_evaluate"),
            None,
            _context,
        )
        assert has_evaluated() is True

        result = await eval_guard_stop(_make_stop_input(), None, _context)
        assert result == {}

    async def test_track_evaluate_sets_flag(self):
        """Calling workspace_evaluate should set the evaluated flag"""
        assert has_evaluated() is False
        await track_evaluate(
            _make_post_tool_input("mcp__long_utils__workspace_evaluate"),
            None,
            _context,
        )
        assert has_evaluated() is True

    async def test_track_evaluate_with_evaluator_agent(self):
        """Evaluator SubAgent should also set the evaluated flag"""
        await track_evaluate(
            _make_post_tool_input("evaluator"),
            None,
            _context,
        )
        assert has_evaluated() is True

    async def test_track_evaluate_ignores_other_tools(self):
        """Non-evaluation tools should not change state"""
        await track_evaluate(
            _make_post_tool_input("Read"),
            None,
            _context,
        )
        assert has_evaluated() is False

    async def test_track_reading_tools_marks_read(self):
        """Read tool should be marked as reading tool usage"""
        assert has_used_reading_tools() is False
        await track_reading_tools(
            _make_post_tool_input("Read", "content"),
            None,
            _context,
        )
        assert has_used_reading_tools() is True

    async def test_track_reading_tools_marks_grep(self):
        """Grep tool should be marked as reading tool usage"""
        await track_reading_tools(
            _make_post_tool_input("Grep", "matches"),
            None,
            _context,
        )
        assert has_used_reading_tools() is True

    async def test_track_reading_tools_marks_mcp_tools(self):
        """MCP reading tools should be marked as reading tool usage"""
        await track_reading_tools(
            _make_post_tool_input("mcp__long_utils__workspace_update", "ok"),
            None,
            _context,
        )
        assert has_used_reading_tools() is True

    async def test_track_reading_tools_ignores_non_reading(self):
        """Non-reading tools should not be marked"""
        await track_reading_tools(
            _make_post_tool_input("TodoWrite", "ok"),
            None,
            _context,
        )
        assert has_used_reading_tools() is False


# ── AutoRecordReminder Tests ─────────────────────────────────────────────


class TestAutoRecordReminder:
    """Test auto_record_reminder"""

    async def test_reminder_after_read(self):
        """Should inject reminder after Read returns valid content"""
        result = await auto_record_post_hook(
            _make_post_tool_input("Read", "A" * 100),
            None,
            _context,
        )
        assert "hookSpecificOutput" in result
        assert "additionalContext" in result["hookSpecificOutput"]
        assert "workspace_update" in result["hookSpecificOutput"]["additionalContext"]

    async def test_no_reminder_for_short_output(self):
        """Short output should not trigger reminder"""
        result = await auto_record_post_hook(
            _make_post_tool_input("Read", "short"),
            None,
            _context,
        )
        assert result == {}

    async def test_no_reminder_for_no_matches(self):
        """'No matches found' should not trigger reminder"""
        result = await auto_record_post_hook(
            _make_post_tool_input("Grep", "No matches found in the file"),
            None,
            _context,
        )
        assert result == {}

    async def test_workspace_update_clears_pending(self):
        """workspace_update should clear pending record state"""
        result = await auto_record_post_hook(
            _make_post_tool_input("mcp__long_utils__workspace_update"),
            None,
            _context,
        )
        assert result == {}

    async def test_non_read_tool_no_reminder(self):
        """Non Read/Grep tools should not trigger reminder"""
        result = await auto_record_post_hook(
            _make_post_tool_input("TodoWrite", "A" * 200),
            None,
            _context,
        )
        assert result == {}


# ── TokenTracker Tests ───────────────────────────────────────────────────


class TestTokenTracker:
    """Test token_tracker"""

    async def test_records_tool_call(self):
        """Should record tool calls"""
        await token_tracker_hook(
            _make_post_tool_input("Read", "some content here"),
            None,
            _context,
        )
        tracker = get_tracker()
        summary = tracker.summary()
        assert summary["total_tool_calls"] >= 1
        assert "Read" in summary["tool_calls"]

    async def test_records_multiple_tools(self):
        """Should record multiple tools separately"""
        await token_tracker_hook(
            _make_post_tool_input("Read", "content1"),
            None,
            _context,
        )
        await token_tracker_hook(
            _make_post_tool_input("Grep", "content2"),
            None,
            _context,
        )
        tracker = get_tracker()
        summary = tracker.summary()
        assert summary["total_tool_calls"] >= 2
        assert "Read" in summary["tool_calls"]
        assert "Grep" in summary["tool_calls"]

    async def test_records_output_size(self):
        """Should record output size"""
        content = "x" * 500
        await token_tracker_hook(
            _make_post_tool_input("Read", content),
            None,
            _context,
        )
        tracker = get_tracker()
        assert tracker.tool_token_usage.get("Read", 0) >= 500

    async def test_returns_empty_dict(self):
        """token_tracker should not intervene with tool behavior"""
        result = await token_tracker_hook(
            _make_post_tool_input("Read", "content"),
            None,
            _context,
        )
        assert result == {}


# ── ReadGuard Tests ──────────────────────────────────────────────────────


class TestReadGuard:
    """Test read_guard (PreToolUse)"""

    async def test_no_file_path_returns_empty(self):
        """Should allow when no file_path parameter"""
        result = await read_guard(
            _make_pre_tool_input("Read", {}),
            None,
            _context,
        )
        assert result == {}

    async def test_nonexistent_file_returns_empty(self):
        """Should allow when file does not exist (let Read report the error)"""
        result = await read_guard(
            _make_pre_tool_input(
                "Read", {"file_path": "/tmp/definitely_not_exists_xyz.txt"}
            ),
            None,
            _context,
        )
        assert result == {}


# ── Reset Tests ──────────────────────────────────────────────────────────


class TestResetHooks:
    """Test reset_all_hooks"""

    async def test_reset_clears_evaluation_state(self):
        """After reset, evaluation and reading tool flags should be cleared"""
        await track_evaluate(
            _make_post_tool_input("mcp__long_utils__workspace_evaluate"),
            None,
            _context,
        )
        await track_reading_tools(
            _make_post_tool_input("Read", "content"),
            None,
            _context,
        )
        assert has_evaluated() is True
        assert has_used_reading_tools() is True
        reset_all_hooks()
        assert has_evaluated() is False
        assert has_used_reading_tools() is False

    async def test_reset_clears_tracker(self):
        """After reset, tracker statistics should be cleared"""
        await token_tracker_hook(
            _make_post_tool_input("Read", "content"),
            None,
            _context,
        )
        tracker = get_tracker()
        assert tracker.summary()["total_tool_calls"] >= 1
        reset_all_hooks()
        # reset_tracker creates a new instance, need to re-fetch
        new_tracker = get_tracker()
        assert new_tracker.summary()["total_tool_calls"] == 0
