"""Topology workflow: evidence-first background analysis.

Uses the same shared schemas and policies as the chat workflow.
Stages:
  1. gather_evidence   — fetch topology DAG + telemetry using shared tools
  2. analyze_impact    — LLM analysis with structured output
  3. verify_updates    — verify proposals before persistence
  4. apply_updates     — write verified updates to DB
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.agents.policies import TOPOLOGY_ANALYSIS_OVERLAY, build_system_prompt
from app.agents.runtime import verify_topology_updates
from app.agents.schemas import (
    NodeStatusUpdate,
    ProposedInsight,
    ProposedVulnerability,
    TopologyAnalysisResult,
)
from app.agents.tools.security_snapshot import (
    get_system_overview,
    _spikes_to_anomalies,
)
from app.agents.tools.telemetry import get_resource_spikes_structured
from app.models.topology import (
    LLMInsight,
    TopologyEdge,
    TopologyNode,
    Vulnerability,
)

logger = logging.getLogger(__name__)


# ── LLM structured output schema ────────────────────────────
# This mirrors TopologyAnalysisResult but is used for with_structured_output


class LLMNodeUpdate(BaseModel):
    id: str = Field(description="TopologyNode ID to update")
    status: str = Field(description="'healthy', 'warning', or 'compromised'")
    rationale: str = Field(description="Brief explanation for the status change")
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="Evidence IDs supporting this change",
    )


class LLMVulnerability(BaseModel):
    title: str
    severity: str = Field(description="'critical', 'high', 'medium', or 'low'")
    affected_node_id: str
    description: str
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="Evidence IDs supporting this vulnerability",
    )


class LLMInsightOutput(BaseModel):
    node_id: str
    type: str = Field(description="'anomaly', 'threat', or 'info'")
    summary: str
    details: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: List[str] = Field(default_factory=list)


class LLMImpactAnalysis(BaseModel):
    node_updates: List[LLMNodeUpdate] = Field(default_factory=list)
    new_vulnerabilities: List[LLMVulnerability] = Field(default_factory=list)
    new_insights: List[LLMInsightOutput] = Field(default_factory=list)


# ── Workflow stages ──────────────────────────────────────────


async def _fetch_evidence(db: AsyncSession) -> Dict[str, Any]:
    """Gather structured evidence for topology analysis."""
    evidence: Dict[str, Any] = {}

    # Telemetry spikes
    try:
        spikes = await get_resource_spikes_structured(300, db)
        anomalies = _spikes_to_anomalies(spikes, 300)
        evidence["anomalies"] = [a.model_dump() for a in anomalies]
        evidence["spike_summaries"] = [s.summary_line() for s in spikes]
    except Exception as e:
        logger.error("Failed to fetch spikes: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        evidence["anomalies"] = []
        evidence["spike_summaries"] = []

    # Topology DAG
    nodes_result = await db.execute(select(TopologyNode))
    edges_result = await db.execute(select(TopologyEdge))

    nodes = [
        {"id": n.id, "label": n.label, "status": n.status, "type": n.type}
        for n in nodes_result.scalars().all()
    ]
    edges = [
        {"source": e.source_id, "target": e.target_id, "kind": e.kind}
        for e in edges_result.scalars().all()
    ]

    evidence["nodes"] = nodes
    evidence["edges"] = edges
    evidence["node_ids"] = {n["id"] for n in nodes}

    return evidence


async def _analyze_with_llm(evidence: Dict[str, Any]) -> TopologyAnalysisResult:
    """Use LLM with structured output and shared policy to analyze evidence."""
    system_prompt = build_system_prompt(TOPOLOGY_ANALYSIS_OVERLAY)

    evidence_block = (
        f"System DAG Nodes: {json.dumps(evidence.get('nodes', []), indent=1)}\n\n"
        f"System DAG Edges: {json.dumps(evidence.get('edges', []), indent=1)}\n\n"
        f"Telemetry Anomalies: {json.dumps(evidence.get('anomalies', []), indent=1)}\n\n"
        f"Spike Summaries:\n" + "\n".join(evidence.get("spike_summaries", []))
    )

    full_prompt = (
        f"{system_prompt}\n\n"
        f"=== EVIDENCE ===\n{evidence_block}\n\n"
        "Analyze the evidence and return structured updates. "
        "Remember: telemetry spikes alone → 'warning', NOT 'compromised'. "
        "Include evidence_refs for every proposed change."
    )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0).with_structured_output(
        LLMImpactAnalysis
    )

    try:
        result: LLMImpactAnalysis = await llm.ainvoke(
            [SystemMessage(content=full_prompt)]
        )

        # Convert to shared schema
        return TopologyAnalysisResult(
            node_updates=[
                NodeStatusUpdate(
                    node_id=u.id,
                    new_status=u.status,
                    rationale=u.rationale,
                    evidence_refs=u.evidence_refs,
                )
                for u in result.node_updates
            ],
            new_vulnerabilities=[
                ProposedVulnerability(
                    title=v.title,
                    severity=v.severity,
                    affected_node_id=v.affected_node_id,
                    description=v.description,
                    evidence_refs=v.evidence_refs,
                )
                for v in result.new_vulnerabilities
            ],
            new_insights=[
                ProposedInsight(
                    node_id=i.node_id,
                    insight_type=i.type,
                    summary=i.summary,
                    details=i.details,
                    confidence=i.confidence,
                    evidence_refs=i.evidence_refs,
                )
                for i in result.new_insights
            ],
        )
    except Exception as e:
        logger.error("LLM topology analysis failed: %s", e)
        return TopologyAnalysisResult()


async def _apply_verified_updates(
    db: AsyncSession, result: TopologyAnalysisResult
) -> Dict[str, Any]:
    """Write verified updates to the database."""
    applied = {"node_updates": 0, "new_vulnerabilities": 0, "new_insights": 0}

    for u in result.node_updates:
        node_q = await db.execute(
            select(TopologyNode).where(TopologyNode.id == u.node_id)
        )
        node = node_q.scalar_one_or_none()
        if node and node.status != "compromised":
            node.status = u.new_status
            applied["node_updates"] += 1

    for v in result.new_vulnerabilities:
        new_vuln = Vulnerability(
            id=f"vuln-{uuid.uuid4().hex}",
            title=v.title,
            severity=v.severity,
            affected_node_id=v.affected_node_id,
            description=v.description,
            status="open",
        )
        db.add(new_vuln)
        applied["new_vulnerabilities"] += 1

    for i in result.new_insights:
        new_ins = LLMInsight(
            id=f"ins-{uuid.uuid4().hex}",
            node_id=i.node_id,
            type=i.insight_type,
            summary=i.summary,
            details=i.details,
            confidence=i.confidence,
        )
        db.add(new_ins)
        applied["new_insights"] += 1

    await db.commit()
    return applied


# ── Main entrypoint ──────────────────────────────────────────


async def run_topology_workflow(db: AsyncSession) -> Dict[str, Any]:
    """Execute the full topology analysis workflow.

    1. Gather evidence (deterministic)
    2. Analyze with LLM (structured output)
    3. Verify proposals
    4. Apply verified updates
    """
    try:
        # 1. Gather evidence
        evidence = await _fetch_evidence(db)

        if not evidence.get("nodes"):
            logger.info("No topology nodes found — skipping analysis")
            return {"node_updates": [], "new_vulnerabilities": [], "new_insights": []}

        # 2. Analyze
        analysis = await _analyze_with_llm(evidence)

        # 3. Verify
        verified = verify_topology_updates(analysis, evidence.get("node_ids", set()))

        # 4. Apply
        applied = await _apply_verified_updates(db, verified)
        logger.info("Topology analysis applied: %s", applied)

        return verified.model_dump()

    except Exception as e:
        logger.error("Topology workflow failed: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        return {"node_updates": [], "new_vulnerabilities": [], "new_insights": []}
