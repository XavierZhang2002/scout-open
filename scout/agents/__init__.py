"""Scout — SubAgents Module

Provides 2 sub-agents:
- planner: Analyzes user questions, formulates search strategies and task decomposition
- evaluator: Reviews workspace information, determines if it is sufficient to answer the question

Both are AgentDefinition instances, registered via ClaudeAgentOptions.agents.
Registration format: agents = {"planner": planner_agent, "evaluator": evaluator_agent}
Can be toggled via ScoutConfig.use_planner_agent / use_evaluator_agent.

"""

from .planner import planner_agent
from .evaluator import evaluator_agent

__all__ = [
    "planner_agent",
    "evaluator_agent",
]
