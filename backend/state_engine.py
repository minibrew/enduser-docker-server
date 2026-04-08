from enum import IntEnum


class ProcessState(IntEnum):
    IDLE = 0
    MASH_IN = 24
    MASH_HEATUP = 30
    MASHING = 31
    LAUTERING = 40
    BOILING_HEATUP = 50
    BOILING = 51
    COOLING = 60
    BREW_DONE = 70
    BREW_FAILED = 71
    FERMENTING = 80
    SERVING = 92
    CLEANING = 101
    CLEAN_DONE = 108
    CLEAN_FAILED = 109


PROCESS_STATE_LABELS: dict[int, str] = {
    0: "IDLE",
    24: "MASH_IN",
    30: "MASH_HEATUP",
    31: "MASHING",
    40: "LAUTERING",
    50: "BOILING_HEATUP",
    51: "BOILING",
    60: "COOLING",
    70: "BREW_DONE",
    71: "BREW_FAILED",
    75: "FERMENTING",
    80: "FERMENTING",
    84: "FERMENTING",
    88: "SERVING",
    90: "SERVING",
    91: "SERVING",
    92: "SERVING",
    93: "SERVING",
    101: "CLEANING",
    103: "CLEANING",
    108: "CLEAN_DONE",
    109: "CLEAN_FAILED",
}

PHASES: dict[str, list[int]] = {
    "BREWING": [24, 30, 31, 40, 50, 51, 60, 70, 71],
    "FERMENTATION": [75, 80, 84],
    "SERVING": [88, 90, 91, 92, 93],
    "CLEANING": [101, 103, 108, 109],
}

STATE_TO_PHASE: dict[int, str] = {
    state: phase for phase, states in PHASES.items() for state in states
}

USER_ACTION_LABELS: dict[int, str] = {
    0: "None",
    2: "Prepare cleaning",
    3: "Add cleaning agent",
    4: "Fill water",
    5: "Ready to clean",
    12: "Needs cleaning",
    13: "Needs acid cleaning",
    21: "Start brewing",
    22: "Add ingredients",
    23: "Mash in",
    24: "Heat to mash",
    25: "Mash done",
    26: "Prepare fermentation",
    27: "Cool to fermentation",
    28: "Add yeast",
    30: "Fermentation complete",
    31: "Transfer to serving",
    32: "Start cleaning",
    33: "Rinse",
    34: "Acid clean",
    35: "Sanitize",
    36: "Finished cleaning",
    37: "CIP Finished",
}


def get_phase(state: int) -> str | None:
    return STATE_TO_PHASE.get(state)


def is_failure_state(state: int) -> bool:
    return state in (ProcessState.BREW_FAILED, ProcessState.CLEAN_FAILED)


ALLOWED_COMMANDS_BY_USER_ACTION: dict[int, list[int]] = {
    0: [3],
    12: [2, 3, 32],
    13: [2, 3],
    21: [2, 3],
    22: [2, 3],
    23: [2, 3],
    24: [2, 3],
    25: [2, 3],
    26: [2, 3],
    27: [2, 3],
    28: [2, 3],
    30: [2, 3],
    31: [2, 3],
    32: [2, 3],
    33: [2, 3],
    34: [2, 3],
    35: [2, 3],
    36: [2, 3, 37],
    37: [2, 3],
}


def get_allowed_commands(user_action: int) -> list[int]:
    return ALLOWED_COMMANDS_BY_USER_ACTION.get(user_action, [3])


def build_state_intelligence(state: int, user_action: int = 0, current_state: int = 0) -> dict:
    return {
        "process_state": state,
        "process_label": PROCESS_STATE_LABELS.get(state, "UNKNOWN"),
        "phase": get_phase(state) or "UNKNOWN",
        "is_failure": is_failure_state(state),
        "user_action": user_action,
        "user_action_label": USER_ACTION_LABELS.get(user_action, f"Action {user_action}"),
        "current_state": current_state,
        "allowed_commands": get_allowed_commands(user_action),
    }