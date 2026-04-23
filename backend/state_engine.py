"""
Decodes raw MiniBrew numerical codes into human-readable labels.

Maps:
  - ProcessState codes  → descriptive string (e.g. 31 → "MASHING")
  - UserAction codes    → operator-facing instruction (e.g. 12 → "Needs cleaning")
  - ProcessState codes   → high-level phase (e.g. 31 → "BREWING")
  - ProcessState codes   → failure flag (71, 84, 93, 109 = FAIL)
  - UserAction codes     → which command types are allowed at each step

These maps are derived from the MiniBrew API specification and real
device observations. Unknown codes render as "X (NULL)" in red on the UI.
"""

from enum import IntEnum


# ---------------------------------------------------------------------
# ProcessState – canonical integer codes returned as process_state
# on breweryoverview and v1/devices.  Used for display labels and
# phase detection.
# ---------------------------------------------------------------------

class ProcessState(IntEnum):
    """MiniBrew process state codes as an IntEnum for type safety."""
    IDLE              = 0
    MASH_IN            = 24
    MASH_HEATUP        = 30
    MASHING            = 31
    LAUTERING          = 40
    BOILING_HEATUP     = 50
    BOILING            = 51
    COOLING            = 60
    BREW_DONE           = 70
    BREW_FAILED         = 71   # FAIL: bad mash, stuck sparge, etc.
    FERMENTING          = 80
    SERVING             = 92
    CLEANING            = 101
    CLEAN_DONE          = 108
    CLEAN_FAILED         = 109  # FAIL: CIP did not complete


# Maps every known process_state integer to a short uppercase label.
# Codes not in this map display as "X (NULL)" in red on the dashboard.
PROCESS_STATE_LABELS: dict[int, str] = {
    0:  "IDLE",
    5:  "MANUAL_CONTROL",
    6:  "PREPARE_RINSE",
    7:  "CHECK_KEG",
    8:  "CHECK_WATER",
    10: "PUMP_PRIMING",
    11: "CHECK_FLOW",
    12: "HEATUP_RINSE",
    13: "CLEAN_BALL_VALVE",
    14: "RINSE_BOILING_PATH",
    15: "RINSE_MASHING_PATH",
    16: "RINSE_DONE",
    17: "FILL_MACHINE",
    18: "RINSE_COOL",
    24: "MASH_IN",
    30: "MASH_HEATUP",
    31: "MASHING",
    39: "SPARGING",
    40: "LAUTERING",
    43: "REPLACE_MASH",
    50: "BOILING_HEATUP",
    51: "BOILING",
    52: "SECONDARY_LAUTERING",
    59: "CONNECT_WATER",
    60: "COOL_WORT",
    70: "BREW_DONE",
    71: "BREW_FAILED",
    74: "PITCH_COOLING",
    75: "PREPARE_FERMENTATION",
    76: "PLACE_AIRLOCK",
    77: "REMOVE_AIRLOCK",
    78: "PLACE_TRUB_CONTAINER",
    80: "FERMENTATION_TEMP_CONTROL",
    81: "REMOVE_TRUB",
    82: "FERMENTATION_ADD_INGREDIENT",
    83: "FERMENTATION_REMOVE_INGREDIENT",
    84: "FERMENTATION_FAILED",
    88: "PREPARE_SERVING",
    90: "COOL_BEFORE_SERVING",
    91: "MOUNT_TAP",
    92: "SERVING_TEMP_CONTROL",
    93: "SERVING_FAILED",
    101: "PREPARE_CIP",
    103: "BACKFLUSH",
    108: "CIP_DONE",
    109: "CIP_FAILED",
    111: "CIRCULATE_BOILING_PATH",
    112: "CIRCULATE_MASHING_PATH",
    113: "RINSE_COUNTERFLOW_BOIL",
    114: "RINSE_COUNTERFLOW_MASHTUN",
}


# ---------------------------------------------------------------------
# Phases – high-level groupings of process states.
# Used in the header to show which part of the workflow the device is in.
# ---------------------------------------------------------------------

PHASES: dict[str, list[int]] = {
    "BREWING":      [24, 30, 31, 39, 40, 43, 50, 51, 52, 59, 60, 70, 71, 74],
    "FERMENTATION": [75, 76, 77, 78, 80, 81, 82, 83, 84],
    "SERVING":      [88, 90, 91, 92, 93],
    "CLEANING":     [101, 103, 108, 109, 111, 112, 113, 114],
}

