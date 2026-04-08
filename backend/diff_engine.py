from typing import Any


DIFF_FIELDS = ("process_state", "phase", "user_action", "command_state")


def compute_diff(prev: dict[str, Any] | None, curr: dict[str, Any]) -> dict[str, Any] | None:
    if prev is None:
        return curr

    changes = {}
    for field in DIFF_FIELDS:
        prev_val = prev.get(field)
        curr_val = curr.get(field)
        if prev_val != curr_val:
            changes[field] = curr_val

    if changes:
        return {"changed_fields": changes, "snapshot": curr}
    return None


def should_broadcast(prev: dict[str, Any] | None, curr: dict[str, Any]) -> bool:
    return compute_diff(prev, curr) is not None