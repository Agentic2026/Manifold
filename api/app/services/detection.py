"""Deterministic detection lane.

Runs continuously after telemetry ingestion and emits structured
:class:`DetectionEvent` instances.  This is the **fast lane** — it
never waits for an LLM and updates topology-visible state immediately.

Detector families
-----------------
1. CPU abuse / sustained compute spike
2. Memory staging / sudden memory surge
3. Egress burst / exfil-like transfer
4. Beaconing-like periodic network behaviour
5. Filesystem churn / staging (when data is available)
6. Multi-signal correlation across the same node/container
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import (
    DetectionEvent,
    DetectionEvidenceRef,
    NodeDetectionSummary,
)
from app.agents.tools.telemetry import _extract_cpu_total, _extract_memory_bytes
from app.core.config import settings
from app.models.telemetry import Container, ContainerMetricSnapshot
from app.models.topology import TopologyNode

logger = logging.getLogger(__name__)


# ── Threshold profiles ──────────────────────────────────────

_PROFILES: Dict[str, Dict[str, Any]] = {
    "normal": {
        "cpu_avg_cores": 0.8,
        "memory_surge_mb": 200,
        "egress_mbps": 50.0,
        "beaconing_min_intervals": 5,
        "beaconing_cv_threshold": 0.35,
        "filesystem_churn_mb": 500,
    },
    "demo": {
        "cpu_avg_cores": 0.15,
        "memory_surge_mb": 30,
        "egress_mbps": 5.0,
        "beaconing_min_intervals": 3,
        "beaconing_cv_threshold": 0.55,
        "filesystem_churn_mb": 50,
    },
}


def _get_thresholds() -> Dict[str, Any]:
    profile = getattr(settings, "detection_profile", "normal")
    return _PROFILES.get(profile, _PROFILES["normal"])


def _det_id(kind: str, ref: str, window: int) -> str:
    raw = f"{kind}:{ref}:{window}"
    return "det-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Individual detectors ────────────────────────────────────


def _detect_cpu_abuse(
    container_ref: str,
    node_id: Optional[str],
    snapshots: list,
    lookback: int,
    thresholds: dict,
) -> Optional[DetectionEvent]:
    """Detect sustained high CPU usage."""
    if len(snapshots) < 2:
        return None

    first, last = snapshots[0], snapshots[-1]
    cpu_first = _extract_cpu_total(first.cpu_stats or {})
    cpu_last = _extract_cpu_total(last.cpu_stats or {})
    if cpu_first is None or cpu_last is None:
        return None

    elapsed = (last.timestamp - first.timestamp).total_seconds()
    if elapsed <= 0:
        return None

    cpu_delta_ns = cpu_last - cpu_first
    avg_cores = cpu_delta_ns / (elapsed * 1e9)

    threshold = thresholds["cpu_avg_cores"]
    if avg_cores < threshold:
        return None

    severity = "critical" if avg_cores > threshold * 3 else "warning"
    confidence = min(1.0, avg_cores / (threshold * 4))

    return DetectionEvent(
        id=_det_id("cpu_abuse", container_ref, lookback),
        kind="cpu_abuse",
        node_id=node_id,
        container_id=container_ref,
        severity=severity,
        confidence=round(confidence, 2),
        title=f"Sustained CPU spike: {avg_cores:.2f} cores",
        summary=(
            f"Container {container_ref} averaged {avg_cores:.2f} CPU cores "
            f"over {elapsed:.0f}s (threshold: {threshold})."
        ),
        metrics={"avg_cores": round(avg_cores, 4), "elapsed_seconds": round(elapsed, 1)},
        detected_at=datetime.now(UTC).isoformat(),
        lookback_seconds=lookback,
        evidence_refs=[
            DetectionEvidenceRef(
                ref_type="metric_snapshot",
                ref_id=str(last.id),
                description=f"CPU delta {cpu_delta_ns} ns over {elapsed:.0f}s",
            )
        ],
    )


def _detect_memory_staging(
    container_ref: str,
    node_id: Optional[str],
    snapshots: list,
    lookback: int,
    thresholds: dict,
) -> Optional[DetectionEvent]:
    """Detect sudden memory surge."""
    if len(snapshots) < 2:
        return None

    first, last = snapshots[0], snapshots[-1]
    mem_first = _extract_memory_bytes(first.memory_stats or {})
    mem_last = _extract_memory_bytes(last.memory_stats or {})
    if mem_first is None or mem_last is None:
        return None

    delta_mb = (mem_last - mem_first) / (1024 * 1024)
    threshold = thresholds["memory_surge_mb"]
    if delta_mb < threshold:
        return None

    severity = "critical" if delta_mb > threshold * 5 else "warning"
    confidence = min(1.0, delta_mb / (threshold * 6))

    return DetectionEvent(
        id=_det_id("memory_staging", container_ref, lookback),
        kind="memory_staging",
        node_id=node_id,
        container_id=container_ref,
        severity=severity,
        confidence=round(confidence, 2),
        title=f"Memory surge: +{delta_mb:.1f} MB",
        summary=(
            f"Container {container_ref} memory grew by {delta_mb:.1f} MB "
            f"(threshold: {threshold} MB)."
        ),
        metrics={
            "delta_mb": round(delta_mb, 1),
            "current_mb": round(mem_last / (1024 * 1024), 1),
        },
        detected_at=datetime.now(UTC).isoformat(),
        lookback_seconds=lookback,
        evidence_refs=[
            DetectionEvidenceRef(
                ref_type="metric_snapshot",
                ref_id=str(last.id),
                description=f"Memory delta {delta_mb:.1f} MB",
            )
        ],
    )


def _net_bytes_from_snapshot(snap: ContainerMetricSnapshot) -> tuple[float, float]:
    """Extract (rx_bytes, tx_bytes) from a snapshot's network_stats."""
    net = snap.network_stats
    rx, tx = 0.0, 0.0
    if net and isinstance(net, dict):
        if "interfaces" in net:
            for iface in net["interfaces"]:
                rx += iface.get("rx_bytes", 0)
                tx += iface.get("tx_bytes", 0)
        else:
            rx += net.get("rx_bytes", 0)
            tx += net.get("tx_bytes", 0)
    return rx, tx


