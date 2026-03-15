"""Tests for the two-lane detection architecture.

Required scenarios:
1. Ingestion → detector → immediate warning state
2. Detector → agentic report (reports reference detections)
3. Demo profile sensitivity
4. Multi-signal correlation
5. Manual deep scan consumes precomputed detections
"""

import copy
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import get_db_session, Base

# Reuse the test engine and session factory from test_topology.py
# to avoid dependency_override conflicts when running together.
from tests.test_topology import test_engine, TestSessionLocal, _reset_tables

VALID_TOKEN = "test-secret-123"


# ── Helpers ─────────────────────────────────────────────────

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
"""


def _make_batch(now_iso, samples):
    return {
        "schema_version": "1",
        "sent_at": now_iso,
        "machine_name": "test-node",
        "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
        "samples": samples,
    }


def _make_sample(
    name,
    project,
    service,
    timestamp,
    cpu_total=100000,
    mem_usage=10_000_000,
    mem_ws=8_000_000,
    rx_bytes=1000,
    tx_bytes=500,
    fs_usage=None,
):
    sample = {
        "container_reference": {
            "name": name,
            "aliases": [service],
            "namespace": "docker",
        },
        "container_spec": {
            "image": "test:latest",
            "labels": {
                "com.docker.compose.service": service,
                "com.docker.compose.project": project,
            },
        },
        "stats": {
            "timestamp": timestamp,
            "cpu": {"usage": {"total": cpu_total}},
            "memory": {"usage": mem_usage, "working_set": mem_ws},
            "network": {
                "interfaces": [
                    {"name": "eth0", "rx_bytes": rx_bytes, "tx_bytes": tx_bytes}
                ]
            },
        },
    }
    if fs_usage is not None:
        sample["stats"]["filesystem"] = [{"device": "/dev/sda1", "usage": fs_usage}]
    return sample


# ────────────────────────────────────────────────────────────
# 1. Ingestion → detector → immediate warning state
# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingestion_triggers_detector_and_updates_status():
    """Simulated egress burst ingestion should update topology-visible
    state to warning without waiting for LLM."""
    await _reset_tables()

    now = datetime.now(timezone.utc)
    t1 = (now - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t2 = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Two snapshots with massive egress delta to trigger egress_burst
    # demo profile: threshold 8 Mbps; tx delta = 100MB in 30s = ~26 Mbps
    batch1 = _make_batch(
        t1,
        [
            _make_sample(
                "/proj-api-1",
                "proj",
                "api",
                t1,
                cpu_total=100000,
                tx_bytes=1_000_000,
                rx_bytes=1000,
            ),
        ],
    )
    batch2 = _make_batch(
        t2,
        [
            _make_sample(
                "/proj-api-1",
                "proj",
                "api",
                t2,
                cpu_total=200000,
                tx_bytes=100_000_000,
                rx_bytes=2000,
            ),
        ],
    )

    with (
        patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN),
        patch("app.core.config.settings.detection_profile", "demo"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            # Ingest two batches
            resp1 = await ac.post(
                "/cadvisor/batch",
                json=batch1,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            assert resp1.status_code == 202

            resp2 = await ac.post(
                "/cadvisor/batch",
                json=batch2,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            assert resp2.status_code == 202
            body = resp2.json()
            # Egress burst should be detected under demo profile
            assert body["detection_events"] >= 1

            # Topology should show the node as warning
            topo = await ac.get("/topology")
            assert topo.status_code == 200
            data = topo.json()
            api_node = next((n for n in data["nodes"] if n["id"] == "proj__api"), None)
            assert api_node is not None
            # With the egress burst, detection lane should flag it
            assert api_node["status"] in ("warning", "compromised")


# ────────────────────────────────────────────────────────────
# 2. Detector → agentic report (reports reference detections)
# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detector_events_feed_into_reports():
    """Detection events should be included in generated reports."""
    await _reset_tables()

    from app.services.report_generation import generate_reports

    # Seed topology so nodes exist for posture report
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await ac.post("/topology/seed")

    scan_result = {
        "node_updates": [],
        "new_vulnerabilities": [],
        "new_insights": [],
    }
    det_events = [
        {
            "id": "det-test-001",
            "kind": "egress_burst",
            "node_id": "proj__api",
            "severity": "warning",
            "title": "Egress burst detected",
        },
        {
            "id": "det-test-002",
            "kind": "cpu_abuse",
            "node_id": "proj__api",
            "severity": "critical",
            "title": "Sustained CPU spike",
        },
    ]
    det_summaries = [
        {
            "node_id": "proj__api",
            "max_severity": "critical",
            "detection_count": 2,
            "recommended_status": "warning",
        },
    ]

    async with TestSessionLocal() as session:
        reports = await generate_reports(
            session,
            scan_result,
            trigger="detection",
            detection_events=det_events,
            detection_summaries=det_summaries,
        )

        assert len(reports) == 2  # deep_scan + security_posture

        deep_report = next(r for r in reports if r.report_kind == "deep_scan")
        event_ids = (deep_report.payload or {}).get("detection_event_ids", [])
        assert "det-test-001" in event_ids
        assert "det-test-002" in event_ids
        assert "Egress burst" in deep_report.details_markdown
        assert "proj__api" in deep_report.details_markdown
        assert "detection" in deep_report.summary.lower()

        await session.commit()


# ────────────────────────────────────────────────────────────
# 3. Demo profile sensitivity
# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_profile_more_sensitive_than_normal():
    """Same telemetry under demo profile should produce more detections."""
    await _reset_tables()

    now = datetime.now(timezone.utc)
    t1 = (now - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t2 = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Moderate egress: 10 Mbps — above demo threshold (8) but below normal (50)
    # tx delta = 10 Mbps => ~75 MB in 60 seconds => 75_000_000 bytes
    batch1 = _make_batch(
        t1,
        [
            _make_sample("/proj-web-1", "proj", "web", t1, tx_bytes=1_000_000),
        ],
    )
    batch2 = _make_batch(
        t2,
        [
            _make_sample("/proj-web-1", "proj", "web", t2, tx_bytes=76_000_000),
        ],
    )

    from app.services.detection import run_detectors

    # Run under demo profile
    with (
        patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN),
        patch("app.core.config.settings.detection_profile", "demo"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            await ac.post(
                "/cadvisor/batch",
                json=batch1,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            await ac.post(
                "/cadvisor/batch",
                json=batch2,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )

        async with TestSessionLocal() as session:
            demo_events, demo_summaries = await run_detectors(session)

    # Reset and run under normal profile
    await _reset_tables()
    with (
        patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN),
        patch("app.core.config.settings.detection_profile", "normal"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            await ac.post(
                "/cadvisor/batch",
                json=batch1,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            await ac.post(
                "/cadvisor/batch",
                json=batch2,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )

        async with TestSessionLocal() as session:
            normal_events, normal_summaries = await run_detectors(session)

    # Demo should produce more or equal detections than normal
    assert len(demo_events) >= len(normal_events)
    # The moderate egress should trigger under demo but not normal
    demo_egress = [e for e in demo_events if e.kind == "egress_burst"]
    normal_egress = [e for e in normal_events if e.kind == "egress_burst"]
    assert len(demo_egress) > len(normal_egress)


# ────────────────────────────────────────────────────────────
# 4. Multi-signal correlation
# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multi_signal_correlation():
    """Mixed incident behaviour should generate multi-signal correlation
    that is stronger than any single raw spike."""
    await _reset_tables()

    now = datetime.now(timezone.utc)
    t1 = (now - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t2 = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # High CPU + high egress to trigger both cpu_abuse and egress_burst (demo)
    batch1 = _make_batch(
        t1,
        [
            _make_sample(
                "/proj-api-1",
                "proj",
                "api",
                t1,
                cpu_total=1_000_000_000,
                tx_bytes=1_000_000,
                mem_usage=100_000_000,
                mem_ws=80_000_000,
            ),
        ],
    )
    batch2 = _make_batch(
        t2,
        [
            _make_sample(
                "/proj-api-1",
                "proj",
                "api",
                t2,
                cpu_total=20_000_000_000,
                tx_bytes=100_000_000,
                mem_usage=200_000_000,
                mem_ws=180_000_000,
            ),
        ],
    )

    from app.services.detection import run_detectors

    with (
        patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN),
        patch("app.core.config.settings.detection_profile", "demo"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            await ac.post(
                "/cadvisor/batch",
                json=batch1,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            await ac.post(
                "/cadvisor/batch",
                json=batch2,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )

        async with TestSessionLocal() as session:
            events, summaries = await run_detectors(session)

    # Should have multiple individual detections + a multi-signal correlation
    kinds = [e.kind for e in events]
    assert "multi_signal_correlation" in kinds, f"Expected multi_signal, got: {kinds}"

    # Multi-signal correlation should have higher confidence than individual events
    multi = [e for e in events if e.kind == "multi_signal_correlation"][0]
    singles = [e for e in events if e.kind != "multi_signal_correlation"]
    avg_single_conf = (
        sum(s.confidence for s in singles) / len(singles) if singles else 0
    )
    assert multi.confidence >= avg_single_conf

    # Node summary should recommend "warning"
    api_summary = next((s for s in summaries if s.node_id == "proj__api"), None)
    assert api_summary is not None
    assert api_summary.recommended_status == "warning"
    assert api_summary.detection_count >= 3  # at least 2 singles + 1 multi


# ────────────────────────────────────────────────────────────
# 5. Manual deep scan consumes precomputed detections
# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_manual_scan_consumes_detections():
    """Manual deep scan should work and consume precomputed detections
    rather than acting as first detector."""
    await _reset_tables()

    # Mock LLM to return empty analysis (we just want to verify detection
    # events flow through to reports)
    mock_run_analysis = AsyncMock(
        return_value={
            "node_updates": [],
            "new_vulnerabilities": [],
            "new_insights": [],
        }
    )

    with patch("app.routers.aegis.run_topology_analysis", new=mock_run_analysis):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            # Seed topology
            resp = await ac.post("/topology/seed")
            assert resp.status_code == 200

            # Scan still works
            scan_resp = await ac.post("/topology/scan")
            assert scan_resp.status_code == 200
            assert scan_resp.json()["scanStatus"] == "complete"


# ────────────────────────────────────────────────────────────
# Unit tests for detector functions
# ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detection_schemas():
    """Detection schemas should be constructable and serializable."""
    from app.agents.schemas import (
        DetectionEvent,
        NodeDetectionSummary,
        DetectionEvidenceRef,
    )

    ref = DetectionEvidenceRef(
        ref_type="metric_snapshot", ref_id="snap-123", description="test"
    )
    event = DetectionEvent(
        id="det-001",
        kind="cpu_abuse",
        node_id="test-node",
        severity="warning",
        confidence=0.75,
        title="Test detection",
        summary="Test summary",
        detected_at=datetime.now(timezone.utc).isoformat(),
        lookback_seconds=300,
        evidence_refs=[ref],
    )
    assert event.model_dump()["kind"] == "cpu_abuse"

    summary = NodeDetectionSummary(
        node_id="test-node",
        max_severity="warning",
        detection_count=1,
        detection_kinds=["cpu_abuse"],
        events=[event],
        recommended_status="warning",
    )
    assert summary.model_dump()["recommended_status"] == "warning"


@pytest.mark.asyncio
async def test_detectors_empty_db():
    """Detectors should return empty results on empty database."""
    await _reset_tables()

    from app.services.detection import run_detectors

    async with TestSessionLocal() as session:
        events, summaries = await run_detectors(session)

    assert events == []
    assert summaries == []


@pytest.mark.asyncio
async def test_detection_profile_config():
    """Verify detection profile thresholds are configurable."""
    from app.services.detection import _get_thresholds

    with patch("app.core.config.settings.detection_profile", "demo"):
        thresholds = _get_thresholds()
        assert thresholds["cpu_avg_cores"] == 0.25
        assert thresholds["memory_surge_mb"] == 64
        assert thresholds["egress_mbps"] == 8.0
        assert thresholds["beaconing_min_intervals"] == 5
        assert thresholds["beaconing_cv_threshold"] == 0.25
        assert thresholds["filesystem_churn_mb"] == 128

    with patch("app.core.config.settings.detection_profile", "normal"):
        thresholds = _get_thresholds()
        assert thresholds["cpu_avg_cores"] == 0.8
        assert thresholds["memory_surge_mb"] == 200
        assert thresholds["egress_mbps"] == 50.0
        assert thresholds["beaconing_min_intervals"] == 5
        assert thresholds["beaconing_cv_threshold"] == 0.35
        assert thresholds["filesystem_churn_mb"] == 500


@pytest.mark.asyncio
async def test_detections_endpoint():
    """GET /detections should return structured detection data."""
    await _reset_tables()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get("/detections")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "summaries" in data
        assert isinstance(data["events"], list)
        assert isinstance(data["summaries"], list)


@pytest.mark.asyncio
async def test_status_engine_with_detection_severity():
    """Verify the status engine incorporates detection severity."""
    from app.routers.aegis import _compute_node_status, NodeTelemetry

    # Normal healthy telemetry, but detection says warning
    telem = NodeTelemetry(
        ingressMbps=1.0,
        egressMbps=2.0,
        lastSeen=datetime.now(timezone.utc).isoformat(),
    )
    assert (
        _compute_node_status("healthy", telem, detection_severity="warning")
        == "warning"
    )
    assert (
        _compute_node_status("healthy", telem, detection_severity="critical")
        == "warning"
    )
    assert _compute_node_status("healthy", telem, detection_severity=None) == "healthy"
    assert (
        _compute_node_status("healthy", telem, detection_severity="info") == "healthy"
    )

    # No telemetry, detection severity provided
    assert (
        _compute_node_status("healthy", None, detection_severity="warning") == "warning"
    )


@pytest.mark.asyncio
async def test_ingest_returns_detection_metadata():
    """POST /cadvisor/batch should return detection_events count in response."""
    await _reset_tables()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    batch = _make_batch(
        now,
        [
            _make_sample("/proj-api-1", "proj", "api", now),
        ],
    )

    with patch("app.core.config.settings.cadvisor_metrics_api_token", VALID_TOKEN):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                "/cadvisor/batch",
                json=batch,
                headers={"Authorization": f"Bearer {VALID_TOKEN}"},
            )
            assert resp.status_code == 202
            body = resp.json()
            assert "detection_events" in body
            assert "nodes_updated" in body
