import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from polling_worker import PollingWorker


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.verify = AsyncMock(return_value={
        "brew_clean_idle": [],
        "fermenting": [],
        "serving": [],
        "brew_acid_clean_idle": []
    })
    client.get_sessions = AsyncMock(return_value={"sessions": []})
    client.get_kegs = AsyncMock(return_value={"kegs": []})
    return client


class TestPollingWorker:
    @pytest.mark.asyncio
    async def test_poll_calls_client_methods(self, mock_client):
        worker = PollingWorker(mock_client)
        
        # We need to mock get_state_store and get_event_bus because they are called inside _poll
        with patch("polling_worker.get_state_store") as mock_get_store, \
             patch("polling_worker.get_event_bus") as mock_get_bus:
            
            mock_store = MagicMock()
            mock_get_store.return_value = mock_store
            mock_get_bus.return_value = AsyncMock()
            
            await worker._poll()
            
            mock_client.verify.assert_called_once()
            mock_client.get_sessions.assert_called_once()
            mock_client.get_kegs.assert_called_once()
            mock_store.set_brewery_overview.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_updates_store_with_data(self, mock_client):
        mock_client.verify.return_value = {
            "brew_clean_idle": [{"uuid": "dev1", "process_state": 0, "title": "My Brew"}]
        }
        mock_client.get_sessions.return_value = [{"id": "sess1", "beer_name": "IPA"}]
        
        worker = PollingWorker(mock_client)
        
        with patch("polling_worker.get_state_store") as mock_get_store, \
             patch("polling_worker.get_event_bus") as mock_get_bus:
            
            mock_store = MagicMock()
            mock_get_store.return_value = mock_store
            mock_get_bus.return_value = AsyncMock()
            
            # Setup mock_store.get_selected_device_uuid to return None initially
            mock_store.get_selected_device_uuid.return_value = None
            
            await worker._poll()
            
            # Should select the first device if none selected
            mock_store.select_device.assert_called_with("dev1")
            # Should update session
            mock_store.set_session.assert_called()
