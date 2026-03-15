"""Runtime topology discovery from live container metadata.

This module auto-creates TopologyNode and TopologyEdge rows from
containers already persisted by the ingestion service.  It is the
primary mechanism for building the DAG – no manual Compose import
is required.
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


# ── Layout ──────────────────────────────────────────────────

_COL_WIDTH = 260
_ROW_HEIGHT = 160
_COLS = 3


def _grid_position(index: int) -> dict[str, int]:
    return {
        "x": 60 + (index % _COLS) * _COL_WIDTH,
        "y": 60 + (index // _COLS) * _ROW_HEIGHT,
    }


# ── Core discovery ──────────────────────────────────────────

async def reconcile_topology_from_containers(db: AsyncSession) -> int:
    """Upsert topology nodes and inferred edges from current containers.

    Groups containers by ``com.docker.compose.service`` (primary) or
    ``topology_node_id`` (fallback).  Each unique service becomes a
    TopologyNode.  Services within the same Compose project get
    lightweight inferred edges.

    Returns the number of nodes upserted.
    """
    result = await db.execute(select(Container))
    containers = result.scalars().all()

    if not containers:
        return 0

    # Group containers → services
    # key: (project, service_name)
    service_map: dict[tuple[str, str], list[Container]] = defaultdict(list)
    for c in containers:
        node_id = c.topology_node_id
        if not node_id:
            continue
        labels = c.labels if isinstance(c.labels, dict) else {}
        project = labels.get("com.docker.compose.project", "__default__")
        service_map[(project, node_id)].append(c)

    if not service_map:
        return 0

    # Upsert nodes
    idx = 0
    node_ids: list[str] = []
    project_services: dict[str, list[str]] = defaultdict(list)

    for (project, svc_name), ctrs in service_map.items():
        # Derive representative image from first container
        rep_image = ctrs[0].image if ctrs else None
        svc_type = _guess_service_type(svc_name, rep_image)
        position = _grid_position(idx)

        stmt = pg_insert(DBNode).values(
            id=svc_name,
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

        node_ids.append(svc_name)
        project_services[project].append(svc_name)
        idx += 1

    # Inferred edges: services in the same project
    edge_count = 0
    for project, members in project_services.items():
        if len(members) < 2:
            continue
        # Sort for deterministic edge generation
        members_sorted = sorted(members)
        for i, src in enumerate(members_sorted):
            for tgt in members_sorted[i + 1:]:
                edge_id = f"inferred-{project}-{src}-{tgt}"
                stmt = pg_insert(DBEdge).values(
                    id=edge_id,
                    source_id=src,
                    target_id=tgt,
                    kind="inferred",
                    label=f"same project ({project})",
                    animated=False,
                ).on_conflict_do_nothing(index_elements=["id"])
                await db.execute(stmt)
                edge_count += 1

    await db.commit()
    return len(node_ids)
