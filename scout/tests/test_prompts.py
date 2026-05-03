"""
Scout — tests/test_prompts.py

Tests for PromptBuilder modular prompt assembly.
"""

import pytest

from scout.prompts.prompt_builder import PromptBuilder
from scout.config import ScoutConfig, load_config


class TestPromptBuilderBuild:
    """Test build() method"""

    def test_build_with_variables(self):
        builder = PromptBuilder()
        prompt = builder.build(
            variables={
                "env_cwd": "/tmp/test",
                "env_time": "2026-03-13 10:00:00",
            }
        )
        assert "/tmp/test" in prompt
        assert "2026-03-13 10:00:00" in prompt
        assert len(prompt) > 500

    def test_build_without_variables(self):
        builder = PromptBuilder()
        prompt = builder.build()
        assert isinstance(prompt, str)
        assert len(prompt) > 400

    def test_build_contains_core_sections(self):
        builder = PromptBuilder()
        prompt = builder.build()
        # Should contain key sections from role, strategy, tools
        assert any(
            keyword in prompt.lower()
            for keyword in ["agent", "reading", "workspace", "plan"]
        )


class TestPromptBuilderWithConfig:
    """Test build_with_config() method"""

    def test_default_config_includes_evaluation(self, tmp_workspace):
        config = ScoutConfig(cwd=tmp_workspace)
        builder = PromptBuilder()
        prompt = builder.build_with_config(config)
        # Default: SubAgents enabled → evaluation.md (not v1_compat)
        assert "evaluator" in prompt.lower() or "agent" in prompt.lower()

    def test_evaluator_off_uses_v1_compat(self, tmp_workspace):
        config = ScoutConfig(cwd=tmp_workspace, use_evaluator_agent=False)
        builder = PromptBuilder()
        prompt = builder.build_with_config(config)
        # Should use fallback evaluation module
        assert "workspace_evaluate" in prompt

    def test_config_injects_cwd_and_time(self, tmp_workspace):
        config = ScoutConfig(cwd=tmp_workspace)
        builder = PromptBuilder()
        prompt = builder.build_with_config(config)
        assert tmp_workspace in prompt


class TestPromptBuilderModules:
    """Test module management features"""

    def test_list_modules(self):
        builder = PromptBuilder()
        modules = builder.list_modules()
        assert len(modules) > 5
        assert "base/role.md" in modules

    def test_remove_module(self):
        builder = PromptBuilder()
        original_count = len(builder.list_modules())
        builder.remove_module("base/principles.md")
        assert len(builder.list_modules()) == original_count - 1

    def test_add_module_back(self):
        builder = PromptBuilder()
        original_count = len(builder.list_modules())
        builder.remove_module("base/principles.md")
        builder.add_module("base/principles.md")
        assert len(builder.list_modules()) == original_count

    def test_remove_nonexistent_module_no_crash(self):
        builder = PromptBuilder()
        original_count = len(builder.list_modules())
        builder.remove_module("nonexistent/module.md")
        assert len(builder.list_modules()) == original_count
