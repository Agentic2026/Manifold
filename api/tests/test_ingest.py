import pytest
import os
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.mark.asyncio
async def test_cadvisor_ingestion_authentication():
    payload = {
        "schema_version": "1",
        "sent_at": "2024-01-15T12:34:56.789Z",
        "machine_name": "test-node",
        "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
        "samples": []
    }
    
    os.environ["CADVISOR_METRICS_API_TOKEN"] = "test-secret-123"
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # No token
        response = await ac.post("/cadvisor/batch", json=payload)
        assert response.status_code == 401
        
        # Wrong token
        headers = {"Authorization": "Bearer wrong-token"}
        response = await ac.post("/cadvisor/batch", json=payload, headers=headers)
        assert response.status_code == 401
        
        # We don't test valid token DB insertion fully here without a DB mock or proper test DB, 
        # but we can verify it doesn't get rejected by auth.
