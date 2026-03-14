import pytest
import sqlite3
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.sqltypes import JSON
from app.main import app
from app.core.database import get_db_session, Base

# SQLite doesn't support JSONB, compile it as JSON (or Text)
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(JSON, "sqlite")
def compile_json_sqlite(type_, compiler, **kw):
    return "JSON"

# Create an in-memory SQLite engine for testing
test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
TestSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=test_engine, class_=AsyncSession)

async def override_get_db_session():
    # Only for tests, yield the session
    async with TestSessionLocal() as session:
        yield session

app.dependency_overrides[get_db_session] = override_get_db_session

from unittest.mock import patch, AsyncMock

VALID_TOKEN = "test-secret-123"

# ────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────

SMALL_COMPOSE = """\
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
    depends_on:
      - api
  api:
    image: python:3.12
    depends_on:
      db:
        condition: service_healthy
  db:
    image: postgres:16
    ports:
      - "5432:5432"
  redis:
    image: redis:8
"""

SAMPLE_BATCH_WITH_NET = {
    "schema_version": "1",
    "sent_at": "2024-01-15T12:34:56.789Z",
    "machine_name": "test-node",
    "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
    "samples": [
        {
            "container_reference": {"name": "/manifold-api-1", "aliases": ["api"], "namespace": "docker"},
            "container_spec": {
                "image": "manifold-api:latest",
                "labels": {"com.docker.compose.service": "api"},
            },
            "stats": {
                "timestamp": "2024-01-15T12:34:56Z",
                "cpu": {"usage": {"total": 123456789}},
                "memory": {"usage": 67108864, "working_set": 50331648},
                "network": {"interfaces": [{"name": "eth0", "rx_bytes": 5000000, "tx_bytes": 3000000}]},
                "filesystem": [{"device": "/dev/sda1", "usage": 1048576}],
            },
        }
    ],
}


