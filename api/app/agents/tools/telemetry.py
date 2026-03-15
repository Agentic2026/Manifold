from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import Container, ContainerMetricSnapshot


# ── JSON helpers ────────────────────────────────────────────


def _extract_cpu_total(cpu_stats: dict) -> int | None:
    """Extract cumulative CPU usage nanoseconds from stored cpu_stats.

    Supported shapes:
      - {"usage": {"total": <int>, ...}}  (cAdvisor nested)
      - {"usage": <int>}                  (flat fallback)
    """
    if not isinstance(cpu_stats, dict):
        return None
    usage = cpu_stats.get("usage")
    if isinstance(usage, dict):
        val = usage.get("total")
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                return None
    if isinstance(usage, (int, float)):
        try:
            return int(usage)
        except (TypeError, ValueError):
            return None
    return None


def _extract_memory_bytes(memory_stats: dict) -> int | None:
    """Extract working-set (preferred) or usage memory bytes.

    Supported shapes:
      - {"working_set": <int>, "usage": <int>}
      - {"usage": <int>}
    """
    if not isinstance(memory_stats, dict):
        return None
    for key in ("working_set", "usage"):
        val = memory_stats.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return None


# ── Structured spike result ─────────────────────────────────

from dataclasses import dataclass, asdict


@dataclass
class SpikeCandidate:
    """Lightweight container for a single container's spike data."""

    container_ref: str
    topology_node_id: str | None
    image: str | None
    aliases: list | None
    cpu_delta_ns: int
    elapsed_seconds: float
    cpu_avg_cores: float
    latest_memory_bytes: int
    memory_delta_bytes: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary_line(self) -> str:
        node = self.topology_node_id or "(unmapped)"
        mem_mb = (
            round(self.latest_memory_bytes / (1024 * 1024), 1)
            if self.latest_memory_bytes
            else 0
        )
        mem_delta_mb = (
            round(self.memory_delta_bytes / (1024 * 1024), 1)
            if self.memory_delta_bytes
            else 0
        )
        cpu_cores = round(self.cpu_avg_cores, 3) if self.cpu_avg_cores else 0
        return (
            f"Node {node} (container {self.container_ref}): "
            f"cpu_avg_cores={cpu_cores}, "
            f"mem_working_set_mb={mem_mb}, "
            f"mem_delta_mb={mem_delta_mb}"
        )


# ── Core implementation ─────────────────────────────────────


async def get_resource_spikes_impl(
    lookback_seconds: int,
    db: AsyncSession,
) -> str:
    """Check for resource spikes across all supervised containers.

    Uses Python-side extraction of nested JSONB fields to avoid
    PostgreSQL cast errors on ``cpu_stats->'usage'`` (which is an
    object, not a numeric scalar).

    Returns a compact structured summary string suitable for LLM
    consumption.
    """
    return _format_spike_results(
        await get_resource_spikes_structured(lookback_seconds, db),
        lookback_seconds,
    )


async def get_resource_spikes_structured(
    lookback_seconds: int,
    db: AsyncSession,
) -> List[SpikeCandidate]:
    """Return structured spike candidates (used internally and by topology agent)."""
    from datetime import datetime, timezone, timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=lookback_seconds)

    # Fetch all snapshots in the lookback window joined to container metadata
    stmt = (
        select(
            Container.reference_name,
            Container.topology_node_id,
            Container.image,
            Container.aliases,
            ContainerMetricSnapshot.cpu_stats,
            ContainerMetricSnapshot.memory_stats,
            ContainerMetricSnapshot.timestamp,
            ContainerMetricSnapshot.container_id,
        )
        .join(Container, ContainerMetricSnapshot.container_id == Container.id)
        .where(ContainerMetricSnapshot.timestamp >= cutoff)
        .order_by(
            ContainerMetricSnapshot.container_id, ContainerMetricSnapshot.timestamp
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return []

    # Group by container_id → pick first and last snapshot
    from collections import defaultdict

    groups: Dict[int, list] = defaultdict(list)
    for row in rows:
        groups[row.container_id].append(row)

    candidates: List[SpikeCandidate] = []
    for cid, snapshots in groups.items():
        first = snapshots[0]
        last = snapshots[-1]

        # Elapsed time
        ts_first = first.timestamp
        ts_last = last.timestamp
        if ts_first and ts_last:
            elapsed = (ts_last - ts_first).total_seconds()
        else:
            elapsed = 0

        # CPU delta
        cpu_first = _extract_cpu_total(first.cpu_stats or {})
        cpu_last = _extract_cpu_total(last.cpu_stats or {})
        if cpu_first is not None and cpu_last is not None:
            cpu_delta_ns = cpu_last - cpu_first
        else:
            cpu_delta_ns = 0

        cpu_avg_cores = (cpu_delta_ns / (elapsed * 1e9)) if elapsed > 0 else 0.0

        # Memory
        mem_first = _extract_memory_bytes(first.memory_stats or {})
        mem_last = _extract_memory_bytes(last.memory_stats or {})
        latest_memory_bytes = mem_last or 0
        memory_delta_bytes = (
            (mem_last - mem_first)
            if (mem_last is not None and mem_first is not None)
            else 0
        )

        candidates.append(
            SpikeCandidate(
                container_ref=first.reference_name,
                topology_node_id=first.topology_node_id,
                image=first.image,
                aliases=first.aliases,
                cpu_delta_ns=cpu_delta_ns,
                elapsed_seconds=elapsed,
                cpu_avg_cores=cpu_avg_cores,
                latest_memory_bytes=latest_memory_bytes,
                memory_delta_bytes=memory_delta_bytes,
            )
        )

    # Filter to containers that show meaningful activity.
    # Heuristic thresholds — tuned for typical containerized services:
    # - >0.01 CPU cores average sustained utilization
    # - >10 MB memory delta within the lookback window
    MEM_DELTA_THRESHOLD = 10 * 1024 * 1024  # 10 MB
    CPU_CORES_THRESHOLD = 0.01

    candidates = [
        c
        for c in candidates
        if c.cpu_avg_cores > CPU_CORES_THRESHOLD
        or abs(c.memory_delta_bytes) > MEM_DELTA_THRESHOLD
    ]

    candidates.sort(
        key=lambda c: (c.cpu_avg_cores, abs(c.memory_delta_bytes)), reverse=True
    )
    return candidates[:15]


def _format_spike_results(
    candidates: List[SpikeCandidate], lookback_seconds: int
) -> str:
    if not candidates:
        return f"No significant resource spikes detected in the last {lookback_seconds} seconds."

    lines = [f"Resource spike candidates in the last {lookback_seconds}s:"]
    for c in candidates:
        lines.append(f" - {c.summary_line()}")
    return "\n".join(lines)


@tool
async def get_resource_spikes(lookback_seconds: int) -> str:
    """Checks for recent resource spikes (CPU or Memory) across all supervised containers."""
    # Placeholder for agent tool schema. Actual execution injects DB session.
    pass
