import pytest
import sqlite3
from datetime import datetime, timezone
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
                "labels": {
                    "com.docker.compose.service": "api",
                    "com.docker.compose.project": "manifold",
                },
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
            response = await ac.post("/topology/seed")
            assert response.status_code == 200
            assert response.json() in [{"status": "seeded"}, {"status": "already_seeded"}]

            # Fetch the topology
            topo_resp = await ac.get("/topology")
            assert topo_resp.status_code == 200
            topo_data = topo_resp.json()

            assert len(topo_data["nodes"]) > 0
            assert len(topo_data["edges"]) > 0

            # Run a scan to invoke LangGraph agent
            scan_resp = await ac.post("/topology/scan")
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
        resp = await ac.post("/topology/import", json={"yaml_content": SMALL_COMPOSE})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "imported"
        assert body["nodes"] == 4  # web, api, db, redis

        # depends_on edges: web→api, api→db  (redis has none, web→api)
        assert body["edges"] >= 2

        # Verify the topology endpoint returns them
        topo = await ac.get("/topology")
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

    # Verify the container record has project-scoped topology_node_id
    from app.models.telemetry import Container
    from sqlalchemy import select
    async with TestSessionLocal() as session:
        result = await session.execute(select(Container).where(Container.reference_name == "/manifold-api-1"))
        container = result.scalar_one()
        assert container.topology_node_id == "manifold__api"


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
            await ac.post("/topology/import", json={"yaml_content": SMALL_COMPOSE})

            # Ingest container data matching "api" node
            resp = await ac.post(
                "/cadvisor/batch",
                json=recent_batch,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            assert resp.status_code == 202

            # Fetch topology
            topo = await ac.get("/topology")
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


# ────────────────────────────────────────────────────────────
# Test: runtime auto-discovery without prior import
# ────────────────────────────────────────────────────────────

MULTI_SERVICE_BATCH = {
    "schema_version": "1",
    "machine_name": "test-node",
    "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
    "samples": [
        {
            "container_reference": {"name": "/myapp-web-1", "aliases": ["web"], "namespace": "docker"},
            "container_spec": {
                "image": "nginx:latest",
                "labels": {
                    "com.docker.compose.service": "web",
                    "com.docker.compose.project": "myapp",
                },
            },
            "stats": {
                "cpu": {"usage": {"total": 100000}},
                "memory": {"usage": 10000000, "working_set": 8000000},
                "network": {"interfaces": [{"name": "eth0", "rx_bytes": 1000, "tx_bytes": 500}]},
            },
        },
        {
            "container_reference": {"name": "/myapp-api-1", "aliases": ["api"], "namespace": "docker"},
            "container_spec": {
                "image": "python:3.12",
                "labels": {
                    "com.docker.compose.service": "api",
                    "com.docker.compose.project": "myapp",
                },
            },
            "stats": {
                "cpu": {"usage": {"total": 200000}},
                "memory": {"usage": 20000000, "working_set": 15000000},
                "network": {"interfaces": [{"name": "eth0", "rx_bytes": 2000, "tx_bytes": 1000}]},
            },
        },
        {
            "container_reference": {"name": "/myapp-db-1", "aliases": ["db"], "namespace": "docker"},
            "container_spec": {
                "image": "postgres:16",
                "labels": {
                    "com.docker.compose.service": "db",
                    "com.docker.compose.project": "myapp",
                },
            },
            "stats": {
                "cpu": {"usage": {"total": 300000}},
                "memory": {"usage": 30000000, "working_set": 25000000},
            },
        },
    ],
}


@pytest.mark.asyncio
async def test_runtime_discovery_creates_topology_nodes():
    """Ingesting containers with compose labels auto-creates topology nodes — no import needed."""
    await _reset_tables()

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    batch = {**MULTI_SERVICE_BATCH, "sent_at": now_iso}
    # Add timestamps to each sample
    for s in batch["samples"]:
        s["stats"]["timestamp"] = now_iso

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Ingest — no prior import
            resp = await ac.post(
                "/cadvisor/batch",
                json=batch,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            assert resp.status_code == 202

            # GET /api/topology should return auto-discovered nodes
            topo = await ac.get("/topology")
            assert topo.status_code == 200
            data = topo.json()

            node_ids = {n["id"] for n in data["nodes"]}
            assert {"myapp__web", "myapp__api", "myapp__db"} == node_ids

            # Edges should exist between services in the same project
            assert len(data["edges"]) >= 1
            # All edges should be "inferred" kind
            for e in data["edges"]:
                assert e["kind"] == "inferred"


@pytest.mark.asyncio
async def test_runtime_discovery_topology_has_telemetry():
    """Auto-discovered topology nodes should have real telemetry."""
    await _reset_tables()

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    batch = {**MULTI_SERVICE_BATCH, "sent_at": now_iso}
    for s in batch["samples"]:
        s["stats"]["timestamp"] = now_iso

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/cadvisor/batch",
                json=batch,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            assert resp.status_code == 202

            topo = await ac.get("/topology")
            data = topo.json()

            # "web" has network stats → should have telemetry
            web_node = next((n for n in data["nodes"] if n["id"] == "myapp__web"), None)
            assert web_node is not None
            assert web_node["telemetry"] is not None
            assert web_node["telemetry"]["ingressMbps"] >= 0

            # "db" has no network stats → telemetry may be None or have zero throughput
            db_node = next((n for n in data["nodes"] if n["id"] == "myapp__db"), None)
            assert db_node is not None


@pytest.mark.asyncio
async def test_runtime_discovery_stable_across_ingests():
    """Repeated ingests should not duplicate nodes — idempotent upsert."""
    await _reset_tables()

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    batch = {**MULTI_SERVICE_BATCH, "sent_at": now_iso}
    for s in batch["samples"]:
        s["stats"]["timestamp"] = now_iso

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Ingest twice
            for _ in range(2):
                resp = await ac.post(
                    "/cadvisor/batch",
                    json=batch,
                    headers={"Authorization": f"Bearer {VALID_TOKEN}"},
                )
                assert resp.status_code == 202

            topo = await ac.get("/topology")
            data = topo.json()

            # Should still be exactly 3 unique nodes
            node_ids = [n["id"] for n in data["nodes"]]
            assert len(node_ids) == 3
            assert set(node_ids) == {"myapp__web", "myapp__api", "myapp__db"}


@pytest.mark.asyncio
async def test_runtime_discovery_coexists_with_import():
    """Imported topology and runtime-discovered topology should coexist.

    Import without project_name creates unscoped nodes (web, api, db, redis).
    Runtime discovery creates project-scoped nodes (proj__api).
    Both coexist — import enriches, runtime discovers.
    """
    await _reset_tables()

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Import topology first (creates web, api, db, redis — unscoped)
            await ac.post("/topology/import", json={"yaml_content": SMALL_COMPOSE})

            # Ingest a container "api" from project "proj" — creates proj__api
            single_batch = {
                "schema_version": "1",
                "sent_at": now_iso,
                "machine_name": "test-node",
                "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
                "samples": [{
                    "container_reference": {"name": "/proj-api-1", "aliases": ["api"], "namespace": "docker"},
                    "container_spec": {
                        "image": "python:3.12",
                        "labels": {
                            "com.docker.compose.service": "api",
                            "com.docker.compose.project": "proj",
                        },
                    },
                    "stats": {
                        "timestamp": now_iso,
                        "cpu": {"usage": {"total": 100}},
                        "memory": {"usage": 1000, "working_set": 800},
                        "network": {"interfaces": [{"name": "eth0", "rx_bytes": 500, "tx_bytes": 200}]},
                    },
                }],
            }
            resp = await ac.post(
                "/cadvisor/batch",
                json=single_batch,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            assert resp.status_code == 202

            # Topology should have both imported and runtime-discovered nodes
            topo = await ac.get("/topology")
            data = topo.json()
            node_ids = {n["id"] for n in data["nodes"]}
            # Imported (unscoped): web, api, db, redis
            # Runtime (scoped): proj__api
            assert {"web", "api", "db", "redis"}.issubset(node_ids)
            assert "proj__api" in node_ids

            # The scoped node should have telemetry
            api_node = next((n for n in data["nodes"] if n["id"] == "proj__api"), None)
            assert api_node is not None
            assert api_node["telemetry"] is not None


@pytest.mark.asyncio
async def test_import_with_project_name_merges_with_runtime():
    """Import with project_name should merge with runtime-discovered nodes."""
    await _reset_tables()

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Runtime discovery first — creates myapp__web, myapp__api, myapp__db
            batch = {**MULTI_SERVICE_BATCH, "sent_at": now_iso}
            for s in batch["samples"]:
                s["stats"]["timestamp"] = now_iso
            await ac.post(
                "/cadvisor/batch",
                json=batch,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )

            # Import with matching project_name → should merge
            await ac.post("/topology/import", json={
                "yaml_content": SMALL_COMPOSE,
                "project_name": "myapp",
            })

            topo = await ac.get("/topology")
            data = topo.json()
            node_ids = {n["id"] for n in data["nodes"]}

            # Runtime nodes should still exist with scoped IDs
            assert "myapp__web" in node_ids
            assert "myapp__api" in node_ids
            assert "myapp__db" in node_ids

            # Import also adds myapp__redis (scoped by project_name)
            assert "myapp__redis" in node_ids

            # Check that import enriched descriptions
            api_node = next((n for n in data["nodes"] if n["id"] == "myapp__api"), None)
            assert api_node is not None
            assert "Imported from project: myapp" in (api_node.get("description") or "")


@pytest.mark.asyncio
async def test_get_topology_empty_when_no_data():
    """GET /topology returns an empty graph when no containers have been ingested."""
    await _reset_tables()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        topo = await ac.get("/topology")
        assert topo.status_code == 200
        data = topo.json()
        assert data["nodes"] == []
        assert data["edges"] == []
        assert data["scanStatus"] == "idle"


@pytest.mark.asyncio
async def test_edge_generation_inferred_label():
    """Inferred edges should be labeled with 'inferred' kind, not 'network' like imports."""
    await _reset_tables()

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    batch = {**MULTI_SERVICE_BATCH, "sent_at": now_iso}
    for s in batch["samples"]:
        s["stats"]["timestamp"] = now_iso

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post(
                "/cadvisor/batch",
                json=batch,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )

            topo = await ac.get("/topology")
            data = topo.json()

            for edge in data["edges"]:
                assert edge["kind"] == "inferred"
                assert "inferred:" in edge["label"]


@pytest.mark.asyncio
async def test_security_score_endpoint():
    """GET /api/security-score returns a valid score."""
    await _reset_tables()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/security-score")
        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert "breakdown" in data
        assert data["score"] >= 0 and data["score"] <= 100


# ────────────────────────────────────────────────────────────
# Regression: telemetry tool shape — nested CPU usage
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_spike_tool_nested_cpu_shape():
    """get_resource_spikes_impl works with cpu_stats = {usage: {total: N, ...}}.

    This is the actual cAdvisor shape stored by ingestion.  The old SQL-based
    implementation would crash with InvalidTextRepresentation because it cast
    the JSON object to numeric.
    """
    await _reset_tables()

    from app.agents.tools.telemetry import get_resource_spikes_impl
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    ts1 = (now - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ts2 = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Ingest TWO batches with different CPU totals to produce a delta
    batch1 = {
        "schema_version": "1",
        "sent_at": ts1,
        "machine_name": "test-node",
        "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
        "samples": [{
            "container_reference": {"name": "/spike-test-1", "aliases": ["spike"], "namespace": "docker"},
            "container_spec": {
                "image": "spike:latest",
                "labels": {
                    "com.docker.compose.service": "spike",
                    "com.docker.compose.project": "spikeproj",
                },
            },
            "stats": {
                "timestamp": ts1,
                "cpu": {"usage": {"total": 1000000000, "user": 700000000, "system": 300000000}},
                "memory": {"usage": 200000000, "working_set": 150000000},
            },
        }],
    }
    batch2 = {
        "schema_version": "1",
        "sent_at": ts2,
        "machine_name": "test-node",
        "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
        "samples": [{
            "container_reference": {"name": "/spike-test-1", "aliases": ["spike"], "namespace": "docker"},
            "container_spec": {
                "image": "spike:latest",
                "labels": {
                    "com.docker.compose.service": "spike",
                    "com.docker.compose.project": "spikeproj",
                },
            },
            "stats": {
                "timestamp": ts2,
                "cpu": {"usage": {"total": 61000000000, "user": 40000000000, "system": 21000000000}},
                "memory": {"usage": 220000000, "working_set": 170000000},
            },
        }],
    }

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post("/cadvisor/batch", json=batch1, headers={"Authorization": f"Bearer {VALID_TOKEN}"})
            await ac.post("/cadvisor/batch", json=batch2, headers={"Authorization": f"Bearer {VALID_TOKEN}"})

    # Now call get_resource_spikes_impl directly with a test session
    async with TestSessionLocal() as session:
        result = await get_resource_spikes_impl(lookback_seconds=300, db=session)

    # Must succeed without InvalidTextRepresentation or any crash
    assert isinstance(result, str)
    # The result should mention the container or node
    assert "spike" in result.lower() or "No significant" in result
    # If there are spikes, verify the format is structured
    if "spike" in result.lower():
        assert "cpu_avg_cores=" in result
        assert "mem_working_set_mb=" in result


# ────────────────────────────────────────────────────────────
# Regression: scan transaction recovery
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scan_transaction_recovery():
    """POST /topology/scan returns 200 even when spike extraction fails internally.

    Also verifies that a subsequent GET /topology still works
    (session is not poisoned by an aborted transaction).
    """
    await _reset_tables()

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    batch = {
        "schema_version": "1",
        "sent_at": now_iso,
        "machine_name": "test-node",
        "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
        "samples": [{
            "container_reference": {"name": "/scan-test-1", "aliases": ["scantest"], "namespace": "docker"},
            "container_spec": {
                "image": "scantest:latest",
                "labels": {
                    "com.docker.compose.service": "scantest",
                    "com.docker.compose.project": "scanproj",
                },
            },
            "stats": {
                "timestamp": now_iso,
                "cpu": {"usage": {"total": 123456789, "user": 100000000, "system": 23456789}},
                "memory": {"usage": 67108864, "working_set": 50331648},
            },
        }],
    }

    mock_run_analysis = AsyncMock(return_value={"node_updates": [], "new_vulnerabilities": [], "new_insights": []})

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Ingest data with nested CPU shape
            resp = await ac.post(
                "/cadvisor/batch", json=batch,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            assert resp.status_code == 202

            # Run scan (mocked LLM)
            with patch("app.routers.aegis.run_topology_analysis", new=mock_run_analysis):
                scan_resp = await ac.post("/topology/scan")
                assert scan_resp.status_code == 200
                scan_data = scan_resp.json()
                assert scan_data["scanStatus"] == "complete"

                # Subsequent GET /topology must not fail
                topo_resp = await ac.get("/topology")
                assert topo_resp.status_code == 200


# ────────────────────────────────────────────────────────────
# Regression: network rate delta semantics
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_network_rate_delta_semantics():
    """Network Mbps must be computed from deltas between snapshots, not cumulative totals."""
    await _reset_tables()

    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    ts1 = (now - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ts2 = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Two batches: cumulative rx_bytes/tx_bytes increase
    # rx: 10_000_000 → 10_500_000 (delta 500_000 over 30s)
    # tx: 5_000_000 → 5_200_000  (delta 200_000 over 30s)
    batch1 = {
        "schema_version": "1",
        "sent_at": ts1,
        "machine_name": "test-node",
        "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
        "samples": [{
            "container_reference": {"name": "/nettest-1", "aliases": ["nettest"], "namespace": "docker"},
            "container_spec": {
                "image": "nettest:latest",
                "labels": {
                    "com.docker.compose.service": "nettest",
                    "com.docker.compose.project": "netproj",
                },
            },
            "stats": {
                "timestamp": ts1,
                "cpu": {"usage": {"total": 100}},
                "memory": {"usage": 1000},
                "network": {"interfaces": [{"name": "eth0", "rx_bytes": 10000000, "tx_bytes": 5000000}]},
            },
        }],
    }
    batch2 = {
        "schema_version": "1",
        "sent_at": ts2,
        "machine_name": "test-node",
        "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
        "samples": [{
            "container_reference": {"name": "/nettest-1", "aliases": ["nettest"], "namespace": "docker"},
            "container_spec": {
                "image": "nettest:latest",
                "labels": {
                    "com.docker.compose.service": "nettest",
                    "com.docker.compose.project": "netproj",
                },
            },
            "stats": {
                "timestamp": ts2,
                "cpu": {"usage": {"total": 200}},
                "memory": {"usage": 1000},
                "network": {"interfaces": [{"name": "eth0", "rx_bytes": 10500000, "tx_bytes": 5200000}]},
            },
        }],
    }

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post("/cadvisor/batch", json=batch1, headers={"Authorization": f"Bearer {VALID_TOKEN}"})
            await ac.post("/cadvisor/batch", json=batch2, headers={"Authorization": f"Bearer {VALID_TOKEN}"})

            topo = await ac.get("/topology")
            assert topo.status_code == 200
            data = topo.json()

            net_node = next((n for n in data["nodes"] if n["id"] == "netproj__nettest"), None)
            assert net_node is not None, "netproj__nettest node should exist"
            assert net_node["telemetry"] is not None

            ingress = net_node["telemetry"]["ingressMbps"]
            egress = net_node["telemetry"]["egressMbps"]

            # Delta-based calculation:
            # rx: 500_000 bytes / 30s = 16666 bytes/s → 0.133 Mbps
            # tx: 200_000 bytes / 30s = 6666 bytes/s → 0.053 Mbps
            # If we were using cumulative: rx would be ~2.8 Mbps — way too high
            assert ingress < 1.0, f"Ingress {ingress} Mbps looks like cumulative, not delta"
            assert egress < 1.0, f"Egress {egress} Mbps looks like cumulative, not delta"
            assert ingress > 0, "Ingress should be positive from delta"
            assert egress > 0, "Egress should be positive from delta"


# ────────────────────────────────────────────────────────────
# Regression: security score consistency with topology
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_security_score_reflects_topology_warning():
    """If /topology shows a node as 'warning' from high egress,
    /security-score should reflect that same warning state.

    Uses two snapshots with large rx_bytes/tx_bytes delta so that the
    delta-based rate exceeds _EGRESS_WARNING_MBPS (50 Mbps).
    """
    await _reset_tables()

    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    ts1 = (now - timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ts2 = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Delta: 1_000_000_000 bytes over 10 seconds = 100MB/s = 800 Mbps >> 50 Mbps threshold
    batch1 = {
        "schema_version": "1",
        "sent_at": ts1,
        "machine_name": "test-node",
        "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
        "samples": [{
            "container_reference": {"name": "/highegress-1", "aliases": ["highegress"], "namespace": "docker"},
            "container_spec": {
                "image": "highegress:latest",
                "labels": {
                    "com.docker.compose.service": "highegress",
                    "com.docker.compose.project": "egressproj",
                },
            },
            "stats": {
                "timestamp": ts1,
                "cpu": {"usage": {"total": 100}},
                "memory": {"usage": 1000},
                "network": {"interfaces": [{"name": "eth0", "rx_bytes": 0, "tx_bytes": 0}]},
            },
        }],
    }
    batch2 = {
        "schema_version": "1",
        "sent_at": ts2,
        "machine_name": "test-node",
        "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
        "samples": [{
            "container_reference": {"name": "/highegress-1", "aliases": ["highegress"], "namespace": "docker"},
            "container_spec": {
                "image": "highegress:latest",
                "labels": {
                    "com.docker.compose.service": "highegress",
                    "com.docker.compose.project": "egressproj",
                },
            },
            "stats": {
                "timestamp": ts2,
                "cpu": {"usage": {"total": 200}},
                "memory": {"usage": 1000},
                "network": {"interfaces": [{"name": "eth0", "rx_bytes": 0, "tx_bytes": 1000000000}]},
            },
        }],
    }

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post("/cadvisor/batch", json=batch1, headers={"Authorization": f"Bearer {VALID_TOKEN}"})
            await ac.post("/cadvisor/batch", json=batch2, headers={"Authorization": f"Bearer {VALID_TOKEN}"})

            # Topology should show the node as 'warning' (high egress)
            topo = await ac.get("/topology")
            assert topo.status_code == 200
            topo_data = topo.json()

            egress_node = next(
                (n for n in topo_data["nodes"] if n["id"] == "egressproj__highegress"),
                None,
            )
            assert egress_node is not None
            assert egress_node["status"] == "warning", (
                f"Expected warning from high egress, got {egress_node['status']}"
            )

            # Security score should reflect the same warning
            score_resp = await ac.get("/security-score")
            assert score_resp.status_code == 200
            score_data = score_resp.json()
            assert score_data["score"] < 100, (
                "Score should be <100 when topology shows a warning node"
            )
            # Check the breakdown mentions warning nodes
            warning_entries = [
                b for b in score_data["breakdown"]
                if "warning" in b.get("label", "").lower()
            ]
            assert len(warning_entries) > 0, (
                "Breakdown should mention warning nodes"
            )


# ────────────────────────────────────────────────────────────
# Regression: topology_node_id in anomaly summaries
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_topology_node_id_in_spike_summaries():
    """Spike summaries include topology_node_id for authoritative mapping."""
    await _reset_tables()

    from app.agents.tools.telemetry import get_resource_spikes_impl
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    ts1 = (now - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ts2 = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    batch1 = {
        "schema_version": "1",
        "sent_at": ts1,
        "machine_name": "test-node",
        "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
        "samples": [{
            "container_reference": {"name": "/mapped-svc-1", "aliases": ["mapped"], "namespace": "docker"},
            "container_spec": {
                "image": "mapped:latest",
                "labels": {
                    "com.docker.compose.service": "mapped",
                    "com.docker.compose.project": "mapproj",
                },
            },
            "stats": {
                "timestamp": ts1,
                "cpu": {"usage": {"total": 1000000000}},
                "memory": {"usage": 100000000, "working_set": 80000000},
            },
        }],
    }
    batch2 = {
        "schema_version": "1",
        "sent_at": ts2,
        "machine_name": "test-node",
        "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
        "samples": [{
            "container_reference": {"name": "/mapped-svc-1", "aliases": ["mapped"], "namespace": "docker"},
            "container_spec": {
                "image": "mapped:latest",
                "labels": {
                    "com.docker.compose.service": "mapped",
                    "com.docker.compose.project": "mapproj",
                },
            },
            "stats": {
                "timestamp": ts2,
                "cpu": {"usage": {"total": 61000000000}},
                "memory": {"usage": 120000000, "working_set": 100000000},
            },
        }],
    }

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post("/cadvisor/batch", json=batch1, headers={"Authorization": f"Bearer {VALID_TOKEN}"})
            await ac.post("/cadvisor/batch", json=batch2, headers={"Authorization": f"Bearer {VALID_TOKEN}"})

    async with TestSessionLocal() as session:
        result = await get_resource_spikes_impl(lookback_seconds=300, db=session)

    # The summary should include the topology_node_id "mapproj__mapped"
    assert "mapproj__mapped" in result, (
        f"topology_node_id should appear in spike summary. Got:\n{result}"
    )
