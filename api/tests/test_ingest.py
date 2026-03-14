import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from app.main import app

VALID_TOKEN = "test-secret-123"
SAMPLE_PAYLOAD = {
    "schema_version": "1",
    "sent_at": "2024-01-15T12:34:56.789Z",
    "machine_name": "test-node",
    "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
    "samples": [],
}


@pytest.mark.asyncio
async def test_cadvisor_missing_token_returns_401():
    """No Authorization header should yield 401 Unauthorized."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/cadvisor/batch", json=SAMPLE_PAYLOAD)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cadvisor_wrong_token_returns_401():
    """Wrong bearer token should yield 401 Unauthorized."""
    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/cadvisor/batch",
                json=SAMPLE_PAYLOAD,
                headers={"Authorization": "Bearer wrong-token"},
            )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cadvisor_malformed_payload_returns_422():
    """A payload missing required fields should yield 422 Unprocessable Entity."""
    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/cadvisor/batch",
                json={"bad": "payload"},
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
    assert response.status_code == 422
