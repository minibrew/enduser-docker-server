import pytest
from unittest.mock import AsyncMock, MagicMock
from command_service import CommandService


@pytest.fixture
def mock_session_service():
    svc = MagicMock()
    svc.get_session_cached = MagicMock(return_value=None)
    svc.get_session = AsyncMock(return_value={"user_action": 0})
    svc.send_command = AsyncMock(return_value={"status": "ok"})
    svc.delete_session = AsyncMock(return_value={"status": "deleted"})
    return svc


@pytest.fixture
def command_service(mock_session_service):
    cs = CommandService(client=MagicMock())
    cs.set_session_service(mock_session_service)
    return cs


class TestCommandService:
    @pytest.mark.asyncio
    async def test_execute_session_command_allowed(self, command_service, mock_session_service):
        # user_action 0 allows generic command (type 3)
        mock_session_service.get_session.return_value = {"user_action": 0}
        
        result = await command_service.execute_session_command("sess_123", "NEXT_STEP")
        
        assert result == {"status": "ok"}
        mock_session_service.send_command.assert_called_with("sess_123", 3, None)

    @pytest.mark.asyncio
    async def test_execute_session_command_blocked(self, command_service, mock_session_service):
        # user_action 0 DOES NOT allow CHANGE_TEMPERATURE (type 6)
        mock_session_service.get_session.return_value = {"user_action": 0}
        
        result = await command_service.execute_session_command("sess_123", "CHANGE_TEMPERATURE")
        
        assert "error" in result
        assert "not allowed" in result["error"]
        mock_session_service.send_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_session_command_end_session(self, command_service, mock_session_service):
        # END_SESSION is a special case that calls delete_session
        result = await command_service.execute_session_command("sess_123", "END_SESSION")
        
        assert result == {"status": "deleted"}
        mock_session_service.delete_session.assert_called_with("sess_123")

    @pytest.mark.asyncio
    async def test_execute_session_command_needs_cleaning(self, command_service, mock_session_service):
        # user_action 12 allows generic (3) and START_CLEAN (which we don't have in map but generic is there)
        # Actually in state_engine.py: 12: [2, 3, 32]
        mock_session_service.get_session.return_value = {"user_action": 12}
        
        result = await command_service.execute_session_command("sess_123", "NEXT_STEP")
        assert result == {"status": "ok"}
