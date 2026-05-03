"""
Scout — Unified Configuration Module

Loads configuration from config.yaml at the project root.
Priority: config.yaml > environment variables > defaults.

Usage:
    from scout.config import load_config

    config = load_config()                      # auto-discover config.yaml
    config = load_config("/path/to/config.yaml")  # explicit path
"""

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


# -- Project root discovery ----------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent


def _find_config_file(explicit_path: Optional[str] = None) -> Optional[Path]:
    """Locate config.yaml using priority order:
    1. Explicit path argument
    2. SCOUT_CONFIG env var
    3. ./config.yaml (project root)
    """
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return p

    env_path = os.getenv("SCOUT_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    default = PROJECT_ROOT / "config.yaml"
    if default.exists():
        return default

    return None


def _load_yaml(path: Path) -> dict:
    """Load and parse a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


# -- ScoutConfig dataclass -----------------------------------------------------


@dataclass
class ScoutConfig:
    """Scout unified configuration.

    All fields have sensible defaults. Call load_config() to populate from
    config.yaml automatically.
    """

    # -- Working directory & environment --
    cwd: str = ""
    current_time: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    )

    # -- API connection --
    base_url: Optional[str] = None
    auth_token: Optional[str] = None
    model: Optional[str] = None

    # -- Evaluation LLM (fallback when Evaluator SubAgent is off) --
    eval_api_key: Optional[str] = None
    eval_api_base_url: Optional[str] = None
    eval_model: Optional[str] = None

    # -- Agent behavior --
    max_turns: int = 200
    use_planner_agent: bool = True
    use_evaluator_agent: bool = True
    permission_mode: str = "bypassPermissions"

    # -- Tool parameters --
    tokenizer_model: str = "deepseek-chat"
    large_file_token_threshold: int = 30000
    huge_file_token_threshold: int = 100000
    line_max_length: int = 2000

    # -- Pricing --
    price_input_per_token: float = 0.0
    price_output_per_token: float = 0.0

    # -- Session (reserved for future use) --
    use_sessions: bool = False
    session_data_dir: str = field(
        default_factory=lambda: str(
            Path(__file__).parent / "sessions" / "data"
        )
    )
    session_max_age_hours: int = 24

    # -- Logging --
    log_dir: str = field(
        default_factory=lambda: str(Path(__file__).parent / "logs")
    )
    log_level: str = "DEBUG"

    # -- Bash timeout --
    bash_default_timeout_ms: str = "7200000"
    bash_max_timeout_ms: str = "7200000"

    def __post_init__(self):
        """Sync critical env vars for Claude Agent SDK usage."""
        os.environ["IS_SANDBOX"] = "1"

        if self.base_url:
            os.environ.setdefault("ANTHROPIC_BASE_URL", self.base_url)
        if self.auth_token:
            os.environ.setdefault("ANTHROPIC_AUTH_TOKEN", self.auth_token)
        if self.model:
            os.environ.setdefault("ANTHROPIC_MODEL", self.model)
        if self.eval_api_key:
            os.environ.setdefault("EVAL_API_KEY", self.eval_api_key)
        if self.eval_api_base_url:
            os.environ.setdefault("EVAL_API_BASE_URL", self.eval_api_base_url)
        if self.eval_model:
            os.environ.setdefault("EVAL_MODEL", self.eval_model)

    # -- Convenience properties --

    @property
    def workspace_dir(self) -> str:
        return str(Path(__file__).parent / "workspace")

    @property
    def env_dict(self) -> dict:
        """Dict passed to ClaudeAgentOptions.env."""
        return {
            "BASH_DEFAULT_TIMEOUT_MS": self.bash_default_timeout_ms,
            "BASH_MAX_TIMEOUT_MS": self.bash_max_timeout_ms,
        }

    @property
    def allowed_tools(self) -> list[str]:
        return [
            "Read",
            "Glob",
            "Grep",
            "TodoWrite",
            "mcp__long_utils__get_file_info",
            "mcp__long_utils__normalize_document",
            "mcp__long_utils__workspace_update",
            "mcp__long_utils__workspace_view",
            "mcp__long_utils__workspace_search",
            "mcp__long_utils__workspace_evaluate",
        ]

    @property
    def disallowed_tools(self) -> list[str]:
        return [
            "WebFetch",
            "WebSearch",
            "Bash",
            "BashOutput",
            "KillBash",
            "KillShell",
            "Skill",
            "MultiEdit",
            "SlashCommand",
            "Task",
            "NotebookEdit",
            "ExitPlanMode",
            "Write",
            "Edit",
        ]

    def summary(self) -> str:
        """Configuration summary for logging."""
        lines = [
            "=== Scout Configuration ===",
            f"  base_url:            {self.base_url}",
            f"  model:               {self.model}",
            f"  cwd:                 {self.cwd}",
            f"  permission_mode:     {self.permission_mode}",
            f"  max_turns:           {self.max_turns}",
            f"  use_planner_agent:   {self.use_planner_agent}",
            f"  use_evaluator_agent: {self.use_evaluator_agent}",
            f"  use_sessions:        {self.use_sessions}",
            f"  eval_model:          {self.eval_model}",
            f"  tokenizer_model:     {self.tokenizer_model}",
            f"  log_level:           {self.log_level}",
            "============================",
        ]
        return "\n".join(lines)


# -- Public API: load_config() -------------------------------------------------


def load_config(
    config_path: Optional[str] = None,
    **overrides,
) -> ScoutConfig:
    """Load Scout configuration from YAML file with env var fallbacks.

    Args:
        config_path: Path to config.yaml. If None, auto-discovers.
        **overrides: Keyword arguments that override YAML/env values.

    Returns:
        A populated ScoutConfig instance.
    """
    # 1. Start with defaults
    kwargs: dict = {}

    # 2. Load from YAML if available
    yaml_path = _find_config_file(config_path)
    if yaml_path:
        data = _load_yaml(yaml_path)

        # Map YAML structure to flat ScoutConfig fields
        api = data.get("api", {})
        if api.get("base_url"):
            kwargs["base_url"] = api["base_url"]
        if api.get("auth_token"):
            kwargs["auth_token"] = api["auth_token"]
        if api.get("model"):
            kwargs["model"] = api["model"]

        eval_cfg = data.get("eval", {})
        if eval_cfg.get("api_key"):
            kwargs["eval_api_key"] = eval_cfg["api_key"]
        if eval_cfg.get("base_url"):
            kwargs["eval_api_base_url"] = eval_cfg["base_url"]
        if eval_cfg.get("model"):
            kwargs["eval_model"] = eval_cfg["model"]

        agent = data.get("agent", {})
        if "max_turns" in agent:
            kwargs["max_turns"] = agent["max_turns"]
        if "use_planner" in agent:
            kwargs["use_planner_agent"] = agent["use_planner"]
        if "use_evaluator" in agent:
            kwargs["use_evaluator_agent"] = agent["use_evaluator"]
        if "permission_mode" in agent:
            kwargs["permission_mode"] = agent["permission_mode"]

        tools = data.get("tools", {})
        if "tokenizer_model" in tools:
            kwargs["tokenizer_model"] = tools["tokenizer_model"]
        if "large_file_token_threshold" in tools:
            kwargs["large_file_token_threshold"] = tools["large_file_token_threshold"]
        if "huge_file_token_threshold" in tools:
            kwargs["huge_file_token_threshold"] = tools["huge_file_token_threshold"]
        if "line_max_length" in tools:
            kwargs["line_max_length"] = tools["line_max_length"]

        pricing = data.get("pricing", {})
        if "input_per_token" in pricing:
            kwargs["price_input_per_token"] = pricing["input_per_token"]
        if "output_per_token" in pricing:
            kwargs["price_output_per_token"] = pricing["output_per_token"]

    # 3. Environment variable fallbacks (for fields still unset)
    if "base_url" not in kwargs:
        env_val = os.getenv("ANTHROPIC_BASE_URL")
        if env_val:
            kwargs["base_url"] = env_val
    if "auth_token" not in kwargs:
        env_val = os.getenv("ANTHROPIC_AUTH_TOKEN")
        if env_val:
            kwargs["auth_token"] = env_val
    if "model" not in kwargs:
        env_val = os.getenv("ANTHROPIC_MODEL")
        if env_val:
            kwargs["model"] = env_val
    if "eval_api_key" not in kwargs:
        env_val = os.getenv("EVAL_API_KEY")
        if env_val:
            kwargs["eval_api_key"] = env_val
    if "eval_api_base_url" not in kwargs:
        env_val = os.getenv("EVAL_API_BASE_URL")
        if env_val:
            kwargs["eval_api_base_url"] = env_val
    if "eval_model" not in kwargs:
        env_val = os.getenv("EVAL_MODEL")
        if env_val:
            kwargs["eval_model"] = env_val

    # 4. Apply explicit overrides (highest priority)
    kwargs.update(overrides)

    return ScoutConfig(**kwargs)
