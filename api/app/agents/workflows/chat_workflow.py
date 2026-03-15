"""Chat workflow: evidence-first security analyst interaction.

Stages:
  1. route_intent    — classify the user question
  2. gather_evidence — deterministically fetch relevant evidence
  3. react_gap_fill  — optional bounded tool use (max 2 iterations)
  4. synthesize      — generate a grounded answer from evidence
  5. verify          — ensure claims are supported, downgrade speculation
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.policies import (
    CHAT_ANALYST_OVERLAY,
    FINDING_EXPLANATION_OVERLAY,
    REMEDIATION_OVERLAY,
    build_system_prompt,
)
from app.agents.runtime import (
    classify_intent,
    get_thread_history,
    store_message,
    verify_chat_answer,
)
from app.agents.tools.security_snapshot import (
    get_recent_findings,
    get_remediation_candidates,
    get_security_snapshot,
    get_system_overview,
    get_topology_subgraph,
)

logger = logging.getLogger(__name__)


async def _gather_evidence(
    intent: str,
    db: AsyncSession,
    node_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministically gather the right evidence bundle for the intent."""
    evidence: Dict[str, Any] = {}

    try:
        if intent in ("system_threat_landscape", "general_followup"):
            overview = await get_system_overview(db, lookback_seconds=900)
            evidence["system_overview"] = overview.model_dump()

        elif intent == "node_investigation":
            if node_id:
                snapshot = await get_security_snapshot(db, node_id=node_id)
                evidence["node_snapshot"] = snapshot.model_dump()
                subgraph = await get_topology_subgraph(db, node_id=node_id, radius=1)
                evidence["subgraph"] = subgraph
            else:
                overview = await get_system_overview(db, lookback_seconds=900)
                evidence["system_overview"] = overview.model_dump()

        elif intent == "remediation_plan":
            candidates = await get_remediation_candidates(db, node_id=node_id)
            evidence["remediation_candidates"] = candidates
            if node_id:
                snapshot = await get_security_snapshot(db, node_id=node_id)
                evidence["node_snapshot"] = snapshot.model_dump()
            else:
                overview = await get_system_overview(db, lookback_seconds=900)
                evidence["system_overview"] = overview.model_dump()

        elif intent == "rbac_risk":
            if node_id:
                snapshot = await get_security_snapshot(db, node_id=node_id)
                evidence["node_snapshot"] = snapshot.model_dump()
            else:
                overview = await get_system_overview(db, lookback_seconds=900)
                evidence["system_overview"] = overview.model_dump()

        elif intent in ("vulnerability_summary", "explain_finding"):
            findings = await get_recent_findings(db, node_id=node_id, since_minutes=60)
            evidence["recent_findings"] = findings
            if node_id:
                snapshot = await get_security_snapshot(db, node_id=node_id)
                evidence["node_snapshot"] = snapshot.model_dump()

        else:
            # General: provide system overview
            overview = await get_system_overview(db, lookback_seconds=900)
            evidence["system_overview"] = overview.model_dump()

    except Exception as e:
        logger.error("Evidence gathering failed: %s", e, exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        evidence["_error"] = f"Evidence gathering partially failed: {str(e)}"

    return evidence


def _build_evidence_context(evidence: Dict[str, Any]) -> str:
    """Format gathered evidence into a context block for the LLM."""
    if not evidence or (len(evidence) == 1 and "_error" in evidence):
        return "No internal evidence could be gathered. Note this limitation in your response."

    parts = ["=== INTERNAL EVIDENCE (use this to ground your response) ===\n"]
    for key, val in evidence.items():
        if key == "_error":
            parts.append(f"⚠ {val}\n")
            continue
        # Compact JSON for LLM consumption
        try:
            formatted = json.dumps(val, indent=1, default=str)
        except (TypeError, ValueError):
            formatted = str(val)
        parts.append(f"--- {key} ---\n{formatted}\n")

    return "\n".join(parts)


def _select_overlays(intent: str) -> list[str]:
    """Pick the right policy overlays for the intent."""
    overlays = [CHAT_ANALYST_OVERLAY]
    if intent == "remediation_plan":
        overlays.append(REMEDIATION_OVERLAY)
    elif intent == "explain_finding":
        overlays.append(FINDING_EXPLANATION_OVERLAY)
    return overlays


async def stream_chat_workflow(
    user_msg: str,
    context: Optional[Dict[str, Any]],
    db: AsyncSession,
    thread_id: str = "default",
    history: Optional[List[Dict[str, str]]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Execute the chat workflow and stream SSE-compatible events.

    Workflow:
      1. route_intent
      2. gather_evidence (deterministic)
      3. synthesize_answer (LLM with structured evidence)
      4. verify_answer
    """
    # ── 1. Route intent ──
    node_id = context.get("nodeId") if context else None
    intent = classify_intent(user_msg, has_node_context=bool(node_id))

    # ── 2. Gather evidence ──
    yield {
        "event": "message",
        "data": json.dumps({"token": ""}),
    }  # keep connection alive

    evidence = await _gather_evidence(intent, db, node_id=node_id)
    evidence_context = _build_evidence_context(evidence)
    has_evidence = bool(evidence) and "_error" not in evidence

    # Collect evidence refs for verification
    evidence_refs: List[str] = []
    if "node_snapshot" in evidence:
        for a in evidence.get("node_snapshot", {}).get("recent_anomalies", []):
            evidence_refs.append(a.get("evidence_id", ""))
    if "system_overview" in evidence:
        for a in evidence.get("system_overview", {}).get("notable_anomalies", []):
            evidence_refs.append(a.get("evidence_id", ""))

    # ── 3. Synthesize answer ──
    overlays = _select_overlays(intent)
    system_prompt = build_system_prompt(*overlays)

    # Build message sequence
    messages = [SystemMessage(content=system_prompt)]

    # Add conversation history for continuity
    recent_history = history or get_thread_history(thread_id, max_messages=6)
    for msg in recent_history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    # Add node context if present
    if context:
        context_str = json.dumps(context, indent=2)
        messages.append(
            SystemMessage(
                content=f"The analyst is currently investigating this node:\n{context_str}"
            )
        )

    # Add evidence as system context
    messages.append(SystemMessage(content=evidence_context))

    # Add the user message
    messages.append(HumanMessage(content=user_msg))

    # Create LLM and stream
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1, max_tokens=2000)

    accumulated_answer = ""
    try:
        async for chunk in llm.astream(messages):
            if chunk.content and isinstance(chunk.content, str):
                accumulated_answer += chunk.content
                yield {
                    "event": "message",
                    "data": json.dumps({"token": chunk.content}),
                }
    except Exception as e:
        logger.error("LLM streaming failed: %s", e, exc_info=True)
        error_msg = (
            "\n\n**Error:** Failed to generate response. "
            "Evidence gathering completed but LLM synthesis failed."
        )
        if has_evidence:
            error_msg += (
                " Internal evidence was available but could not be synthesized."
            )
        yield {"event": "message", "data": json.dumps({"token": error_msg})}
        accumulated_answer = error_msg

    # ── 4. Verify answer ──
    verified = verify_chat_answer(accumulated_answer, evidence_refs, has_evidence)

    # Store in conversation memory
    store_message(thread_id, "user", user_msg)
    store_message(thread_id, "assistant", accumulated_answer)

    # Emit verification metadata as a final SSE event
    if verified.uncertainty_notes:
        notes_text = "\n\n---\n_" + "; ".join(verified.uncertainty_notes) + "_"
        yield {"event": "message", "data": json.dumps({"token": notes_text})}
