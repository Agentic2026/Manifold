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

@pytest.mark.asyncio
async def test_topology_seed_and_fetch():
    """Verify that we can seed the topology and fetch it from DB."""
    
    # Needs to create tables in the SQLite test DB first
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Mock run_topology_analysis so we don't actually hit the LLM during the scan endpoint
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
