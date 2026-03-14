import pytest
from unittest.mock import AsyncMock, MagicMock
from app.agents.tools.telemetry import get_resource_spikes_impl

@pytest.mark.asyncio
async def test_agent_tool_get_resource_spikes():
    mock_db = AsyncMock()
    
    # Mock empty DB results
    mock_result_empty = MagicMock()
    mock_result_empty.fetchall.return_value = []
    mock_db.execute.return_value = mock_result_empty
    
    result = await get_resource_spikes_impl(lookback_seconds=300, db=mock_db)
    assert isinstance(result, str)
    assert "No significant resource spikes" in result
    
    # Mock data spike
    mock_row = MagicMock()
    mock_row.reference_name = "/docker/test-1"
    mock_row.cpu_delta = 5000
    mock_row.mem_delta = 20000000
    
    mock_result_data = MagicMock()
    mock_result_data.fetchall.return_value = [mock_row]
    mock_db.execute.return_value = mock_result_data

    result2 = await get_resource_spikes_impl(lookback_seconds=300, db=mock_db)
    assert "Container '/docker/test-1'" in result2
    assert "CPU Delta=5000" in result2
    assert len(result2) < 2000 # Enforce context window friendliness limitation