def _detect_egress_burst(
    container_ref: str,
    node_id: Optional[str],
    snapshots: list,
    lookback: int,
    thresholds: dict,
) -> Optional[DetectionEvent]:
    """Detect exfil-like egress bursts."""
    if len(snapshots) < 2:
        return None

    first, last = snapshots[0], snapshots[-1]
    _, tx_first = _net_bytes_from_snapshot(first)
    _, tx_last = _net_bytes_from_snapshot(last)

    elapsed = (last.timestamp - first.timestamp).total_seconds()
    if elapsed <= 0:
        return None

    tx_rate_bps = max(0, tx_last - tx_first) / elapsed
    tx_mbps = (tx_rate_bps * 8) / 1_000_000

    threshold = thresholds["egress_mbps"]
    if tx_mbps < threshold:
        return None

    severity = "critical" if tx_mbps > threshold * 5 else "warning"
    confidence = min(1.0, tx_mbps / (threshold * 6))

    return DetectionEvent(
        id=_det_id("egress_burst", container_ref, lookback),
        kind="egress_burst",
        node_id=node_id,
        container_id=container_ref,
        severity=severity,
        confidence=round(confidence, 2),
        title=f"Egress burst: {tx_mbps:.1f} Mbps",
        summary=(
            f"Container {container_ref} egress rate {tx_mbps:.1f} Mbps "
            f"(threshold: {threshold} Mbps)."
        ),
        metrics={"egress_mbps": round(tx_mbps, 2), "elapsed_seconds": round(elapsed, 1)},
        detected_at=datetime.now(UTC).isoformat(),
        lookback_seconds=lookback,
        evidence_refs=[
            DetectionEvidenceRef(
                ref_type="metric_snapshot",
                ref_id=str(last.id),
                description=f"TX rate {tx_mbps:.1f} Mbps",
            )
        ],
    )


