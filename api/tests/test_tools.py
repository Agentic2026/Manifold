import pytest
from unittest.mock import AsyncMock, MagicMock
from app.agents.tools.telemetry import (
    get_resource_spikes_impl,
    _extract_cpu_total,
    _extract_memory_bytes,
)


# ────────────────────────────────────────────────────────────
# Unit tests for JSON extraction helpers
# ────────────────────────────────────────────────────────────

def test_extract_cpu_total_nested():
    """cpu_stats = {usage: {total: N}} — standard cAdvisor shape."""
    assert _extract_cpu_total({"usage": {"total": 123456789}}) == 123456789


def test_extract_cpu_total_nested_with_user_system():
    """Verify it extracts total even when user/system keys are present."""
    stats = {"usage": {"total": 500000, "user": 300000, "system": 200000}}
    assert _extract_cpu_total(stats) == 500000


def test_extract_cpu_total_flat_fallback():
    """cpu_stats = {usage: N} — flat numeric fallback."""
    assert _extract_cpu_total({"usage": 42}) == 42


def test_extract_cpu_total_missing():
    """Missing or malformed data returns None."""
    assert _extract_cpu_total({}) is None
    assert _extract_cpu_total({"usage": "not-a-number"}) is None
    assert _extract_cpu_total(None) is None


def test_extract_memory_prefers_working_set():
    """Prefer working_set over usage when both present."""
    stats = {"working_set": 50331648, "usage": 67108864}
    assert _extract_memory_bytes(stats) == 50331648


def test_extract_memory_fallback_to_usage():
    """Fall back to usage when working_set is absent."""
    assert _extract_memory_bytes({"usage": 67108864}) == 67108864


def test_extract_memory_missing():
    assert _extract_memory_bytes({}) is None
    assert _extract_memory_bytes(None) is None


# ────────────────────────────────────────────────────────────
# Integration test for get_resource_spikes_impl using real DB
# (see test_topology.py for full integration tests)
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_tool_get_resource_spikes_empty_db():
    """Empty DB should return 'no spikes' message."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute.return_value = mock_result

    result = await get_resource_spikes_impl(lookback_seconds=300, db=mock_db)
    assert isinstance(result, str)
    assert "No significant resource spikes" in result
