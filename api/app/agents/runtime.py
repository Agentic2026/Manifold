"""Agent runtime: shared verification, conversation memory, and helpers.

Provides verification stages and conversation continuity that are used
by both the chat and topology workflows.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.agents.schemas import (
    NodeStatusUpdate,
    ProposedInsight,
    ProposedVulnerability,
    TopologyAnalysisResult,
    VerifiedAgentAnswer,
)

logger = logging.getLogger(__name__)

# ── Conversation memory ──────────────────────────────────────

# Thread-scoped in-memory conversation store.
# Bounded to MAX_HISTORY_PER_THREAD messages per thread.
MAX_HISTORY_PER_THREAD = 20

_thread_store: Dict[str, List[Dict[str, str]]] = defaultdict(list)


def store_message(thread_id: str, role: str, content: str) -> None:
    """Append a message to thread history, evicting oldest if over limit."""
    history = _thread_store[thread_id]
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY_PER_THREAD:
        _thread_store[thread_id] = history[-MAX_HISTORY_PER_THREAD:]


def get_thread_history(thread_id: str, max_messages: int = 10) -> List[Dict[str, str]]:
    """Return recent messages for a thread."""
    return _thread_store.get(thread_id, [])[-max_messages:]


def clear_thread(thread_id: str) -> None:
    """Clear history for a thread."""
    _thread_store.pop(thread_id, None)


# ── Chat answer verification ────────────────────────────────


def verify_chat_answer(
    answer_text: str,
    evidence_refs: List[str],
    has_evidence: bool,
) -> VerifiedAgentAnswer:
    """Post-process a chat answer to add uncertainty notes.

    This is a deterministic verification step that checks whether the
    answer makes concrete claims without evidence backing.
    """
    uncertainty_notes: List[str] = []

    if not has_evidence:
        uncertainty_notes.append(
            "Limited internal evidence was available. "
            "This response may include general guidance rather than project-specific analysis."
        )

    # Heuristic: if answer is very long but no evidence refs, flag it
    if len(answer_text) > 500 and not evidence_refs:
        uncertainty_notes.append(
            "This response was generated without specific evidence references."
        )

    # Confidence: higher if evidence exists
    confidence = 0.8 if has_evidence and evidence_refs else 0.4

    return VerifiedAgentAnswer(
        answer_text=answer_text,
        confidence=confidence,
        evidence_refs=evidence_refs,
        uncertainty_notes=uncertainty_notes,
    )


# ── Topology verification ───────────────────────────────────


def verify_topology_updates(
    result: TopologyAnalysisResult,
    known_node_ids: set[str],
) -> TopologyAnalysisResult:
    """Verify proposed topology updates before persistence.

    - Removes updates for non-existent nodes.
    - Downgrades 'compromised' to 'warning' if only telemetry evidence.
    - Removes vulnerabilities/insights for non-existent nodes.
    """
    verified_updates: List[NodeStatusUpdate] = []
    for u in result.node_updates:
        if u.node_id not in known_node_ids:
            logger.warning("Dropping update for unknown node: %s", u.node_id)
            continue
        # Downgrade compromised if evidence is only telemetry-based
        if u.new_status == "compromised":
            refs = u.evidence_refs
            has_non_telemetry = any(not r.startswith("anom-") for r in refs)
            if not has_non_telemetry:
                logger.info(
                    "Downgrading node %s from compromised to warning (telemetry-only evidence)",
                    u.node_id,
                )
                u = NodeStatusUpdate(
                    node_id=u.node_id,
                    new_status="warning",
                    rationale=u.rationale + " [Downgraded: telemetry-only evidence]",
                    evidence_refs=u.evidence_refs,
                )
        verified_updates.append(u)

    verified_vulns: List[ProposedVulnerability] = []
    for v in result.new_vulnerabilities:
        if v.affected_node_id not in known_node_ids:
            logger.warning(
                "Dropping vulnerability for unknown node: %s", v.affected_node_id
            )
            continue
        if not v.evidence_refs:
            logger.warning("Dropping vulnerability without evidence refs: %s", v.title)
            continue
        verified_vulns.append(v)

    verified_insights: List[ProposedInsight] = []
    for i in result.new_insights:
        if i.node_id not in known_node_ids:
            logger.warning("Dropping insight for unknown node: %s", i.node_id)
            continue
        verified_insights.append(i)

    return TopologyAnalysisResult(
        node_updates=verified_updates,
        new_vulnerabilities=verified_vulns,
        new_insights=verified_insights,
    )


# ── Intent routing ───────────────────────────────────────────

INTENT_KEYWORDS = {
    "system_threat_landscape": [
        "threat landscape",
        "system status",
        "overview",
        "security posture",
        "what's happening",
        "current threats",
        "system health",
    ],
    "node_investigation": [
        "investigate",
        "node",
        "service",
        "container",
        "what about",
        "tell me about",
        "status of",
        "check on",
    ],
    "remediation_plan": [
        "remediation",
        "remediate",
        "fix",
        "mitigate",
        "action plan",
        "what should we do",
        "how to fix",
        "containment",
    ],
    "rbac_risk": [
        "rbac",
        "role",
        "permission",
        "access control",
        "privilege",
    ],
    "vulnerability_summary": [
        "vulnerability",
        "vulnerabilities",
        "cve",
        "exploit",
    ],
    "explain_finding": [
        "explain",
        "what does this mean",
        "finding",
        "insight",
        "why",
    ],
}


def classify_intent(message: str, has_node_context: bool = False) -> str:
    """Classify a user message into an intent category.

    Simple keyword-based classification. Falls back to node_investigation
    when node context is present, or general_followup otherwise.
    """
    msg_lower = message.lower()
    scores: Dict[str, int] = defaultdict(int)

    for intent, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in msg_lower:
                scores[intent] += 1

    if scores:
        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        if scores[best] > 0:
            return best

    if has_node_context:
        return "node_investigation"
    return "general_followup"
