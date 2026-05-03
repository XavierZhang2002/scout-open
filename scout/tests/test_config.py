"""
Scout — tests/test_config.py

Tests for the ScoutConfig class and load_config() function.
"""

import os
import tempfile

import pytest

from scout.config import ScoutConfig, load_config


class TestScoutConfigDefaults:
    """Test default configuration values."""

    def test_default_creation(self, tmp_workspace):
        config = ScoutConfig(cwd=tmp_workspace)
        assert config.cwd == tmp_workspace
        assert config.max_turns == 200
        assert config.permission_mode == "bypassPermissions"
        assert config.use_planner_agent is True
        assert config.use_evaluator_agent is True
        assert config.use_sessions is False

    def test_default_model_none(self):
        config = ScoutConfig(cwd="/tmp/test")
        assert isinstance(config.max_turns, int)

    def test_sandbox_env_set(self):
        config = ScoutConfig(cwd="/tmp/test")
        assert os.environ.get("IS_SANDBOX") == "1"


class TestScoutConfigTools:
    """Test tool lists."""

    def test_allowed_tools(self, default_config):
        allowed = default_config.allowed_tools
        assert "Read" in allowed
        assert "Grep" in allowed
        assert "Glob" in allowed
        assert "TodoWrite" in allowed
        assert "mcp__long_utils__workspace_search" in allowed
        assert "mcp__long_utils__get_file_info" in allowed

    def test_disallowed_tools(self, default_config):
        disallowed = default_config.disallowed_tools
        assert "Bash" in disallowed
        assert "Write" in disallowed
        assert "Edit" in disallowed
        assert "WebFetch" in disallowed


class TestScoutConfigSummary:
    """Test summary output."""

    def test_summary_contains_key_info(self, default_config):
        s = default_config.summary()
        assert "Scout Configuration" in s
        assert "bypassPermissions" in s

    def test_summary_no_crash_with_none_fields(self):
        config = ScoutConfig(cwd="/tmp/test")
        s = config.summary()
        assert isinstance(s, str)
        assert len(s) > 50


class TestScoutConfigOverrides:
    """Test configuration override behavior."""

    def test_explicit_fields(self, tmp_workspace):
        config = ScoutConfig(
            cwd=tmp_workspace,
            base_url="http://custom-url",
            auth_token="test-token",
            model="test-model",
        )
        assert config.base_url == "http://custom-url"
        assert config.auth_token == "test-token"
        assert config.model == "test-model"

    def test_env_dict(self, default_config):
        env = default_config.env_dict
        assert "BASH_DEFAULT_TIMEOUT_MS" in env
        assert "BASH_MAX_TIMEOUT_MS" in env

    def test_workspace_dir_property(self, default_config):
        ws_dir = default_config.workspace_dir
        assert "workspace" in ws_dir


class TestLoadConfig:
    """Test load_config() YAML loading."""

    def test_load_from_yaml(self, tmp_workspace):
        """Test loading from a YAML file."""
        import yaml

        yaml_content = {
            "api": {
                "base_url": "http://test-server:3456",
                "auth_token": "test-token",
                "model": "test,model-name",
            },
            "agent": {
                "max_turns": 100,
                "use_planner": False,
            },
            "tools": {
                "tokenizer_model": "gpt-4",
            },
        }

        yaml_path = os.path.join(tmp_workspace, "test_config.yaml")
        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f)

        config = load_config(yaml_path)
        assert config.base_url == "http://test-server:3456"
        assert config.auth_token == "test-token"
        assert config.model == "test,model-name"
        assert config.max_turns == 100
        assert config.use_planner_agent is False
        assert config.tokenizer_model == "gpt-4"

    def test_load_with_overrides(self, tmp_workspace):
        """Test that keyword overrides take highest priority."""
        import yaml

        yaml_content = {
            "api": {"model": "yaml-model"},
            "agent": {"max_turns": 50},
        }

        yaml_path = os.path.join(tmp_workspace, "test_config.yaml")
        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f)

        config = load_config(yaml_path, model="override-model", max_turns=999)
        assert config.model == "override-model"
        assert config.max_turns == 999

    def test_load_nonexistent_file_uses_defaults(self):
        """Test graceful fallback when yaml doesn't exist."""
        config = load_config("/nonexistent/path/config.yaml")
        assert config.max_turns == 200  # default
        assert config.use_planner_agent is True  # default
