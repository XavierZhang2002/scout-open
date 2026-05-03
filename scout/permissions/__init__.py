"""Scout — Permissions Module

Provides canUseTool callback for runtime permission checks.
"""

from .permission_callback import create_permission_callback

__all__ = [
    "create_permission_callback",
]
