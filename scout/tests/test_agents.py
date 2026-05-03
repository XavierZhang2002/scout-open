"""
Scout — tests/test_agents.py

Tests for SubAgent definitions (planner + evaluator).
"""

import pytest

from claude_agent_sdk import AgentDefinition

from scout.agents import planner_agent, evaluator_agent


class TestPlannerAgent:
    """Test Planner SubAgent definition."""

    def test_is_agent_definition(self):
        assert isinstance(planner_agent, AgentDefinition)

    def test_has_description(self):
        assert len(planner_agent.description) > 10

    def test_has_prompt(self):
        assert len(planner_agent.prompt) > 100

    def test_uses_todowrite_tool(self):
        assert "TodoWrite" in planner_agent.tools

    def test_model_is_none(self):
        """model=None means using the same model as the main Agent"""
        assert planner_agent.model is None

    def test_prompt_contains_strategy_guidance(self):
        prompt = planner_agent.prompt
        assert any(
            keyword in prompt for keyword in ["search", "keyword", "strategy"]
        )


class TestEvaluatorAgent:
    """Test Evaluator SubAgent definition."""

    def test_is_agent_definition(self):
        assert isinstance(evaluator_agent, AgentDefinition)

    def test_has_description(self):
        assert len(evaluator_agent.description) > 10

    def test_has_prompt(self):
        assert len(evaluator_agent.prompt) > 100

    def test_uses_workspace_view_tool(self):
        assert "mcp__long_utils__workspace_view" in evaluator_agent.tools

    def test_model_is_none(self):
        assert evaluator_agent.model is None

    def test_prompt_contains_json_format(self):
        assert "JSON" in evaluator_agent.prompt

    def test_prompt_contains_evaluation_rules(self):
        prompt = evaluator_agent.prompt
        assert "is_sufficient" in prompt
        assert "confidence" in prompt
        assert "draft_answer" in prompt
