"""Runtime topology discovery from live container metadata.

This module auto-creates TopologyNode and TopologyEdge rows from
containers already persisted by the ingestion service.  It is the
primary mechanism for building the DAG – no manual Compose import
is required.

Node IDs are project-scoped (``<project>__<service>``) to prevent
collisions across different Compose projects.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.telemetry import Container
from app.models.topology import TopologyNode as DBNode, TopologyEdge as DBEdge


# ── Heuristics ──────────────────────────────────────────────

_TYPE_KEYWORDS: list[tuple[list[str], str]] = [
    (["postgres", "mysql", "redis", "mongo", "db", "mariadb"], "database"),
    (["web", "frontend", "ui", "nginx"], "frontend"),
    (["gateway", "lb", "proxy", "traefik", "cadvisor"], "gateway"),
    (["agent", "llm", "ai", "worker"], "agent"),
    (["api", "backend", "server"], "api"),
]


def _guess_service_type(name: str, image: str | None) -> str:
    """Infer service type from name and image with simple keyword matching."""
    name_l = name.lower()
    image_l = (image or "").lower()
    for keywords, svc_type in _TYPE_KEYWORDS:
        if any(k in name_l for k in keywords):
            return svc_type
        if any(k in image_l for k in keywords):
            return svc_type
    return "service"


def _parse_scoped_id(scoped_id: str) -> tuple[str, str]:
    """Split a scoped node ID into (project, service_name).

    Returns ("__default__", scoped_id) when no project separator is present.
    """
    if "__" in scoped_id:
        project, svc_name = scoped_id.split("__", 1)
        return project, svc_name
    return "__default__", scoped_id


# ── Layout ──────────────────────────────────────────────────

_COL_WIDTH = 260
_ROW_HEIGHT = 160
_COLS = 3


def _grid_position(index: int) -> dict[str, int]:
    return {
        "x": 60 + (index % _COLS) * _COL_WIDTH,
        "y": 60 + (index // _COLS) * _ROW_HEIGHT,
    }


# ── Shared-network extraction ──────────────────────────────

def _extract_shared_networks(containers: list[Container]) -> dict[str, list[str]]:
    """Build a mapping of network name → list of topology_node_ids.

    Inspects Docker network labels on each container to find shared
    connectivity.  Only containers with a topology_node_id are included.
    """
    net_members: dict[str, set[str]] = defaultdict(set)
    for c in containers:
        node_id = c.topology_node_id
        if not node_id:
            continue
        labels = c.labels if isinstance(c.labels, dict) else {}
        # Docker Compose containers get a network named <project>_<network>
        # Look for com.docker.compose.project to derive default network
        project = labels.get("com.docker.compose.project")
        if project:
            net_members[f"{project}_default"].add(node_id)
        # Check for explicit network labels (if present)
        networks_csv = labels.get("com.docker.compose.networks")
        if networks_csv:
            for net in networks_csv.split(","):
                net = net.strip()
                if net:
                    net_members[net].add(node_id)
    return {k: sorted(v) for k, v in net_members.items()}


# ── Core discovery ──────────────────────────────────────────

async def reconcile_topology_from_containers(db: AsyncSession) -> int:
    """Upsert topology nodes and inferred edges from current containers.

    Groups containers by ``topology_node_id`` (now project-scoped).
    Each unique scoped ID becomes a TopologyNode.  Services within the
    same Compose project get inferred edges labeled with evidence
    (shared network, same project).

    Returns the number of nodes upserted.
    """
    result = await db.execute(select(Container))
    containers = result.scalars().all()

    if not containers:
        return 0

    # Group containers → services (by scoped topology_node_id)
    service_map: dict[str, list[Container]] = defaultdict(list)
    for c in containers:
        node_id = c.topology_node_id
        if not node_id:
            continue
        service_map[node_id].append(c)

    if not service_map:
        return 0

    # Build shared-network info for richer edges
    network_map = _extract_shared_networks(containers)

    # Upsert nodes
    idx = 0
    node_ids: list[str] = []
    project_services: dict[str, list[str]] = defaultdict(list)

    for scoped_id, ctrs in service_map.items():
        project, svc_name = _parse_scoped_id(scoped_id)

        # Derive representative image from first container
        rep_image = ctrs[0].image if ctrs else None
        svc_type = _guess_service_type(svc_name, rep_image)
        position = _grid_position(idx)

        stmt = pg_insert(DBNode).values(
            id=scoped_id,
            label=svc_name,
            service_id=svc_name,
            status="healthy",
            type=svc_type,
            position=position,
            description=f"Auto-discovered from runtime metadata (project: {project}).",
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "label": svc_name,
                "service_id": svc_name,
                "type": svc_type,
                # Preserve existing position to avoid layout jumps
                # Preserve existing status (will be recomputed on GET)
            },
        )
        await db.execute(stmt)

        node_ids.append(scoped_id)
        project_services[project].append(scoped_id)
        idx += 1

    # ── Inferred edges ──────────────────────────────────────
    # Build a set of known shared-network pairs for stronger evidence
    network_pairs: dict[tuple[str, str], list[str]] = defaultdict(list)
    for net_name, members in network_map.items():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                pair = (min(a, b), max(a, b))
                network_pairs[pair].append(net_name)

    for project, members in project_services.items():
        if len(members) < 2:
            continue
        # Sort for deterministic edge generation
        members_sorted = sorted(members)
        for i, src in enumerate(members_sorted):
            for tgt in members_sorted[i + 1:]:
                pair = (min(src, tgt), max(src, tgt))
                shared_nets = network_pairs.get(pair, [])

                if shared_nets:
                    edge_label = f"inferred: shared network ({', '.join(shared_nets)})"
                else:
                    edge_label = f"inferred: same project ({project})"

                edge_id = f"inferred-{project}-{src}-{tgt}"
                stmt = pg_insert(DBEdge).values(
                    id=edge_id,
                    source_id=src,
                    target_id=tgt,
                    kind="inferred",
                    label=edge_label,
                    animated=False,
                ).on_conflict_do_nothing(index_elements=["id"])
                await db.execute(stmt)

    await db.commit()
    return len(node_ids)
