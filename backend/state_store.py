from typing import Any


class StateStore:
    _instance: "StateStore | None" = None

    def __new__(cls) -> "StateStore":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._sessions: dict[str, dict[str, Any]] = {}
        self._kegs: dict[str, dict[str, Any]] = {}
        self._device_state: dict[str, Any] = {}
        self._command_states: dict[str, str] = {}
        self._initialized = True

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self._sessions.get(session_id)

    def set_session(self, session_id: str, data: dict[str, Any]) -> None:
        self._sessions[session_id] = data

    def list_sessions(self) -> list[dict[str, Any]]:
        return list(self._sessions.values())

    def remove_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def get_keg(self, keg_uuid: str) -> dict[str, Any] | None:
        return self._kegs.get(keg_uuid)

    def set_keg(self, keg_uuid: str, data: dict[str, Any]) -> None:
        self._kegs[keg_uuid] = data

    def list_kegs(self) -> list[dict[str, Any]]:
        return list(self._kegs.values())

    def get_device_state(self, device_id: str = "default") -> dict[str, Any]:
        return self._device_state.get(device_id, {})

    def set_device_state(self, device_id: str, data: dict[str, Any]) -> None:
        self._device_state[device_id] = data

    def get_command_state(self, session_id: str) -> str | None:
        return self._command_states.get(session_id)

    def set_command_state(self, session_id: str, state: str) -> None:
        self._command_states[session_id] = state

    def clear_command_state(self, session_id: str) -> None:
        self._command_states.pop(session_id, None)


def get_state_store() -> StateStore:
    return StateStore()