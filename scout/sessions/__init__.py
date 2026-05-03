"""Scout — Sessions Module

Provides session management capabilities (checkpoint/resume reading).

Disabled by default (ScoutConfig.use_sessions=False), enabled in Sprint 3.
"""

from .session_manager import SessionManager, SessionState

__all__ = [
    "SessionManager",
    "SessionState",
]
