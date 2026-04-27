import pytest
from state_engine import (
    ALLOWED_COMMANDS_BY_USER_ACTION,
    PHASES,
    get_phase,
    is_failure_state,
    ProcessState,
)


class TestProcessState:
    def test_known_states(self):
        assert ProcessState.IDLE == 0
        assert ProcessState.BREW_DONE == 70
        assert ProcessState.BREW_FAILED == 71
        assert ProcessState.FERMENTING == 80
        assert ProcessState.SERVING == 92

    def test_get_phase_brewing(self):
        assert get_phase(24) == "BREWING"
        assert get_phase(70) == "BREWING"
        assert get_phase(71) == "BREWING"

    def test_get_phase_fermentation(self):
        assert get_phase(75) == "FERMENTATION"
        assert get_phase(80) == "FERMENTATION"

    def test_get_phase_serving(self):
        assert get_phase(88) == "SERVING"
        assert get_phase(92) == "SERVING"

    def test_get_phase_cleaning(self):
        assert get_phase(101) == "CLEANING"
        assert get_phase(108) == "CLEANING"

    def test_get_phase_idle(self):
        assert get_phase(0) is None

    def test_is_failure_state(self):
        assert is_failure_state(71) is True
        assert is_failure_state(84) is True
        assert is_failure_state(93) is True
        assert is_failure_state(109) is True
        assert is_failure_state(70) is False
        assert is_failure_state(80) is False


class TestCommandValidation:
    def test_end_session_always_allowed(self):
        # In this version, allowed commands are types [3], etc.
        allowed = ALLOWED_COMMANDS_BY_USER_ACTION.get(0, [])
        assert 3 in allowed

    def test_needs_cleaning_allows_clean_commands(self):
        allowed = ALLOWED_COMMANDS_BY_USER_ACTION.get(12, [])
        assert 32 in allowed  # START_CLEAN type or similar
        assert 3 in allowed   # generic

    def test_start_brewing_allows_generic(self):
        allowed = ALLOWED_COMMANDS_BY_USER_ACTION.get(21, [])
        assert 3 in allowed
        assert 32 not in allowed # CLEANING not allowed during START_BREWING
