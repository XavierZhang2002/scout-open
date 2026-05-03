"""
Scout — tests/test_permissions.py

Tests for permission_callback path safety checks.
"""

import pytest

from scout.config import ScoutConfig, load_config
from scout.permissions.permission_callback import create_permission_callback


class TestPermissionCallbackRead:
    """Test path checks for Read/Grep/Glob tools"""

    def test_allows_safe_path(self, tmp_workspace):
        config = ScoutConfig(cwd=tmp_workspace)
        cb = create_permission_callback(config)
        result = cb("Read", {"file_path": f"{tmp_workspace}/data.txt"})
        assert result["type"] == "allow"

    def test_denies_unsafe_path(self, tmp_workspace):
        config = ScoutConfig(cwd=tmp_workspace)
        cb = create_permission_callback(config)
        result = cb("Read", {"file_path": "/etc/passwd"})
        assert result["type"] == "deny"

    def test_denies_traversal_attack(self, tmp_workspace):
        config = ScoutConfig(cwd=tmp_workspace)
        cb = create_permission_callback(config)
        result = cb("Read", {"file_path": f"{tmp_workspace}/../../../etc/passwd"})
        assert result["type"] == "deny"

    def test_allows_grep_safe_path(self, tmp_workspace):
        config = ScoutConfig(cwd=tmp_workspace)
        cb = create_permission_callback(config)
        result = cb("Grep", {"file_path": f"{tmp_workspace}/search_dir"})
        assert result["type"] == "allow"

    def test_allows_glob_safe_path(self, tmp_workspace):
        config = ScoutConfig(cwd=tmp_workspace)
        cb = create_permission_callback(config)
        result = cb("Glob", {"file_path": f"{tmp_workspace}/pattern"})
        assert result["type"] == "allow"


class TestPermissionCallbackMCP:
    """Test path checks for MCP tools"""

    def test_allows_get_file_info_safe(self, tmp_workspace):
        config = ScoutConfig(cwd=tmp_workspace)
        cb = create_permission_callback(config)
        result = cb(
            "mcp__long_utils__get_file_info",
            {"file_path": f"{tmp_workspace}/doc.txt"},
        )
        assert result["type"] == "allow"

    def test_denies_normalize_unsafe(self, tmp_workspace):
        config = ScoutConfig(cwd=tmp_workspace)
        cb = create_permission_callback(config)
        result = cb(
            "mcp__long_utils__normalize_document",
            {"file_path": "/home/user/doc.txt"},
        )
        assert result["type"] == "deny"

    def test_allows_non_path_tools(self, tmp_workspace):
        config = ScoutConfig(cwd=tmp_workspace)
        cb = create_permission_callback(config)
        result = cb("TodoWrite", {"todos": []})
        assert result["type"] == "allow"


class TestPermissionCallbackNoCwd:
    """Test permissive mode when cwd is empty"""

    def test_allows_when_no_cwd(self):
        config = ScoutConfig(cwd="")
        cb = create_permission_callback(config)
        result = cb("Read", {"file_path": "/anywhere/file.txt"})
        assert result["type"] == "allow"
