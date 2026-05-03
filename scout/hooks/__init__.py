"""Scout — Hooks Module

Provides 4 Hooks:
- read_guard: PreToolUse — automatically checks file info before reading
- auto_record_reminder: PostToolUse — reminds to record to workspace after reading
- eval_guard: PostToolUse+Stop — verifies evaluation before stopping
- token_tracker: PostToolUse — automatic token/call statistics
"""

from .read_guard import (
    read_guard,
    reset_cache as reset_read_guard_cache,
    mark_file_checked,
)
from .auto_record_reminder import (
    auto_record_post_hook,
    reset_state as reset_auto_record_state,
)
from .eval_guard import (
    track_evaluate,
    track_reading_tools,
    eval_guard_stop,
    has_evaluated,
    has_used_reading_tools,
    reset_state as reset_eval_guard_state,
)
from .token_tracker import (
    token_tracker_hook,
    get_tracker,
    reset_tracker,
)


def reset_all_hooks():
    """Reset all hook states (for a new session)."""
    reset_read_guard_cache()
    reset_auto_record_state()
    reset_eval_guard_state()
    reset_tracker()


__all__ = [
    # read_guard
    "read_guard",
    "reset_read_guard_cache",
    "mark_file_checked",
    # auto_record_reminder
    "auto_record_post_hook",
    "reset_auto_record_state",
    # eval_guard
    "track_evaluate",
    "track_reading_tools",
    "eval_guard_stop",
    "has_evaluated",
    "has_used_reading_tools",
    "reset_eval_guard_state",
    # token_tracker
    "token_tracker_hook",
    "get_tracker",
    "reset_tracker",
    # utilities
    "reset_all_hooks",
]
