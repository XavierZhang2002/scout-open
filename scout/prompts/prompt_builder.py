"""
Scout — System Prompt Modular Assembler

Assembles system prompt from 11 independent modular files,
assembled on demand via PromptBuilder.

Features:
- Loads module files in a fixed order
- Replaces template variables (e.g., {{env_cwd}}, {{env_time}})
- Dynamically decides which modules to load based on ScoutConfig (e.g., switches evaluation module when SubAgent is disabled)

"""

import os
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import ScoutConfig

PROMPTS_DIR = Path(__file__).parent


class PromptBuilder:
    """System Prompt Modular Assembler."""

    # Default module loading order (all 11 modules)
    DEFAULT_MODULES: List[str] = [
        "base/role.md",
        "base/style.md",
        "base/principles.md",
        "strategy/three_phase.md",
        "strategy/heuristics.md",
        "strategy/anti_patterns.md",
        "tools/planning.md",
        "tools/workspace.md",
        "tools/reading.md",
        "tools/evaluation.md",
        "env.md",
    ]

    def __init__(self, modules: Optional[List[str]] = None):
        """Initialize PromptBuilder.

        Args:
            modules: Custom module list. If not specified, uses DEFAULT_MODULES.
        """
        self.modules = modules or list(self.DEFAULT_MODULES)

    def build(self, variables: Optional[Dict[str, str]] = None) -> str:
        """Assemble the system prompt.

        Args:
            variables: Template variable dictionary, e.g., {"env_cwd": "/path", "env_time": "2026-03-13 10:00:00"}

        Returns:
            Complete system prompt string

        Raises:
            FileNotFoundError: If a module file does not exist
        """
        variables = variables or {}
        sections = []

        for module_path in self.modules:
            full_path = PROMPTS_DIR / module_path
            if not full_path.exists():
                raise FileNotFoundError(
                    f"Prompt module not found: {full_path}\n"
                    f"Available modules in {PROMPTS_DIR}:\n"
                    f"  {list(PROMPTS_DIR.rglob('*.md'))}"
                )

            content = full_path.read_text(encoding="utf-8")

            # Replace template variables {{key}} -> value
            for key, value in variables.items():
                content = content.replace(f"{{{{{key}}}}}", value)

            sections.append(content.strip())

        return "\n\n---\n\n".join(sections)

    def build_with_config(self, config: "ScoutConfig") -> str:
        """Dynamically decide which modules to load based on ScoutConfig.

        Dynamically adjusts module list based on config switches:
        - If Evaluator SubAgent is disabled, replaces evaluation module with fallback version

        Args:
            config: ScoutConfig instance

        Returns:
            Complete system prompt string
        """
        modules = list(self.DEFAULT_MODULES)

        # If Evaluator SubAgent is disabled, replace evaluation module with fallback version
        if not config.use_evaluator_agent:
            try:
                idx = modules.index("tools/evaluation.md")
                modules[idx] = "tools/evaluation_v1_compat.md"
            except ValueError:
                pass  # Module not in list, no replacement needed

        self.modules = modules
        return self.build(
            variables={
                "env_cwd": config.cwd,
                "env_time": config.current_time,
            }
        )

    def list_modules(self) -> List[str]:
        """List the currently configured modules."""
        return list(self.modules)

    def add_module(self, module_path: str, position: Optional[int] = None):
        """Dynamically add a module.

        Args:
            module_path: Module file relative path (e.g., "tools/custom.md")
            position: Insert position (None means append to end)
        """
        if position is not None:
            self.modules.insert(position, module_path)
        else:
            self.modules.append(module_path)

    def remove_module(self, module_path: str):
        """Dynamically remove a module.

        Args:
            module_path: Module file path to remove
        """
        if module_path in self.modules:
            self.modules.remove(module_path)
