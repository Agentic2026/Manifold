import json
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_chat_stream_format():
    """Verify that the /llm/chat/stream endpoint returns valid Server-Sent Events."""
    
    # Mock the underlying generator to just yield a predictable dictionary
    async def mock_stream_agent_response(*args, **kwargs):
        yield {"event": "message", "data": json.dumps({"token": "Hello,"})}
        yield {"event": "message", "data": json.dumps({"token": " world!"})}

    with patch("app.routers.dashboard.stream_agent_response", new=mock_stream_agent_response):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/llm/chat/stream", json={"message": "hi", "context": {}})
            
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    
    # The output should be formatted as SSE
    content = response.text
    assert 'event: message' in content
    assert 'data: {"token": "Hello,"}' in content
    assert 'data: {"token": " world!"}' in content
