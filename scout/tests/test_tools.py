"""
Scout — tests/test_tools.py

Tests for tools/ module: workspace_tools, file_tools.
"""

import os
import tempfile

import pytest

from scout.tools.workspace_tools import (
    create_workspace,
    add_workspace_entry,
    save_workspace,
    load_workspace,
    search_workspace,
    compile_workspace_text,
)
from scout.tools.file_tools import count_tokens, suggest_reading_strategy


class TestWorkspaceCreate:
    """Test workspace creation"""

    def test_create_workspace(self):
        ws = create_workspace("What is X?")
        assert ws["question"] == "What is X?"
        assert len(ws["entries"]) == 0
        assert "id" in ws

    def test_create_workspace_with_default_id(self):
        ws = create_workspace("test")
        # ID format: {md5_hash_8chars}_{timestamp_us}
        assert "_" in ws["id"]
        parts = ws["id"].split("_")
        assert len(parts) == 2
        assert len(parts[0]) == 8  # 8-char md5 prefix


class TestWorkspaceEntries:
    """Test workspace entry management"""

    def test_add_entry_basic(self):
        ws = create_workspace("test")
        ws, msg = add_workspace_entry(ws, "content1", "source1")
        assert len(ws["entries"]) == 1
        assert ws["entries"][0]["content"] == "content1"
        assert ws["entries"][0]["source"] == "source1"
        assert "1 entries" in msg

    def test_add_entry_with_tags(self):
        ws = create_workspace("test")
        ws, _ = add_workspace_entry(
            ws,
            "content",
            "src",
            tags=["tag1", "tag2"],
        )
        assert ws["entries"][0]["tags"] == ["tag1", "tag2"]

    def test_add_entry_with_summary(self):
        ws = create_workspace("test")
        ws, _ = add_workspace_entry(
            ws,
            "content",
            "src",
            summary="Short summary",
        )
        assert ws["entries"][0]["summary"] == "Short summary"

    def test_add_multiple_entries(self):
        ws = create_workspace("test")
        ws, _ = add_workspace_entry(ws, "c1", "s1")
        ws, _ = add_workspace_entry(ws, "c2", "s2")
        ws, msg = add_workspace_entry(ws, "c3", "s3")
        assert len(ws["entries"]) == 3
        assert "3 entries" in msg


class TestWorkspacePersistence:
    """Test workspace save/load"""

    def test_save_load_roundtrip(self, tmp_workspace):
        ws = create_workspace("roundtrip test")
        ws, _ = add_workspace_entry(
            ws,
            "test content",
            "source1",
            tags=["t1"],
        )
        save_workspace(tmp_workspace, ws["id"], ws)
        loaded = load_workspace(tmp_workspace, ws["id"])
        assert loaded["question"] == "roundtrip test"
        assert loaded["entries"][0]["content"] == "test content"
        assert loaded["entries"][0]["tags"] == ["t1"]


class TestWorkspaceSearch:
    """Test workspace search"""

    def test_search_by_keyword(self, sample_workspace):
        result = search_workspace(sample_workspace, keyword="Alice")
        assert result["match_count"] >= 1

    def test_search_by_tag(self, sample_workspace):
        result = search_workspace(sample_workspace, tag="setting")
        assert result["match_count"] == 1

    def test_search_by_tag_character(self, sample_workspace):
        result = search_workspace(sample_workspace, tag="character")
        assert result["match_count"] == 2

    def test_search_no_matches(self, sample_workspace):
        result = search_workspace(sample_workspace, keyword="Nonexistent")
        assert result["match_count"] == 0


class TestWorkspaceCompile:
    """Test workspace compilation"""

    def test_compile_includes_tags(self, sample_workspace):
        text = compile_workspace_text(sample_workspace)
        assert "Tags:" in text

    def test_compile_includes_summary(self, sample_workspace):
        text = compile_workspace_text(sample_workspace)
        assert "Summary:" in text

    def test_compile_includes_content(self, sample_workspace):
        text = compile_workspace_text(sample_workspace)
        assert "Alice" in text


class TestFileTools:
    """Test file tools"""

    def test_count_tokens(self):
        n = count_tokens("Hello world, this is a test.", "deepseek-chat")
        assert 0 < n < 100

    def test_count_tokens_empty(self):
        n = count_tokens("", "deepseek-chat")
        assert n == 0

    def test_suggest_strategy_small_file(self):
        s = suggest_reading_strategy(5000, False)
        assert s["approach"] == "full_read"

    def test_suggest_strategy_medium_needs_norm(self):
        s = suggest_reading_strategy(50000, True)
        assert s["approach"] == "grep_then_read"
        assert any("normalize" in w for w in s["warnings"])

    def test_suggest_strategy_huge_file(self):
        s = suggest_reading_strategy(200000, False)
        assert s["approach"] == "grep_only"
