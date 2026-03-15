"""Composite evidence tools that query internal DB state directly.

These tools provide high-signal evidence bundles for agent workflows.
They operate on the DB session directly — no HTTP self-calls.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import (
    NodeEvidence,
    SystemEvidence,
    TelemetryAnomaly,
)
from app.agents.tools.telemetry import get_resource_spikes_structured, SpikeCandidate
from app.models.telemetry import Container
from app.models.topology import (
    LLMInsight,
    RBACPolicy,
    TopologyEdge,
    TopologyNode,
    Vulnerability,
)

logger = logging.getLogger(__name__)


def _anomaly_id(container_ref: str, metric: str, window: int) -> str:
    """Generate a deterministic evidence ID for an anomaly."""
    raw = f"{container_ref}:{metric}:{window}"
    return "anom-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _spikes_to_anomalies(
    spikes: List[SpikeCandidate], lookback: int
) -> List[TelemetryAnomaly]:
    """Convert structured spike candidates to TelemetryAnomaly schema."""
    anomalies: List[TelemetryAnomaly] = []
    for s in spikes:
        if s.cpu_avg_cores > 0.01:
            anomalies.append(
                TelemetryAnomaly(
                    evidence_id=_anomaly_id(s.container_ref, "cpu", lookback),
                    container_ref=s.container_ref,
                    topology_node_id=s.topology_node_id,
                    metric_type="cpu",
                    observed_value=round(s.cpu_avg_cores, 4),
                    baseline_or_delta=round(s.cpu_delta_ns / 1e9, 2)
                    if s.cpu_delta_ns
                    else None,
                    unit="cores",
                    time_window_seconds=lookback,
                    severity_suggestion="warning" if s.cpu_avg_cores > 0.5 else "info",
                )
            )
        mem_delta_mb = abs(s.memory_delta_bytes) / (1024 * 1024)
        if mem_delta_mb > 10:
            anomalies.append(
                TelemetryAnomaly(
                    evidence_id=_anomaly_id(s.container_ref, "memory", lookback),
                    container_ref=s.container_ref,
                    topology_node_id=s.topology_node_id,
                    metric_type="memory",
                    observed_value=round(s.latest_memory_bytes / (1024 * 1024), 1),
                    baseline_or_delta=round(mem_delta_mb, 1),
                    unit="MB",
                    time_window_seconds=lookback,
                    severity_suggestion="warning" if mem_delta_mb > 100 else "info",
                )
            )
    return anomalies


async def get_security_snapshot(
    db: AsyncSession,
    node_id: Optional[str] = None,
    lookback_seconds: int = 900,
) -> NodeEvidence:
    """Return a structured NodeEvidence for a specific node.

    Gathers telemetry anomalies, vulnerabilities, insights, RBAC risks,
    and neighbor information from the DB.
    """
    # Fetch node
    result = await db.execute(select(TopologyNode).where(TopologyNode.id == node_id))
    node = result.scalar_one_or_none()
    if node is None:
        return NodeEvidence(
            node_id=node_id or "unknown",
            evidence_summary=f"Node '{node_id}' not found in topology.",
        )

    # Mapped containers
    cq = await db.execute(
        select(Container.reference_name).where(Container.topology_node_id == node_id)
    )
    containers = [r[0] for r in cq.all()]

    # Telemetry anomalies
    try:
        spikes = await get_resource_spikes_structured(lookback_seconds, db)
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        spikes = []
    node_anomalies = _spikes_to_anomalies(
        [s for s in spikes if s.topology_node_id == node_id], lookback_seconds
    )

    # Vulnerabilities
    vq = await db.execute(
        select(Vulnerability).where(Vulnerability.affected_node_id == node_id)
    )
    vulns = [
        {"id": v.id, "title": v.title, "severity": v.severity, "status": v.status}
        for v in vq.scalars().all()
    ]

    # LLM insights
    iq = await db.execute(select(LLMInsight).where(LLMInsight.node_id == node_id))
    insights = [
        {
            "id": i.id,
            "type": i.type,
            "summary": i.summary,
            "confidence": i.confidence,
        }
        for i in iq.scalars().all()
    ]

    # RBAC
    rq = await db.execute(select(RBACPolicy).where(RBACPolicy.scope == node_id))
    rbac = [
        {
            "role": r.role,
            "subject": r.subject,
            "risk_level": r.risk_level,
            "permissions": r.permissions,
        }
        for r in rq.scalars().all()
    ]

    # Neighbors
    eq = await db.execute(
        select(TopologyEdge).where(
            (TopologyEdge.source_id == node_id) | (TopologyEdge.target_id == node_id)
        )
    )
    neighbors = [
        {
            "source": e.source_id,
            "target": e.target_id,
            "kind": e.kind,
            "direction": "outgoing" if e.source_id == node_id else "incoming",
        }
        for e in eq.scalars().all()
    ]

    # Build summary
    summary_parts = []
    if node_anomalies:
        summary_parts.append(f"{len(node_anomalies)} telemetry anomalies detected")
    if vulns:
        summary_parts.append(
            f"{len(vulns)} vulnerabilities ({', '.join(v['severity'] for v in vulns)})"
        )
    if rbac:
        high_risk = [r for r in rbac if r["risk_level"] == "high"]
        if high_risk:
            summary_parts.append(f"{len(high_risk)} high-risk RBAC bindings")
    if not summary_parts:
        summary_parts.append("No notable issues detected")

    return NodeEvidence(
        node_id=node.id,
        label=node.label,
        node_type=node.type,
        effective_status=node.status,
        mapped_containers=containers,
        recent_anomalies=node_anomalies,
        vulnerabilities=vulns,
        llm_insights=insights,
        rbac_risks=rbac,
        neighbors=neighbors,
        evidence_summary="; ".join(summary_parts),
    )


async def get_system_overview(
    db: AsyncSession,
    lookback_seconds: int = 900,
) -> SystemEvidence:
    """Return a structured SystemEvidence for system-wide reasoning."""
    # All nodes
    nq = await db.execute(select(TopologyNode))
    nodes = nq.scalars().all()
    node_count = len(nodes)
    warning_nodes = [n for n in nodes if n.status == "warning"]
    compromised_nodes = [n for n in nodes if n.status == "compromised"]

    # Telemetry anomalies
    try:
        spikes = await get_resource_spikes_structured(lookback_seconds, db)
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        spikes = []
    anomalies = _spikes_to_anomalies(spikes, lookback_seconds)

    # High-priority vulnerabilities
    vq = await db.execute(
        select(Vulnerability).where(
            Vulnerability.severity.in_(["critical", "high"]),
            Vulnerability.status == "open",
        )
    )
    high_vulns = [
        {
            "id": v.id,
            "title": v.title,
            "severity": v.severity,
            "affected_node_id": v.affected_node_id,
        }
        for v in vq.scalars().all()
    ]

    # RBAC hotspots
    rq = await db.execute(select(RBACPolicy).where(RBACPolicy.risk_level == "high"))
    rbac_hotspots = [
        {"role": r.role, "subject": r.subject, "scope": r.scope}
        for r in rq.scalars().all()
    ]

    # Build risky node evidence (warning + compromised)
    risky_node_ids = [n.id for n in warning_nodes + compromised_nodes]
    risky_nodes: list[NodeEvidence] = []
    for nid in risky_node_ids[:10]:  # cap at 10
        try:
            ne = await get_security_snapshot(
                db, node_id=nid, lookback_seconds=lookback_seconds
            )
            risky_nodes.append(ne)
        except Exception:
            pass

    # Investigation priorities
    priorities = []
    if compromised_nodes:
        priorities.append(
            f"Investigate {len(compromised_nodes)} compromised node(s): "
            + ", ".join(n.id for n in compromised_nodes[:5])
        )
    if high_vulns:
        priorities.append(f"Address {len(high_vulns)} high/critical vulnerability(ies)")
    if warning_nodes:
        priorities.append(
            f"Monitor {len(warning_nodes)} warning node(s): "
            + ", ".join(n.id for n in warning_nodes[:5])
        )
    if anomalies:
        priorities.append(f"Review {len(anomalies)} telemetry anomalies")

    return SystemEvidence(
        top_risky_nodes=risky_nodes,
        notable_anomalies=anomalies,
        high_priority_vulnerabilities=high_vulns,
        rbac_hotspots=rbac_hotspots,
        node_count=node_count,
        warning_count=len(warning_nodes),
        compromised_count=len(compromised_nodes),
        recommended_investigation_priorities=priorities,
    )


async def get_topology_subgraph(
    db: AsyncSession,
    node_id: str,
    radius: int = 1,
) -> dict:
    """Return immediate graph context for a node (neighbors within radius)."""
    visited = {node_id}
    frontier = {node_id}
    edges_out = []

    for _ in range(radius):
        if not frontier:
            break
        eq = await db.execute(
            select(TopologyEdge).where(
                (TopologyEdge.source_id.in_(frontier))
                | (TopologyEdge.target_id.in_(frontier))
            )
        )
        new_frontier = set()
        for e in eq.scalars().all():
            edges_out.append(
                {"source": e.source_id, "target": e.target_id, "kind": e.kind}
            )
            for nid in (e.source_id, e.target_id):
                if nid not in visited:
                    visited.add(nid)
                    new_frontier.add(nid)
        frontier = new_frontier

    # Fetch node info
    nq = await db.execute(select(TopologyNode).where(TopologyNode.id.in_(visited)))
    nodes_out = [
        {"id": n.id, "label": n.label, "status": n.status, "type": n.type}
        for n in nq.scalars().all()
    ]

    return {"center": node_id, "nodes": nodes_out, "edges": edges_out}


async def get_recent_findings(
    db: AsyncSession,
    node_id: Optional[str] = None,
    since_minutes: int = 60,
) -> dict:
    """Return recent vulnerabilities, insights, and anomalies."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)

    # Vulnerabilities
    vq_stmt = select(Vulnerability).where(Vulnerability.discovered_at >= cutoff)
    if node_id:
        vq_stmt = vq_stmt.where(Vulnerability.affected_node_id == node_id)
    vq = await db.execute(vq_stmt)
    vulns = [
        {
            "id": v.id,
            "title": v.title,
            "severity": v.severity,
            "node": v.affected_node_id,
            "status": v.status,
        }
        for v in vq.scalars().all()
    ]

    # Insights
    iq_stmt = select(LLMInsight).where(LLMInsight.timestamp >= cutoff)
    if node_id:
        iq_stmt = iq_stmt.where(LLMInsight.node_id == node_id)
    iq = await db.execute(iq_stmt)
    insights = [
        {
            "id": i.id,
            "type": i.type,
            "summary": i.summary,
            "node": i.node_id,
            "confidence": i.confidence,
        }
        for i in iq.scalars().all()
    ]

    # Anomalies from telemetry
    try:
        spikes = await get_resource_spikes_structured(since_minutes * 60, db)
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        spikes = []
    if node_id:
        spikes = [s for s in spikes if s.topology_node_id == node_id]
    anomalies = _spikes_to_anomalies(spikes, since_minutes * 60)

    return {
        "vulnerabilities": vulns,
        "insights": insights,
        "anomalies": [a.model_dump() for a in anomalies],
        "since_minutes": since_minutes,
    }


