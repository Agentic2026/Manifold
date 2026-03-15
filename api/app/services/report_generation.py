"""Report generation service.

After every topology scan, two reports are generated and persisted:
  1. A **deep scan** report summarising node-status changes, new
     vulnerabilities, anomalies, and insights produced during the scan.
  2. A **security posture** snapshot capturing score, node-status
     counts, insight-type counts, and vulnerability-severity counts.

Even when nothing materially changed, a report entry is persisted with
a summary like "No material change since previous scan" and a stable
fingerprint so unchanged runs can be recognised.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.topology import (
    LLMInsight,
    SecurityReport,
    TopologyNode,
    Vulnerability,
)

logger = logging.getLogger(__name__)


def _fingerprint(data: dict) -> str:
    """Compute a stable hex digest from a canonical JSON representation."""
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


async def generate_reports(
    db: AsyncSession,
    scan_result: Dict[str, Any],
    *,
    trigger: str = "manual",
    detection_events: Optional[List[Dict[str, Any]]] = None,
    detection_summaries: Optional[List[Dict[str, Any]]] = None,
) -> List[SecurityReport]:
    """Generate a deep-scan report and a security-posture report.

    Parameters
    ----------
    db:
        Active database session (not committed by this function — caller
        must commit after all other writes).
    scan_result:
        The dict returned by ``run_topology_workflow``.
    trigger:
        How the scan was initiated (``"manual"`` | ``"scheduled"`` |
        ``"api"`` | ``"detection"``).
    detection_events:
        Structured detection events from the fast lane (optional).
    detection_summaries:
        Per-node detection summaries from the fast lane (optional).

    Returns
    -------
    list of two :class:`SecurityReport` ORM instances (already added to
    the session).
    """
    now = datetime.now(UTC)

    # ── Gather current state ────────────────────────────────
    nodes_q = await db.execute(select(TopologyNode))
    nodes = nodes_q.scalars().all()

    vulns_q = await db.execute(select(Vulnerability))
    vulns = vulns_q.scalars().all()

    insights_q = await db.execute(select(LLMInsight))
    insights = insights_q.scalars().all()

    # Node-status counts
    status_counts = {"healthy": 0, "warning": 0, "compromised": 0}
    for n in nodes:
        bucket = n.status if n.status in status_counts else "healthy"
        status_counts[bucket] += 1

    # Insight-type counts
    insight_counts = {"threat": 0, "anomaly": 0, "info": 0}
    for i in insights:
        bucket = i.type if i.type in insight_counts else "info"
        insight_counts[bucket] += 1

    # Vulnerability-severity counts
    vuln_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for v in vulns:
        bucket = v.severity if v.severity in vuln_counts else "low"
        vuln_counts[bucket] += 1

    # Determine max_status across all nodes
    if status_counts["compromised"] > 0:
        max_status = "compromised"
    elif status_counts["warning"] > 0:
        max_status = "warning"
    else:
        max_status = "healthy"

    # Simple score (mirrors _compute_security_score logic)
    score = 100
    score -= 20 * status_counts["compromised"]
    score -= 10 * status_counts["warning"]
    score -= 8 * vuln_counts["critical"]
    score -= 5 * vuln_counts["high"]
    score = max(0, score)

    # ── Extract scan deltas ────────────────────────────────
    node_updates = scan_result.get("node_updates") or []
    new_vulns = scan_result.get("new_vulnerabilities") or []
    new_insights = scan_result.get("new_insights") or []
    det_events = detection_events or []
    det_summaries = detection_summaries or []

    has_material_change = bool(node_updates or new_vulns or new_insights or det_events)

    # ── Deep-scan report ────────────────────────────────────
    deep_fp_data = {
        "node_updates": node_updates,
        "new_vulnerabilities": new_vulns,
        "new_insights": new_insights,
        "detection_event_ids": [e.get("id", "") for e in det_events],
    }
    deep_fingerprint = _fingerprint(deep_fp_data)

    if has_material_change:
        deep_title = "Deep Scan Report"
        lines: List[str] = []

        if det_events:
            lines.append("## Detection Events\n")
            for de in det_events:
                lines.append(
                    f"- **{de.get('title', 'Unnamed')}** "
                    f"(kind: `{de.get('kind', '?')}`, "
                    f"severity: `{de.get('severity', '?')}`, "
                    f"node: `{de.get('node_id', '?')}`)"
                )
            lines.append("")

        if det_summaries:
            lines.append("## Detection Summaries\n")
            for ds in det_summaries:
                lines.append(
                    f"- **{ds.get('node_id', '?')}**: "
                    f"{ds.get('detection_count', 0)} detection(s), "
                    f"max severity `{ds.get('max_severity', '?')}`, "
                    f"recommended status `{ds.get('recommended_status', '?')}`"
                )
            lines.append("")

        if node_updates:
            lines.append("## Node Status Changes\n")
            for u in node_updates:
                nid = u.get("node_id") or u.get("id", "?")
                new_st = u.get("new_status") or u.get("status", "?")
                rationale = u.get("rationale", "")
                lines.append(f"- **{nid}** → `{new_st}`: {rationale}")
            lines.append("")

        if new_vulns:
            lines.append("## New Vulnerabilities\n")
            for v in new_vulns:
                lines.append(
                    f"- **{v.get('title', 'Unnamed')}** "
                    f"(severity: `{v.get('severity', '?')}`, "
                    f"node: `{v.get('affected_node_id', '?')}`)"
                )
            lines.append("")

        if new_insights:
            lines.append("## New Insights\n")
            for ins in new_insights:
                lines.append(
                    f"- [{ins.get('insight_type', 'info')}] "
                    f"**{ins.get('summary', '')}** "
                    f"(confidence: {ins.get('confidence', 0):.0%})"
                )
            lines.append("")

        deep_details = "\n".join(lines)
        deep_summary = (
            f"{len(det_events)} detection(s), "
            f"{len(node_updates)} status change(s), "
            f"{len(new_vulns)} vulnerability(ies), "
            f"{len(new_insights)} insight(s)"
        )
    else:
        deep_title = "Deep Scan Report"
        deep_summary = "No material change since previous scan"
        deep_details = (
            "The scan completed successfully but found no new status "
            "changes, vulnerabilities, or insights."
        )

    deep_report = SecurityReport(
        id=f"rpt-{uuid.uuid4().hex}",
        report_kind="deep_scan",
        title=deep_title,
        summary=deep_summary,
        details_markdown=deep_details,
        created_at=now,
        max_status=max_status,
        fingerprint=deep_fingerprint,
        trigger=trigger,
        payload={
            "detection_event_count": len(det_events),
            "detection_event_ids": [e.get("id", "") for e in det_events],
            "affected_node_ids": list(
                set(e.get("node_id") for e in det_events if e.get("node_id"))
            ),
            "node_updates_count": len(node_updates),
            "new_vulnerabilities_count": len(new_vulns),
            "new_insights_count": len(new_insights),
        },
    )
    db.add(deep_report)

    # ── Security-posture report ─────────────────────────────
    posture_fp_data = {
        "score": score,
        "status_counts": status_counts,
        "insight_counts": insight_counts,
        "vuln_counts": vuln_counts,
    }
    posture_fingerprint = _fingerprint(posture_fp_data)

    posture_lines = [
        f"**Security Score:** {score}/100\n",
        "## Node Status",
        f"- Healthy: {status_counts['healthy']}",
        f"- Warning: {status_counts['warning']}",
        f"- Compromised: {status_counts['compromised']}",
        "",
        "## Insights",
        f"- Threats: {insight_counts['threat']}",
        f"- Anomalies: {insight_counts['anomaly']}",
        f"- Info: {insight_counts['info']}",
        "",
        "## Vulnerabilities",
        f"- Critical: {vuln_counts['critical']}",
        f"- High: {vuln_counts['high']}",
        f"- Medium: {vuln_counts['medium']}",
        f"- Low: {vuln_counts['low']}",
    ]

    posture_report = SecurityReport(
        id=f"rpt-{uuid.uuid4().hex}",
        report_kind="security_posture",
        title="Security Posture Snapshot",
        summary=f"Score {score}/100 — {max_status}",
        details_markdown="\n".join(posture_lines),
        created_at=now,
        max_status=max_status,
        fingerprint=posture_fingerprint,
        trigger=trigger,
        payload={
            "score": score,
            "status_counts": status_counts,
            "insight_counts": insight_counts,
            "vuln_counts": vuln_counts,
        },
    )
    db.add(posture_report)

    return [deep_report, posture_report]