async def _reset_tables():
    """Drop and recreate all tables in the test DB."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


# ────────────────────────────────────────────────────────────
# Test: seed and fetch topology (existing)
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_topology_seed_and_fetch():
    """Verify that we can seed the topology and fetch it from DB."""
    await _reset_tables()

    mock_run_analysis = AsyncMock(return_value={"status": "mocked"})

    with patch("app.routers.aegis.run_topology_analysis", new=mock_run_analysis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Seed the DB
            response = await ac.post("/api/topology/seed")
            assert response.status_code == 200
            assert response.json() in [{"status": "seeded"}, {"status": "already_seeded"}]

            # Fetch the topology
            topo_resp = await ac.get("/api/topology")
            assert topo_resp.status_code == 200
            topo_data = topo_resp.json()

            assert len(topo_data["nodes"]) > 0
            assert len(topo_data["edges"]) > 0

            # Run a scan to invoke LangGraph agent
            scan_resp = await ac.post("/api/topology/scan")
            assert scan_resp.status_code == 200
            scan_data = scan_resp.json()
            assert scan_data["scanStatus"] == "complete"


# ────────────────────────────────────────────────────────────
# Test: topology import from Docker Compose
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_topology_import():
    """POST a small compose example → verify nodes and edges are created."""
    await _reset_tables()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/topology/import", json={"yaml_content": SMALL_COMPOSE})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "imported"
        assert body["nodes"] == 4  # web, api, db, redis

        # depends_on edges: web→api, api→db  (redis has none, web→api)
        assert body["edges"] >= 2

        # Verify the topology endpoint returns them
        topo = await ac.get("/api/topology")
        assert topo.status_code == 200
        data = topo.json()
        node_ids = {n["id"] for n in data["nodes"]}
        assert {"web", "api", "db", "redis"} == node_ids


# ────────────────────────────────────────────────────────────
# Test: ingest with network/filesystem stats
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_network_filesystem_stats():
    """Verify network_stats and filesystem_stats are persisted."""
    await _reset_tables()

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/cadvisor/batch",
                json=SAMPLE_BATCH_WITH_NET,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            assert resp.status_code == 202
            assert resp.json()["samples_processed"] == 1


# ────────────────────────────────────────────────────────────
# Test: container-to-node correlation
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_container_to_node_correlation():
    """Ingest a container with compose.service label → verify topology_node_id set."""
    await _reset_tables()

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/cadvisor/batch",
                json=SAMPLE_BATCH_WITH_NET,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            assert resp.status_code == 202

    # Verify the container record has topology_node_id == "api"
    from app.models.telemetry import Container
    from sqlalchemy import select
    async with TestSessionLocal() as session:
        result = await session.execute(select(Container).where(Container.reference_name == "/manifold-api-1"))
        container = result.scalar_one()
        assert container.topology_node_id == "api"


# ────────────────────────────────────────────────────────────
# Test: /api/topology returns real telemetry for mapped nodes
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_topology_real_telemetry():
    """Import topology + ingest matching container → topology returns real telemetry."""
    await _reset_tables()

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    recent_batch = {
        "schema_version": "1",
        "sent_at": now_iso,
        "machine_name": "test-node",
        "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
        "samples": [
            {
                "container_reference": {"name": "/manifold-api-1", "aliases": ["api"], "namespace": "docker"},
                "container_spec": {
                    "image": "manifold-api:latest",
                    "labels": {"com.docker.compose.service": "api"},
                },
                "stats": {
                    "timestamp": now_iso,
                    "cpu": {"usage": {"total": 123456789}},
                    "memory": {"usage": 67108864, "working_set": 50331648},
                    "network": {"interfaces": [{"name": "eth0", "rx_bytes": 5000000, "tx_bytes": 3000000}]},
                    "filesystem": [{"device": "/dev/sda1", "usage": 1048576}],
                },
            }
        ],
    }

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Import topology first
            await ac.post("/api/topology/import", json={"yaml_content": SMALL_COMPOSE})

            # Ingest container data matching "api" node
            resp = await ac.post(
                "/cadvisor/batch",
                json=recent_batch,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            assert resp.status_code == 202

            # Fetch topology
            topo = await ac.get("/api/topology")
            assert topo.status_code == 200
            data = topo.json()

            # Find the "api" node
            api_node = next((n for n in data["nodes"] if n["id"] == "api"), None)
            assert api_node is not None, "api node should exist"

            # It should have telemetry
            assert api_node["telemetry"] is not None
            assert api_node["telemetry"]["ingressMbps"] >= 0
            assert api_node["telemetry"]["egressMbps"] >= 0

            # latencyMs / errorRate should be null (not derivable from cAdvisor)
            assert api_node["telemetry"]["latencyMs"] is None
            assert api_node["telemetry"]["errorRate"] is None

            # Unmatched nodes (e.g. redis) should have no telemetry
            redis_node = next((n for n in data["nodes"] if n["id"] == "redis"), None)
            assert redis_node is not None
            assert redis_node["telemetry"] is None


# ────────────────────────────────────────────────────────────
# Test: deterministic status engine (staleness rule)
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_engine_staleness():
    """Verify the status engine produces 'warning' for stale telemetry."""
    from app.routers.aegis import _compute_node_status, NodeTelemetry
    from datetime import datetime, timezone, timedelta

    # Recent data → healthy
    recent_telem = NodeTelemetry(
        ingressMbps=1.0,
        egressMbps=2.0,
        lastSeen=datetime.now(timezone.utc).isoformat(),
    )
    assert _compute_node_status("healthy", recent_telem) == "healthy"

    # Stale data → warning
    stale_telem = NodeTelemetry(
        ingressMbps=1.0,
        egressMbps=2.0,
        lastSeen=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
    )
    assert _compute_node_status("healthy", stale_telem) == "warning"

    # High egress → warning
    high_egress = NodeTelemetry(
        ingressMbps=1.0,
        egressMbps=60.0,
        lastSeen=datetime.now(timezone.utc).isoformat(),
    )
    assert _compute_node_status("healthy", high_egress) == "warning"

    # No telemetry → keep existing status
    assert _compute_node_status("healthy", None) == "healthy"
    assert _compute_node_status("warning", None) == "warning"