async def get_remediation_candidates(
    db: AsyncSession,
    node_id: Optional[str] = None,
) -> list[dict]:
    """Map observed findings to specific remediation candidates.

    Grounded in current evidence, not a generic security checklist.
    """
    candidates = []

    # Open vulnerabilities
    vq_stmt = select(Vulnerability).where(Vulnerability.status == "open")
    if node_id:
        vq_stmt = vq_stmt.where(Vulnerability.affected_node_id == node_id)
    vq = await db.execute(vq_stmt)
    for v in vq.scalars().all():
        candidates.append(
            {
                "type": "vulnerability_fix",
                "title": f"Remediate: {v.title}",
                "severity": v.severity,
                "affected_node": v.affected_node_id,
                "evidence_ref": v.id,
                "description": v.description,
            }
        )

    # Warning/compromised nodes
    nq_stmt = select(TopologyNode).where(
        TopologyNode.status.in_(["warning", "compromised"])
    )
    if node_id:
        nq_stmt = nq_stmt.where(TopologyNode.id == node_id)
    nq = await db.execute(nq_stmt)
    for n in nq.scalars().all():
        if n.status == "compromised":
            candidates.append(
                {
                    "type": "containment",
                    "title": f"Isolate compromised node: {n.label}",
                    "severity": "critical",
                    "affected_node": n.id,
                    "evidence_ref": f"node-status-{n.id}",
                    "description": f"Node {n.label} is marked as compromised. Immediate containment recommended.",
                }
            )
        elif n.status == "warning":
            candidates.append(
                {
                    "type": "investigation",
                    "title": f"Investigate warning on: {n.label}",
                    "severity": "medium",
                    "affected_node": n.id,
                    "evidence_ref": f"node-status-{n.id}",
                    "description": f"Node {n.label} is in warning state. Further investigation recommended.",
                }
            )

    # High-risk RBAC
    rq_stmt = select(RBACPolicy).where(RBACPolicy.risk_level == "high")
    if node_id:
        rq_stmt = rq_stmt.where(RBACPolicy.scope == node_id)
    rq = await db.execute(rq_stmt)
    for r in rq.scalars().all():
        candidates.append(
            {
                "type": "rbac_tightening",
                "title": f"Review high-risk RBAC: {r.role} on {r.scope}",
                "severity": "high",
                "affected_node": r.scope,
                "evidence_ref": r.id,
                "description": f"Role '{r.role}' assigned to '{r.subject}' has high-risk permissions on scope '{r.scope}'.",
            }
        )

    return candidates
