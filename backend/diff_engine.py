"""
Smart diffing for WebSocket broadcast decisions.

PollingWorker calls breweryoverview every 2 seconds even when nothing has
changed.  compute_diff() compares the previous and current device snapshots
and returns only the fields that actually changed.  should_broadcast()
is a simple True/False wrapper around that result.

Only the four fields most relevant to the operator are compared:
  process_state  – the primary brewing-phase indicator
  phase          – BREWING / FERMENTATION / SERVING / CLEANING
  user_action    – what the operator needs to do next
  command_state  – whether a command is in-flight (used for button enabling)
"""

from typing import Any


# Fields that matter to the operator UI.
# Ignoring temperature, gravity, timestamps, etc. – they change too often
# and would spam the WebSocket without adding value.
DIFF_FIELDS = ("process_state", "phase", "user_action", "command_state")


def compute_diff(prev: dict[str, Any] | None, curr: dict[str, Any]) -> dict[str, Any] | None:
    """
    Compute which operator-relevant fields changed between two device snapshots.

    Args:
        prev:  Previous snapshot (or None on the very first poll).
        curr:  Current snapshot from the latest breweryoverview poll.

    Returns:
        None if no relevant field changed (don't broadcast).
        {"changed_fields": {field: new_value, ...}, "snapshot": curr}
        if at least one field differs.
    """
    if prev is None:
        # First poll – always broadcast so the browser gets a baseline.
        return curr

    changes: dict[str, Any] = {}
    for field in DIFF_FIELDS:
        prev_val = prev.get(field)
        curr_val = curr.get(field)
        if prev_val != curr_val:
            changes[field] = curr_val

    if changes:
        return {"changed_fields": changes, "snapshot": curr}
    return None


def should_broadcast(prev: dict[str, Any] | None, curr: dict[str, Any]) -> bool:
    """
    Returns True if any operator-relevant field differs between the two
    snapshots.  Use this before calling ws_manager.broadcast() to avoid
    spamming connected browsers with identical state.
    """
    return compute_diff(prev, curr) is not None
