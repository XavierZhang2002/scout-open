"""
Scout — Pytest Shared Fixtures

Provides common fixtures: temporary directories, config, workspace, etc.
"""

import os
import sys
import tempfile

import pytest

# Ensure project root is in sys.path so `from scout.xxx` works
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Also add scout/ itself for backward-compatible test imports
SCOUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCOUT_DIR not in sys.path:
    sys.path.insert(0, SCOUT_DIR)


@pytest.fixture
def tmp_workspace():
    """Provide temporary workspace directory, auto-cleanup after test."""
    with tempfile.TemporaryDirectory(prefix="scout_test_") as tmpdir:
        yield tmpdir


@pytest.fixture
def default_config(tmp_workspace):
    """Provide a default ScoutConfig instance."""
    from scout.config import ScoutConfig

    return ScoutConfig(cwd=tmp_workspace)


@pytest.fixture
def sample_workspace():
    """Provide pre-populated workspace for search/compile tests."""
    from scout.tools.workspace_tools import create_workspace, add_workspace_entry

    ws = create_workspace("What happened in chapter 1?")
    ws, _ = add_workspace_entry(
        ws,
        "Alice went to the store to buy groceries.",
        "chapter1:line10",
        tags=["character", "alice"],
        summary="Alice goes shopping",
    )
    ws, _ = add_workspace_entry(
        ws,
        "Bob met Alice at the park and they talked about the weather.",
        "chapter1:line25",
        tags=["character", "bob", "alice"],
        summary="Bob and Alice meet",
    )
    ws, _ = add_workspace_entry(
        ws,
        "The sun was shining brightly on the village square.",
        "chapter1:line40",
        tags=["setting"],
        summary="Weather description",
    )
    return ws


@pytest.fixture(autouse=True)
def reset_hooks_state():
    """Reset all hook state before each test."""
    from scout.hooks import reset_all_hooks

    reset_all_hooks()
    yield
    reset_all_hooks()