def _detect_beaconing(
    container_ref: str,
    node_id: Optional[str],
    snapshots: list,
    lookback: int,
    thresholds: dict,
) -> Optional[DetectionEvent]:
    """Detect beaconing-like periodic outbound network behaviour.

    Looks for regular intervals between outbound traffic increments,
    which is characteristic of C2 beaconing.
    """
    if len(snapshots) < thresholds["beaconing_min_intervals"] + 1:
        return None

    # Compute egress deltas between consecutive snapshots
    intervals: list[float] = []
    prev_tx = None
    prev_ts = None
    for snap in snapshots:
        _, tx = _net_bytes_from_snapshot(snap)
        if prev_tx is not None and prev_ts is not None:
            delta_bytes = tx - prev_tx
            delta_secs = (snap.timestamp - prev_ts).total_seconds()
            if delta_bytes > 0 and delta_secs > 0:
                intervals.append(delta_secs)
        prev_tx = tx
        prev_ts = snap.timestamp

    min_intervals = thresholds["beaconing_min_intervals"]
    if len(intervals) < min_intervals:
        return None

    # Coefficient of variation — low CV means regular intervals
    mean_interval = sum(intervals) / len(intervals)
    if mean_interval <= 0:
        return None
    variance = sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)
    std_dev = variance ** 0.5
    cv = std_dev / mean_interval

    cv_threshold = thresholds["beaconing_cv_threshold"]
    if cv > cv_threshold:
        return None

    severity = "warning"
    confidence = round(max(0.3, min(1.0, 1.0 - cv)), 2)

    return DetectionEvent(
        id=_det_id("beaconing", container_ref, lookback),
        kind="beaconing",
        node_id=node_id,
        container_id=container_ref,
        severity=severity,
        confidence=confidence,
        title=f"Beaconing pattern: ~{mean_interval:.0f}s interval (CV={cv:.2f})",
        summary=(
            f"Container {container_ref} shows periodic outbound traffic "
            f"with mean interval {mean_interval:.1f}s and CV {cv:.2f} "
            f"({len(intervals)} intervals)."
        ),
        metrics={
            "mean_interval_seconds": round(mean_interval, 1),
            "cv": round(cv, 3),
            "interval_count": len(intervals),
        },
        detected_at=datetime.now(UTC).isoformat(),
        lookback_seconds=lookback,
        evidence_refs=[
            DetectionEvidenceRef(
                ref_type="metric_snapshot",
                ref_id=str(snapshots[-1].id),
                description=f"{len(intervals)} periodic egress intervals",
            )
        ],
    )


def _detect_filesystem_churn(
    container_ref: str,
    node_id: Optional[str],
    snapshots: list,
    lookback: int,
    thresholds: dict,
) -> Optional[DetectionEvent]:
    """Detect rapid filesystem writes / staging."""
    if len(snapshots) < 2:
        return None

    def _fs_usage(snap: ContainerMetricSnapshot) -> float:
        fs = snap.filesystem_stats
        if not fs:
            return 0.0
        total = 0.0
        if isinstance(fs, list):
            for entry in fs:
                total += entry.get("usage", 0)
        elif isinstance(fs, dict):
            total += fs.get("usage", 0)
        return total

    usage_first = _fs_usage(snapshots[0])
    usage_last = _fs_usage(snapshots[-1])
    delta_mb = (usage_last - usage_first) / (1024 * 1024)

    threshold = thresholds["filesystem_churn_mb"]
    if delta_mb < threshold:
        return None

    severity = "warning"
    confidence = min(1.0, delta_mb / (threshold * 3))

    return DetectionEvent(
        id=_det_id("filesystem_churn", container_ref, lookback),
        kind="filesystem_churn",
        node_id=node_id,
        container_id=container_ref,
        severity=severity,
        confidence=round(confidence, 2),
        title=f"Filesystem churn: +{delta_mb:.1f} MB",
        summary=(
            f"Container {container_ref} filesystem usage grew by {delta_mb:.1f} MB "
            f"(threshold: {threshold} MB)."
        ),
        metrics={"delta_mb": round(delta_mb, 1)},
        detected_at=datetime.now(UTC).isoformat(),
        lookback_seconds=lookback,
        evidence_refs=[
            DetectionEvidenceRef(
                ref_type="metric_snapshot",
                ref_id=str(snapshots[-1].id),
                description=f"FS delta {delta_mb:.1f} MB",
            )
        ],
    )


def _detect_multi_signal(
    node_id: str,
    events: List[DetectionEvent],
) -> Optional[DetectionEvent]:
    """Correlate multiple signals on the same node for a stronger detection."""
    if len(events) < 2:
        return None

    kinds = sorted(set(e.kind for e in events))
    max_sev = "critical" if any(e.severity == "critical" for e in events) else "warning"
    avg_conf = sum(e.confidence for e in events) / len(events)
    confidence = min(1.0, avg_conf + 0.15)

    lookback = max(e.lookback_seconds for e in events)

    return DetectionEvent(
        id=_det_id("multi_signal_correlation", node_id, lookback),
        kind="multi_signal_correlation",
        node_id=node_id,
        container_id=None,
        severity=max_sev,
        confidence=round(confidence, 2),
        title=f"Multi-signal correlation: {', '.join(kinds)}",
        summary=(
            f"Node {node_id} exhibits correlated suspicious behaviour across "
            f"{len(events)} detections ({', '.join(kinds)})."
        ),
        metrics={
            "signal_count": len(events),
            "signal_kinds": kinds,
            "constituent_ids": [e.id for e in events],
        },
        detected_at=datetime.now(UTC).isoformat(),
        lookback_seconds=lookback,
        evidence_refs=[
            DetectionEvidenceRef(
                ref_type="anomaly",
                ref_id=e.id,
                description=e.title,
            )
            for e in events
        ],
    )


