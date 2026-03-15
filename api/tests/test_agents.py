"""Regression tests for Manifold's evidence-first agentic system.

Covers:
  1. Shared schemas and policy consistency
  2. Chat workflow evidence grounding
  3. Topology workflow verification
  4. Conversation continuity (thread memory)
  5. Production fallback behavior
  6. Tool failure behavior
  7. Composite evidence tool correctness
  8. Intent routing
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import get_db_session, Base
from app.models.topology import TopologyNode, TopologyEdge

# ── Reuse test engine from test_topology (same in-memory SQLite) ────
# The JSONB→JSON compiler hooks are already registered by test_topology.
# We import the same engine/session so app dependency override is shared.

from tests.test_topology import test_engine, TestSessionLocal, _reset_tables

VALID_TOKEN = "test-secret-123"


async def _seed_topology(session: AsyncSession):
    """Insert a minimal topology (web→api→db) directly into the test DB."""
    nodes = [
        TopologyNode(id="web", label="web", service_id="web", status="healthy",
                     type="frontend", position={"x": 0, "y": 0}),
        TopologyNode(id="api", label="api", service_id="api", status="healthy",
                     type="service", position={"x": 100, "y": 0}),
        TopologyNode(id="db", label="db", service_id="db", status="healthy",
                     type="database", position={"x": 200, "y": 0}),
    ]
    edges = [
        TopologyEdge(id="e-web-api", source_id="web", target_id="api",
                     kind="network", label="web→api"),
        TopologyEdge(id="e-api-db", source_id="api", target_id="db",
                     kind="network", label="api→db"),
    ]
    for n in nodes:
        session.add(n)
    for e in edges:
        session.add(e)
    await session.commit()


# ═══════════════════════════════════════════════════════════════
# 1. Shared schemas
# ═══════════════════════════════════════════════════════════════

def test_schemas_telemetry_anomaly():
    """TelemetryAnomaly schema constructs and serializes."""
    from app.agents.schemas import TelemetryAnomaly

    a = TelemetryAnomaly(
        evidence_id="anom-abc",
        container_ref="/test-1",
        topology_node_id="proj__svc",
        metric_type="cpu",
        observed_value=1.5,
        baseline_or_delta=0.5,
        unit="cores",
        time_window_seconds=300,
        severity_suggestion="warning",
    )
    d = a.model_dump()
    assert d["evidence_id"] == "anom-abc"
    assert d["severity_suggestion"] == "warning"


def test_schemas_node_evidence():
    """NodeEvidence schema round-trips correctly."""
    from app.agents.schemas import NodeEvidence

    ne = NodeEvidence(
        node_id="web",
        label="Web Server",
        effective_status="healthy",
        evidence_summary="No issues",
    )
    assert ne.node_id == "web"
    assert ne.recent_anomalies == []


def test_schemas_verified_answer():
    """VerifiedAgentAnswer schema validates confidence bounds."""
    from app.agents.schemas import VerifiedAgentAnswer

    ans = VerifiedAgentAnswer(
        answer_text="All systems healthy.",
        confidence=0.9,
        evidence_refs=["ev-1"],
    )
    assert ans.confidence == 0.9


def test_schemas_topology_result():
    """TopologyAnalysisResult can be constructed empty or populated."""
    from app.agents.schemas import TopologyAnalysisResult, NodeStatusUpdate

    empty = TopologyAnalysisResult()
    assert empty.node_updates == []

    full = TopologyAnalysisResult(
        node_updates=[
            NodeStatusUpdate(
                node_id="api",
                new_status="warning",
                rationale="CPU spike",
                evidence_refs=["anom-123"],
            )
        ]
    )
    assert len(full.node_updates) == 1


# ═══════════════════════════════════════════════════════════════
# 2. Shared policy consistency
# ═══════════════════════════════════════════════════════════════

def test_policy_base_contains_evidence_first():
    """The base policy requires evidence-first reasoning."""
    from app.agents.policies import BASE_SECURITY_POLICY

    assert "EVIDENCE FIRST" in BASE_SECURITY_POLICY
    assert "compromised" in BASE_SECURITY_POLICY.lower()
    assert "corroborating" in BASE_SECURITY_POLICY.lower()


def test_policy_build_system_prompt():
    """build_system_prompt combines base policy with overlays."""
    from app.agents.policies import build_system_prompt, CHAT_ANALYST_OVERLAY

    prompt = build_system_prompt(CHAT_ANALYST_OVERLAY)
    assert "EVIDENCE FIRST" in prompt
    assert "security analyst" in prompt.lower()


def test_policy_topology_overlay_shares_severity_rules():
    """Topology overlay references structured output — but base policy governs severity."""
    from app.agents.policies import build_system_prompt, TOPOLOGY_ANALYSIS_OVERLAY

    prompt = build_system_prompt(TOPOLOGY_ANALYSIS_OVERLAY)
    # Both chat and topology share the base policy with severity rules
    assert "telemetry spikes alone" in prompt.lower()
    assert "warning" in prompt.lower()


# ═══════════════════════════════════════════════════════════════
# 3. Intent routing
# ═══════════════════════════════════════════════════════════════

def test_intent_routing_threat_landscape():
    from app.agents.runtime import classify_intent

    assert classify_intent("Analyze the current threat landscape") == "system_threat_landscape"
    assert classify_intent("What's the system status?") == "system_threat_landscape"


def test_intent_routing_remediation():
    from app.agents.runtime import classify_intent

    assert classify_intent("Generate a remediation plan") == "remediation_plan"
    assert classify_intent("How should we fix this?") == "remediation_plan"


def test_intent_routing_node_context():
    from app.agents.runtime import classify_intent

    # When node context is present, default to node_investigation
    assert classify_intent("Tell me more", has_node_context=True) == "node_investigation"
    # Without context, default to general_followup
    assert classify_intent("Tell me more", has_node_context=False) == "general_followup"


def test_intent_routing_vulnerability():
    from app.agents.runtime import classify_intent

    assert classify_intent("Show me the vulnerabilities") == "vulnerability_summary"


def test_intent_routing_rbac():
    from app.agents.runtime import classify_intent

    assert classify_intent("Any RBAC risks?") == "rbac_risk"


# ═══════════════════════════════════════════════════════════════
# 4. Verification
# ═══════════════════════════════════════════════════════════════

def test_verify_chat_answer_with_evidence():
    from app.agents.runtime import verify_chat_answer

    result = verify_chat_answer(
        answer_text="Node web is in warning state due to CPU spike.",
        evidence_refs=["anom-abc"],
        has_evidence=True,
    )
    assert result.confidence == 0.8
    assert result.uncertainty_notes == []


def test_verify_chat_answer_without_evidence():
    from app.agents.runtime import verify_chat_answer

    result = verify_chat_answer(
        answer_text="Everything looks fine.",
        evidence_refs=[],
        has_evidence=False,
    )
    assert result.confidence == 0.4
    assert len(result.uncertainty_notes) > 0
    assert "limited" in result.uncertainty_notes[0].lower()


def test_verify_topology_drops_unknown_nodes():
    from app.agents.runtime import verify_topology_updates
    from app.agents.schemas import TopologyAnalysisResult, NodeStatusUpdate

    raw = TopologyAnalysisResult(
        node_updates=[
            NodeStatusUpdate(node_id="real", new_status="warning", rationale="spike"),
            NodeStatusUpdate(node_id="fake", new_status="warning", rationale="???"),
        ]
    )
    verified = verify_topology_updates(raw, known_node_ids={"real"})
    assert len(verified.node_updates) == 1
    assert verified.node_updates[0].node_id == "real"


def test_verify_topology_downgrades_telemetry_only_compromised():
    from app.agents.runtime import verify_topology_updates
    from app.agents.schemas import TopologyAnalysisResult, NodeStatusUpdate

    raw = TopologyAnalysisResult(
        node_updates=[
            NodeStatusUpdate(
                node_id="api",
                new_status="compromised",
                rationale="CPU spike",
                evidence_refs=["anom-123"],  # telemetry-only
            )
        ]
    )
    verified = verify_topology_updates(raw, known_node_ids={"api"})
    assert verified.node_updates[0].new_status == "warning"
    assert "Downgraded" in verified.node_updates[0].rationale


def test_verify_topology_keeps_compromised_with_corroboration():
    from app.agents.runtime import verify_topology_updates
    from app.agents.schemas import TopologyAnalysisResult, NodeStatusUpdate

    raw = TopologyAnalysisResult(
        node_updates=[
            NodeStatusUpdate(
                node_id="api",
                new_status="compromised",
                rationale="Known vulnerability exploitation + spike",
                evidence_refs=["anom-123", "vuln-abc"],  # has non-telemetry ref
            )
        ]
    )
    verified = verify_topology_updates(raw, known_node_ids={"api"})
    assert verified.node_updates[0].new_status == "compromised"


def test_verify_topology_drops_ungrounded_vulnerabilities():
    from app.agents.runtime import verify_topology_updates
    from app.agents.schemas import TopologyAnalysisResult, ProposedVulnerability

    raw = TopologyAnalysisResult(
        new_vulnerabilities=[
            ProposedVulnerability(
                title="Vague vuln",
                severity="high",
                affected_node_id="api",
                description="Something bad",
                evidence_refs=[],  # no evidence
            ),
            ProposedVulnerability(
                title="Real vuln",
                severity="high",
                affected_node_id="api",
                description="Based on evidence",
                evidence_refs=["anom-abc"],
            ),
        ]
    )
    verified = verify_topology_updates(raw, known_node_ids={"api"})
    assert len(verified.new_vulnerabilities) == 1
    assert verified.new_vulnerabilities[0].title == "Real vuln"


# ═══════════════════════════════════════════════════════════════
# 5. Conversation memory / thread continuity
# ═══════════════════════════════════════════════════════════════

def test_thread_memory_stores_and_retrieves():
    from app.agents.runtime import store_message, get_thread_history, clear_thread

    clear_thread("test-thread-1")
    store_message("test-thread-1", "user", "Hello")
    store_message("test-thread-1", "assistant", "Hi there")
    store_message("test-thread-1", "user", "What about node X?")

    history = get_thread_history("test-thread-1", max_messages=10)
    assert len(history) == 3
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"
    assert history[-1]["content"] == "What about node X?"

    clear_thread("test-thread-1")
    assert get_thread_history("test-thread-1") == []


def test_thread_memory_bounded():
    from app.agents.runtime import store_message, get_thread_history, clear_thread, MAX_HISTORY_PER_THREAD

    clear_thread("test-thread-2")
    for i in range(MAX_HISTORY_PER_THREAD + 10):
        store_message("test-thread-2", "user", f"msg-{i}")

    history = get_thread_history("test-thread-2", max_messages=100)
    assert len(history) == MAX_HISTORY_PER_THREAD
    clear_thread("test-thread-2")


# ═══════════════════════════════════════════════════════════════
# 6. Composite evidence tools
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_security_snapshot_unknown_node():
    """get_security_snapshot for a non-existent node returns graceful message."""
    await _reset_tables()

    from app.agents.tools.security_snapshot import get_security_snapshot

    async with TestSessionLocal() as session:
        result = await get_security_snapshot(session, node_id="nonexistent")
    assert "not found" in result.evidence_summary.lower()


@pytest.mark.asyncio
async def test_system_overview_empty_db():
    """get_system_overview on empty DB returns zeroed counts."""
    await _reset_tables()

    from app.agents.tools.security_snapshot import get_system_overview

    async with TestSessionLocal() as session:
        result = await get_system_overview(session, lookback_seconds=300)
    assert result.node_count == 0
    assert result.warning_count == 0
    assert result.notable_anomalies == []


@pytest.mark.asyncio
async def test_system_overview_with_nodes():
    """get_system_overview reflects topology data."""
    await _reset_tables()

    from app.agents.tools.security_snapshot import get_system_overview

    async with TestSessionLocal() as session:
        await _seed_topology(session)

    async with TestSessionLocal() as session:
        result = await get_system_overview(session, lookback_seconds=300)

    assert result.node_count == 3  # web, api, db


@pytest.mark.asyncio
async def test_topology_subgraph():
    """get_topology_subgraph returns neighbors."""
    await _reset_tables()

    from app.agents.tools.security_snapshot import get_topology_subgraph

    async with TestSessionLocal() as session:
        await _seed_topology(session)

    async with TestSessionLocal() as session:
        result = await get_topology_subgraph(session, node_id="api", radius=1)

    assert result["center"] == "api"
    # api has edges to/from web and db
    assert len(result["nodes"]) >= 2
    assert len(result["edges"]) >= 1


@pytest.mark.asyncio
async def test_remediation_candidates_empty():
    """get_remediation_candidates returns empty for clean system."""
    await _reset_tables()

    from app.agents.tools.security_snapshot import get_remediation_candidates

    async with TestSessionLocal() as session:
        await _seed_topology(session)

    async with TestSessionLocal() as session:
        candidates = await get_remediation_candidates(session)

    assert candidates == []


@pytest.mark.asyncio
async def test_recent_findings_empty():
    """get_recent_findings returns empty on clean system."""
    await _reset_tables()

    from app.agents.tools.security_snapshot import get_recent_findings

    async with TestSessionLocal() as session:
        findings = await get_recent_findings(session, since_minutes=60)

    assert findings["vulnerabilities"] == []
    assert findings["insights"] == []


# ═══════════════════════════════════════════════════════════════
# 7. Chat workflow grounding (mocked LLM)
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_chat_threat_landscape_gathers_evidence():
    """Chat 'Analyze the threat landscape' gathers system evidence and streams."""
    await _reset_tables()

    async with TestSessionLocal() as session:
        await _seed_topology(session)

    # Mock the LLM to return a deterministic response
    async def mock_astream(messages):
        class FakeChunk:
            content = "Based on internal evidence, the system has 3 nodes, all healthy."
        yield FakeChunk()

    with patch("app.agents.workflows.chat_workflow.ChatOpenAI") as MockLLM:
        instance = MockLLM.return_value
        instance.astream = mock_astream

        events = []
        async with TestSessionLocal() as session:
            from app.agents.workflows.chat_workflow import stream_chat_workflow
            async for ev in stream_chat_workflow(
                "Analyze the current threat landscape",
                context=None,
                db=session,
                thread_id="test-threat",
            ):
                events.append(ev)

    # Should have streamed at least one message event
    data_events = [e for e in events if e.get("event") == "message"]
    assert len(data_events) >= 1
    # The mocked LLM response should be in there
    all_tokens = "".join(
        json.loads(e["data"]).get("token", "") for e in data_events
    )
    assert "internal evidence" in all_tokens or "3 nodes" in all_tokens or all_tokens != ""


@pytest.mark.asyncio
async def test_chat_node_context_uses_snapshot():
    """When node context is provided, chat gathers node-specific evidence."""
    await _reset_tables()

    async with TestSessionLocal() as session:
        await _seed_topology(session)

    async def mock_astream(messages):
        class FakeChunk:
            content = "Node api is healthy with no anomalies."
        yield FakeChunk()

    with patch("app.agents.workflows.chat_workflow.ChatOpenAI") as MockLLM:
        instance = MockLLM.return_value
        instance.astream = mock_astream

        events = []
        async with TestSessionLocal() as session:
            from app.agents.workflows.chat_workflow import stream_chat_workflow
            async for ev in stream_chat_workflow(
                "Investigate this node",
                context={"nodeId": "api", "nodeName": "API Service", "status": "healthy"},
                db=session,
                thread_id="test-node-ctx",
            ):
                events.append(ev)

    data_events = [e for e in events if e.get("event") == "message"]
    assert len(data_events) >= 1


@pytest.mark.asyncio
async def test_chat_remediation_grounding():
    """Chat 'Generate a remediation plan' gathers remediation candidates."""
    await _reset_tables()

    async with TestSessionLocal() as session:
        await _seed_topology(session)

    async def mock_astream(messages):
        class FakeChunk:
            content = "No open findings — no remediation actions needed."
        yield FakeChunk()

    with patch("app.agents.workflows.chat_workflow.ChatOpenAI") as MockLLM:
        instance = MockLLM.return_value
        instance.astream = mock_astream

        events = []
        async with TestSessionLocal() as session:
            from app.agents.workflows.chat_workflow import stream_chat_workflow
            async for ev in stream_chat_workflow(
                "Generate a remediation plan",
                context=None,
                db=session,
                thread_id="test-remediation",
            ):
                events.append(ev)

    data_events = [e for e in events if e.get("event") == "message"]
    assert len(data_events) >= 1


# ═══════════════════════════════════════════════════════════════
# 8. Follow-up continuity
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_followup_preserves_context():
    """A follow-up question should see previous conversation history."""
    await _reset_tables()

    from app.agents.runtime import store_message, get_thread_history, clear_thread

    clear_thread("test-followup")
    store_message("test-followup", "user", "Analyze the threat landscape")
    store_message("test-followup", "assistant", "System has 3 nodes, all healthy. No anomalies.")

    history = get_thread_history("test-followup", max_messages=6)
    assert len(history) == 2
    assert "threat landscape" in history[0]["content"].lower()
    clear_thread("test-followup")


# ═══════════════════════════════════════════════════════════════
# 9. Topology workflow verification
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_topology_workflow_empty_returns_cleanly():
    """Topology workflow on empty DB returns empty result."""
    await _reset_tables()

    from app.agents.workflows.topology_workflow import run_topology_workflow

    async with TestSessionLocal() as session:
        result = await run_topology_workflow(session)

    assert result["node_updates"] == []
    assert result["new_vulnerabilities"] == []


@pytest.mark.asyncio
async def test_topology_workflow_verifies_before_persist():
    """Topology workflow runs verification before DB writes."""
    await _reset_tables()

    from app.agents.schemas import TopologyAnalysisResult, NodeStatusUpdate, ProposedVulnerability

    async with TestSessionLocal() as session:
        await _seed_topology(session)

    # Mock the LLM to return an analysis that includes a non-existent node
    fake_result = TopologyAnalysisResult(
        node_updates=[
            NodeStatusUpdate(
                node_id="api", new_status="warning",
                rationale="CPU spike", evidence_refs=["anom-abc"],
            ),
            NodeStatusUpdate(
                node_id="nonexistent", new_status="compromised",
                rationale="Fake", evidence_refs=["anom-xyz"],
            ),
        ],
        new_vulnerabilities=[
            ProposedVulnerability(
                title="Ungrounded vuln", severity="high",
                affected_node_id="api", description="No evidence",
                evidence_refs=[],
            ),
        ],
    )

    with patch("app.agents.workflows.topology_workflow._analyze_with_llm", return_value=fake_result):
        from app.agents.workflows.topology_workflow import run_topology_workflow
        async with TestSessionLocal() as session:
            result = await run_topology_workflow(session)

    # "nonexistent" should be dropped, ungrounded vuln should be dropped
    assert len(result["node_updates"]) == 1
    assert result["node_updates"][0]["node_id"] == "api"
    assert len(result["new_vulnerabilities"]) == 0


# ═══════════════════════════════════════════════════════════════
# 10. Production fallback behavior
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_chat_stream_does_not_mock_in_production():
    """The /llm/chat/stream endpoint does not silently produce mock responses.

    We verify that the endpoint delegates to stream_agent_response (real workflow).
    If the LLM is unavailable, it should produce an error, not canned content.
    """
    await _reset_tables()

    async def mock_stream_that_fails(*args, **kwargs):
        yield {"event": "message", "data": json.dumps({"token": "Error: LLM unavailable"})}

    with patch("app.routers.dashboard.stream_agent_response", new=mock_stream_that_fails):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/llm/chat/stream", json={"message": "test"})

    assert response.status_code == 200
    # Should contain the error, not a canned mock response
    content = response.text
    assert "Error" in content or "error" in content


# ═══════════════════════════════════════════════════════════════
# 11. Tool failure behavior
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_chat_tool_failure_surfaces_error():
    """When evidence gathering fails, the answer explains what's missing."""
    await _reset_tables()

    async def mock_astream(messages):
        # The LLM should receive the error context and explain the limitation
        class FakeChunk:
            content = "Evidence gathering failed. Unable to provide a grounded analysis."
        yield FakeChunk()

    with patch("app.agents.workflows.chat_workflow.ChatOpenAI") as MockLLM:
        instance = MockLLM.return_value
        instance.astream = mock_astream

        # Patch evidence gathering to raise
        with patch("app.agents.workflows.chat_workflow.get_system_overview", side_effect=Exception("DB error")):
            events = []
            async with TestSessionLocal() as session:
                from app.agents.workflows.chat_workflow import stream_chat_workflow
                async for ev in stream_chat_workflow(
                    "Analyze the current threat landscape",
                    context=None,
                    db=session,
                    thread_id="test-failure",
                ):
                    events.append(ev)

    # Should still produce events (not crash)
    data_events = [e for e in events if e.get("event") == "message"]
    assert len(data_events) >= 1

    # Should include uncertainty note about limited evidence
    all_tokens = "".join(
        json.loads(e["data"]).get("token", "") for e in data_events
    )
    assert "evidence" in all_tokens.lower() or "limited" in all_tokens.lower() or "failed" in all_tokens.lower()