# Inverted index: process_state → phase name.
STATE_TO_PHASE: dict[int, str] = {
    state: phase for phase, states in PHASES.items() for state in states
}


# ---------------------------------------------------------------------
# UserAction – operator prompts surfaced by the MiniBrew device.
# Controls which command buttons are enabled on the dashboard at any time.
# ---------------------------------------------------------------------

USER_ACTION_LABELS: dict[int, str] = {
    0:  "None",
    2:  "Prepare cleaning",
    3:  "Add cleaning agent",
    4:  "Fill water",
    5:  "Ready to clean",
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


# ---------------------------------------------------------------------
# Command-type authorisation.
# Maps each user_action to the list of command_type integers that are
# safe to dispatch at that step.  CommandService.execute_session_command
# checks this before sending anything to the MiniBrew API.
#
#   command_type values:
#     2 = wake_device   – power on / wake the machine
#     3 = generic_command – NEXT_STEP, BYPASS, GO_TO_MASH, etc.
#     6 = update_recipe – CHANGE_TEMPERATURE (sends serving_temperature)
# ---------------------------------------------------------------------

ALLOWED_COMMANDS_BY_USER_ACTION: dict[int, list[int]] = {
    0:  [3],         # IDLE: only generic commands allowed
    12: [2, 3, 32],  # Needs cleaning: can wake, generic, or start clean
    13: [2, 3],      # Needs acid cleaning: wake + generic
    21: [2, 3],      # Start brewing
    22: [2, 3],      # Add ingredients
    23: [2, 3],      # Mash in
    24: [2, 3],      # Heat to mash
    25: [2, 3],      # Mash done
    26: [2, 3],      # Prepare fermentation
    27: [2, 3],      # Cool to fermentation
    28: [2, 3],      # Add yeast
    30: [2, 3],      # Fermentation complete
    31: [2, 3],      # Transfer to serving
    32: [2, 3],      # Start cleaning
    33: [2, 3],      # Rinse
    34: [2, 3],      # Acid clean
    35: [2, 3],      # Sanitize
    36: [2, 3, 37],  # Finished cleaning: + CIP finished command
    37: [2, 3],      # CIP Finished
}


# ---------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------

def get_phase(state: int) -> str | None:
    """Return the high-level phase name for a process_state, or None."""
    return STATE_TO_PHASE.get(state)


def is_failure_state(state: int) -> bool:
    """
    Return True for known failure state codes.
    These render with a red FAIL: prefix on the dashboard.
    """
    return state in (
        ProcessState.BREW_FAILED,
        84,   # FERMENTATION_FAILED (not in the IntEnum)
        93,   # SERVING_FAILED (not in the IntEnum but observed)
        ProcessState.CLEAN_FAILED,
    )


def get_allowed_commands(user_action: int) -> list[int]:
    """
    Return the list of command_type integers that are safe to dispatch
    when the device is prompting the given user_action.
    Falls back to [3] (generic_command) for unknown user_action values.
    """
    return ALLOWED_COMMANDS_BY_USER_ACTION.get(user_action, [3])


def build_state_intelligence(
    state: int,
    user_action: int = 0,
    current_state: int = 0,
) -> dict:
    """
    Assemble a complete intelligence dict from raw MiniBrew fields.

    This is what the frontend's Device Info panel renders — all the
    human-readable labels computed server-side so the browser doesn't
    need to know the raw codes.

    Args:
        state:         process_state from breweryoverview or v1/devices
        user_action:   user_action from breweryoverview or v1/devices
        current_state: current_state from v1/devices (may differ from
                       process_state during transitional states)

    Returns:
        {
            process_state, process_label, phase, is_failure,
            user_action, user_action_label, current_state, allowed_commands
        }
    """
    return {
        "process_state":      state,
        "process_label":      PROCESS_STATE_LABELS.get(state, "UNKNOWN"),
        "phase":              get_phase(state) or "UNKNOWN",
        "is_failure":         is_failure_state(state),
        "user_action":        user_action,
        "user_action_label":  USER_ACTION_LABELS.get(user_action, f"Action {user_action}"),
        "current_state":      current_state,
        "allowed_commands":   get_allowed_commands(user_action),
    }