# ── Severity / status helpers ───────────────────────────────

_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


def _max_severity(a: str, b: str) -> str:
    return a if _SEVERITY_ORDER.get(a, 0) >= _SEVERITY_ORDER.get(b, 0) else b


def _severity_to_status(severity: str, has_multi_signal: bool) -> str:
    """Map detection severity to a recommended topology node status.

    Conservative: telemetry-only evidence stays at warning.
    Multi-signal correlation can push to ``warning`` (never hard
    ``compromised`` — that requires LLM confirmation or manual action).
    """
    if severity == "critical" and has_multi_signal:
        return "warning"  # strong warning — LLM can escalate
    if severity in ("warning", "critical"):
        return "warning"
    return "healthy"


# ── Main entry point ────────────────────────────────────────


async def run_detectors(
    db: AsyncSession,
    lookback_seconds: int = 300,
) -> tuple[List[DetectionEvent], List[NodeDetectionSummary]]:
    """Run all detectors on recent telemetry and return structured results.

    Returns
    -------
    (events, summaries)
        *events* is the flat list of all detection events.
        *summaries* is one :class:`NodeDetectionSummary` per affected node.
    """
    thresholds = _get_thresholds()
    cutoff = datetime.now(UTC) - timedelta(seconds=lookback_seconds)

    # Fetch snapshots with container metadata
    stmt = (
        select(
            Container.reference_name,
            Container.topology_node_id,
            ContainerMetricSnapshot,
        )
        .join(Container, ContainerMetricSnapshot.container_id == Container.id)
        .where(ContainerMetricSnapshot.timestamp >= cutoff)
        .order_by(
            ContainerMetricSnapshot.container_id,
            ContainerMetricSnapshot.timestamp,
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    # Group by container
    groups: Dict[str, dict] = {}
    for ref_name, node_id, snap in rows:
        if ref_name not in groups:
            groups[ref_name] = {"node_id": node_id, "snapshots": []}
        groups[ref_name]["snapshots"].append(snap)

    all_events: List[DetectionEvent] = []

    for container_ref, info in groups.items():
        node_id = info["node_id"]
        snaps = info["snapshots"]

        for detector in (
            _detect_cpu_abuse,
            _detect_memory_staging,
            _detect_egress_burst,
            _detect_beaconing,
            _detect_filesystem_churn,
        ):
            evt = detector(container_ref, node_id, snaps, lookback_seconds, thresholds)
            if evt is not None:
                all_events.append(evt)

    # Group events by node for multi-signal correlation
    node_events: Dict[str, List[DetectionEvent]] = defaultdict(list)
    for evt in all_events:
        if evt.node_id:
            node_events[evt.node_id].append(evt)

    # Add multi-signal correlations
    for nid, events in list(node_events.items()):
        corr = _detect_multi_signal(nid, events)
        if corr is not None:
            all_events.append(corr)
            node_events[nid].append(corr)

    # Build per-node summaries
    summaries: List[NodeDetectionSummary] = []
    for nid, events in node_events.items():
        max_sev = "info"
        kinds = set()
        has_multi = False
        for e in events:
            max_sev = _max_severity(max_sev, e.severity)
            kinds.add(e.kind)
            if e.kind == "multi_signal_correlation":
                has_multi = True

        summaries.append(
            NodeDetectionSummary(
                node_id=nid,
                max_severity=max_sev,
                detection_count=len(events),
                detection_kinds=sorted(kinds),
                events=events,
                recommended_status=_severity_to_status(max_sev, has_multi),
            )
        )

    logger.info(
        "Detection complete: %d events, %d nodes affected",
        len(all_events),
        len(summaries),
    )
    return all_events, summaries


async def apply_detection_statuses(
    db: AsyncSession,
    summaries: List[NodeDetectionSummary],
) -> int:
    """Update topology node statuses from detection summaries.

    Only escalates status (healthy → warning).  Never demotes a node
    that is already in a more severe state.
    """
    updated = 0
    for s in summaries:
        if s.recommended_status == "healthy":
            continue
        result = await db.execute(
            select(TopologyNode).where(TopologyNode.id == s.node_id)
        )
        node = result.scalar_one_or_none()
        if node is None:
            continue
        current = _SEVERITY_ORDER.get(node.status, -1)
        proposed = _SEVERITY_ORDER.get(s.recommended_status, 0)
        if proposed > current:
            node.status = s.recommended_status
            updated += 1

    if updated:
        await db.commit()
    return updated
