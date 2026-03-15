"""Shared Pydantic schemas for Manifold's evidence-first agent system.

Every agentic component (chat workflow, topology workflow, composite tools)
uses these models so that intermediate and final reasoning artifacts have a
consistent structure.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Telemetry evidence ──────────────────────────────────────


class TelemetryAnomaly(BaseModel):
    """A single container-level telemetry anomaly."""

    evidence_id: str = Field(description="Unique identifier for this anomaly")
    container_ref: str = Field(description="Container reference name")
    topology_node_id: Optional[str] = Field(
        default=None, description="Authoritative topology node mapping (if known)"
    )
    metric_type: str = Field(description="'cpu', 'memory', or 'network'")
    observed_value: float = Field(description="Observed metric value")
    baseline_or_delta: Optional[float] = Field(
        default=None, description="Baseline or delta value for comparison"
    )
    unit: str = Field(
        default="", description="Unit of measurement (e.g. 'cores', 'MB', 'Mbps')"
    )
    time_window_seconds: int = Field(description="Lookback window in seconds")
    severity_suggestion: str = Field(
        default="info",
        description="Suggested severity: 'info', 'warning'. Only 'compromised' with corroboration.",
    )


# ── Node-level evidence ─────────────────────────────────────


class NodeEvidence(BaseModel):
    """Aggregated evidence bundle for a single topology node."""

    node_id: str
    label: str = ""
    node_type: str = ""
    effective_status: str = "unknown"
    mapped_containers: List[str] = Field(default_factory=list)
    recent_anomalies: List[TelemetryAnomaly] = Field(default_factory=list)
    vulnerabilities: List[dict] = Field(default_factory=list)
    llm_insights: List[dict] = Field(default_factory=list)
    rbac_risks: List[dict] = Field(default_factory=list)
    neighbors: List[dict] = Field(default_factory=list)
    evidence_summary: str = ""


# ── System-level evidence ────────────────────────────────────


class SystemEvidence(BaseModel):
    """High-level evidence snapshot for system-wide reasoning."""

    top_risky_nodes: List[NodeEvidence] = Field(default_factory=list)
    notable_anomalies: List[TelemetryAnomaly] = Field(default_factory=list)
    high_priority_vulnerabilities: List[dict] = Field(default_factory=list)
    rbac_hotspots: List[dict] = Field(default_factory=list)
    suspicious_dependency_chains: List[dict] = Field(default_factory=list)
    recommended_investigation_priorities: List[str] = Field(default_factory=list)
    node_count: int = 0
    warning_count: int = 0
    compromised_count: int = 0


# ── Remediation ──────────────────────────────────────────────


class RemediationAction(BaseModel):
    """A single evidence-grounded remediation recommendation."""

    title: str
    rationale: str
    affected_nodes: List[str] = Field(default_factory=list)
    priority: str = Field(
        default="medium", description="'critical', 'high', 'medium', 'low'"
    )
    evidence_refs: List[str] = Field(
        default_factory=list, description="Evidence IDs supporting this action"
    )
    expected_effect: str = ""
    operational_tradeoff: str = ""


# ── Verified agent answer ────────────────────────────────────


class VerifiedAgentAnswer(BaseModel):
    """Final verified output from any agent workflow."""

    answer_text: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_refs: List[str] = Field(default_factory=list)
    uncertainty_notes: List[str] = Field(default_factory=list)
    follow_up_suggestions: List[str] = Field(default_factory=list)
    remediation_actions: List[RemediationAction] = Field(default_factory=list)


# ── Topology analysis output (shared with topology workflow) ─


class NodeStatusUpdate(BaseModel):
    """Proposed status change for a topology node."""

    node_id: str
    new_status: str = Field(description="'healthy', 'warning', or 'compromised'")
    rationale: str
    evidence_refs: List[str] = Field(default_factory=list)


class ProposedVulnerability(BaseModel):
    """A vulnerability proposed by the analysis pipeline (pre-verification)."""

    title: str
    severity: str
    affected_node_id: str
    description: str
    evidence_refs: List[str] = Field(default_factory=list)


class ProposedInsight(BaseModel):
    """An LLM insight proposed by analysis (pre-verification)."""

    node_id: str
    insight_type: str = Field(description="'anomaly', 'threat', or 'info'")
    summary: str
    details: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: List[str] = Field(default_factory=list)


class TopologyAnalysisResult(BaseModel):
    """Structured output from topology analysis — used for verification."""

    node_updates: List[NodeStatusUpdate] = Field(default_factory=list)
    new_vulnerabilities: List[ProposedVulnerability] = Field(default_factory=list)
    new_insights: List[ProposedInsight] = Field(default_factory=list)
