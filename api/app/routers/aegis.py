from datetime import UTC, datetime, timedelta
import logging
from typing import List, Optional

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db_session
from app.models.topology import (
    TopologyNode as DBNode,
    TopologyEdge as DBEdge,
    Vulnerability as DBVuln,
    LLMInsight as DBInsight,
    RBACPolicy as DBRBAC,
    SecurityReport as DBReport,
)
from app.models.telemetry import Container, ContainerMetricSnapshot
from app.agents.topology import run_topology_analysis
from app.services.discovery import reconcile_topology_from_containers

logger = logging.getLogger(__name__)

router = APIRouter(tags=["aegis"])

# Throttle lazy topology reconciliation to at most once every 30 seconds
_last_reconcile_ts: float = 0.0


# ────────────────────────────────────────────────────────────
# Pydantic models (match frontend TypeScript types exactly)
# ────────────────────────────────────────────────────────────


class NodeTelemetry(BaseModel):
    ingressMbps: float
    egressMbps: float
    latencyMs: Optional[float] = None  # Not derivable from cAdvisor today
    errorRate: Optional[float] = None  # Not derivable from cAdvisor today
    lastSeen: Optional[str] = None


class NodeAnalysis(BaseModel):
    summary: str
    findings: List[str]
    recommendations: List[str]


class TopologyNode(BaseModel):
    id: str
    label: str
    serviceId: str
    status: str  # "healthy" | "warning" | "compromised"
    type: str  # "gateway" | "frontend" | "service" | "api" | "agent" | "database"
    position: dict
    description: Optional[str] = None
    telemetry: Optional[NodeTelemetry] = None
    analysis: Optional[NodeAnalysis] = None
    groupId: Optional[str] = None
    groupKind: Optional[str] = None  # "network" | "project" | "ungrouped"
    groupLabel: Optional[str] = None


class TopologyEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: str  # "network" | "api" | "inferred"
    label: str
    animated: Optional[bool] = False
    display: Optional[str] = "visible"  # "visible" | "hidden"


class TopologyGroup(BaseModel):
    id: str
    label: str
    kind: str  # "network" | "project" | "ungrouped"


class TopologyData(BaseModel):
    nodes: List[TopologyNode]
    edges: List[TopologyEdge]
    groups: List[TopologyGroup] = []
    lastUpdated: str
    scanStatus: str  # "idle" | "scanning" | "complete"


class Vulnerability(BaseModel):
    id: str
    title: str
    severity: str  # "critical" | "high" | "medium" | "low"
    affectedNode: str
    affectedNodeId: str
    description: str
    discoveredAt: str
    status: str  # "open" | "in-progress" | "resolved"
    cve: Optional[str] = None


class LLMInsight(BaseModel):
    id: str
    nodeId: str
    nodeName: str
    type: str  # "anomaly" | "threat" | "info"
    summary: str
    details: str
    timestamp: str
    confidence: float  # 0–1


class RBACPolicy(BaseModel):
    id: str
    role: str
    subject: str
    permissions: List[str]
    scope: str
    lastModified: str
    riskLevel: str  # "low" | "medium" | "high"


class SecurityScore(BaseModel):
    score: int
    breakdown: List[dict]


class SecurityReportResponse(BaseModel):
    id: str
    reportKind: str  # "deep_scan" | "security_posture"
    title: str
    summary: str
    detailsMarkdown: str
    createdAt: str
    maxStatus: str  # "healthy" | "warning" | "compromised"
    fingerprint: str
    trigger: str  # "manual" | "scheduled" | "api"
    payload: Optional[dict] = None


# ────────────────────────────────────────────────────────────
# Mock data (used ONLY for seeding)
# ────────────────────────────────────────────────────────────

_now = datetime.now(UTC)


def _iso(delta_hours: float = 0) -> str:
    return (_now - timedelta(hours=delta_hours)).isoformat()


def _iso_days(delta_days: int = 0) -> str:
    return (_now - timedelta(days=delta_days)).isoformat()


MOCK_NODES: List[TopologyNode] = [
    TopologyNode(
        id="ext-lb",
        label="External Gateway",
        serviceId="EXT-LB",
        status="healthy",
        type="gateway",
        position={"x": 60, "y": 300},
        description="Public-facing load balancer. Routes all external traffic to internal services via TLS termination.",
    ),
    TopologyNode(
        id="web-front",
        label="Web Frontend",
        serviceId="WEB-FRONT",
        status="healthy",
        type="frontend",
        position={"x": 320, "y": 120},
        description="React SPA served via CDN. Communicates with backend APIs and Auth Service.",
    ),
    TopologyNode(
        id="auth-svc",
        label="Auth Service",
        serviceId="AUTH-SVC",
        status="healthy",
        type="service",
        position={"x": 620, "y": 50},
        description="Handles authentication and session management. Issues short-lived JWTs.",
    ),
    TopologyNode(
        id="api-core",
        label="Core API Hub",
        serviceId="API-CORE",
        status="warning",
        type="api",
        position={"x": 400, "y": 320},
        description="Node.js backend hub. Routes requests to downstream services and the LLM agent via MCP bridge.",
    ),
    TopologyNode(
        id="llm-agent",
        label="Context Agent",
        serviceId="LLM-AGENT",
        status="compromised",
        type="agent",
        position={"x": 660, "y": 320},
        description="LLM-powered context agent with MCP tool access. Reads from Vector Store and returns augmented responses.",
    ),
    TopologyNode(
        id="db-main",
        label="Primary Database",
        serviceId="DB-MAIN",
        status="healthy",
        type="database",
        position={"x": 840, "y": 160},
        description="PostgreSQL primary. Stores user records, session data, and application state.",
    ),
    TopologyNode(
        id="db-vector",
        label="Vector Store",
        serviceId="DB-VECTOR",
        status="warning",
        type="database",
        position={"x": 950, "y": 420},
        description="Qdrant vector database. Holds document embeddings used by the Context Agent for RAG.",
    ),
]

MOCK_EDGES: List[TopologyEdge] = [
    TopologyEdge(
        id="e-ext-web",
        source="ext-lb",
        target="web-front",
        kind="network",
        label="NETWORK: public:443",
    ),
    TopologyEdge(
        id="e-web-auth",
        source="web-front",
        target="auth-svc",
        kind="api",
        label="API: service_account:auth_read",
    ),
    TopologyEdge(
        id="e-web-api",
        source="web-front",
        target="api-core",
        kind="api",
        label="API: frontend_role",
    ),
    TopologyEdge(
        id="e-ext-api",
        source="ext-lb",
        target="api-core",
        kind="api",
        label="API: public:443 → internal:8080",
    ),
    TopologyEdge(
        id="e-auth-db",
        source="auth-svc",
        target="db-main",
        kind="network",
        label="NETWORK: db_auth_admin",
    ),
    TopologyEdge(
        id="e-api-db",
        source="api-core",
        target="db-main",
        kind="network",
        label="NETWORK: db_api_rw",
    ),
    TopologyEdge(
        id="e-api-agent",
        source="api-core",
        target="llm-agent",
        kind="api",
        label="mcp_bridge_role",
        animated=True,
    ),
    TopologyEdge(
        id="e-agent-vector",
        source="llm-agent",
        target="db-vector",
        kind="api",
        label="vector_read_role",
        animated=True,
    ),
]

# ────────────────────────────────────────────────────────────
# Topology helpers: import, telemetry aggregation, status
# ────────────────────────────────────────────────────────────

# Staleness threshold – if the most recent snapshot for a node is older
# than this many seconds the node is considered "stale".
_STALE_SECONDS = 120
# Egress warning threshold in Mbps
_EGRESS_WARNING_MBPS = 50.0


class ComposeImportRequest(BaseModel):
    """Accepts raw Docker Compose YAML for topology import."""

    yaml_content: str
    project_name: Optional[str] = None


def _parse_compose_to_topology(
    compose_text: str,
    project_name: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Parse a Docker Compose YAML string into topology node/edge dicts.

    When *project_name* is provided, node IDs are scoped as
    ``<project_name>__<service>`` to match runtime-discovered IDs.

    Returns (nodes, edges) where each element is a dict suitable for
    constructing ``TopologyNode`` / ``TopologyEdge`` ORM objects.
    """
    doc = yaml.safe_load(compose_text)
    services = doc.get("services") or {}
    svc_names = list(services.keys())

    # Deterministic grid layout – 3 columns
    COL_WIDTH, ROW_HEIGHT = 260, 160
    COLS = 3

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_edges: set[str] = set()

    def _scope_id(svc_name: str) -> str:
        if project_name:
            return f"{project_name}__{svc_name}"
        return svc_name

    # Service-type heuristics
    def _guess_type(name: str, svc: dict) -> str:
        image = (svc.get("image") or "").lower()
        name_l = name.lower()
        if any(k in name_l for k in ("db", "postgres", "mysql", "redis", "mongo")):
            return "database"
        if any(k in image for k in ("postgres", "mysql", "redis", "mongo")):
            return "database"
        if any(k in name_l for k in ("web", "frontend", "ui", "nginx")):
            return "frontend"
        if any(k in name_l for k in ("gateway", "lb", "proxy", "traefik")):
            return "gateway"
        if any(k in name_l for k in ("agent", "llm", "ai")):
            return "agent"
        if any(k in name_l for k in ("api", "backend", "server")):
            return "api"
        return "service"

    for idx, svc_name in enumerate(svc_names):
        svc = services[svc_name]
        col = idx % COLS
        row = idx // COLS

        ports_desc = ""
        ports = svc.get("ports") or []
        if ports:
            ports_desc = f"  Ports: {', '.join(str(p) for p in ports)}"

        scoped = _scope_id(svc_name)
        source_label = f"project: {project_name}" if project_name else "Docker Compose"
        nodes.append(
            {
                "id": scoped,
                "label": svc_name,
                "service_id": svc_name,
                "status": "healthy",
                "type": _guess_type(svc_name, svc),
                "position": {"x": 60 + col * COL_WIDTH, "y": 60 + row * ROW_HEIGHT},
                "description": f"Imported from {source_label}.{ports_desc}",
            }
        )

        # Edges from depends_on — labeled as declared
        depends = svc.get("depends_on") or []
        if isinstance(depends, dict):
            depends = list(depends.keys())
        for dep in depends:
            edge_id = f"declared-{_scope_id(svc_name)}-{_scope_id(dep)}"
            if edge_id not in seen_edges and dep in services:
                edges.append(
                    {
                        "id": edge_id,
                        "source_id": _scope_id(svc_name),
                        "target_id": _scope_id(dep),
                        "kind": "declared",
                        "label": "declared: depends_on",
                        "animated": False,
                    }
                )
                seen_edges.add(edge_id)

    # Edges from shared networks — labeled with network name
    network_members: dict[str, list[str]] = {}
    for svc_name, svc in services.items():
        nets = svc.get("networks")
        if isinstance(nets, list):
            for n in nets:
                network_members.setdefault(n, []).append(_scope_id(svc_name))
        elif isinstance(nets, dict):
            for n in nets:
                network_members.setdefault(n, []).append(_scope_id(svc_name))

    for net_name, members in network_members.items():
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                edge_id = f"declared-net-{net_name}-{a}-{b}"
                if edge_id not in seen_edges:
                    edges.append(
                        {
                            "id": edge_id,
                            "source_id": a,
                            "target_id": b,
                            "kind": "declared",
                            "label": f"declared: shared network ({net_name})",
                            "animated": False,
                        }
                    )
                    seen_edges.add(edge_id)

    return nodes, edges


async def _aggregate_node_telemetry(
    node_id: str,
    db: AsyncSession,
    lookback_seconds: int = 300,
) -> Optional[NodeTelemetry]:
    """Aggregate recent network telemetry for containers mapped to *node_id*.

    Computes network throughput from **deltas** between the two most recent
    snapshots per container (not from cumulative counters directly).

    Returns ``None`` when no snapshots exist for the node in the lookback
    window (or no containers are mapped at all).
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=lookback_seconds)

    # Find containers mapped to this topology node
    containers_q = await db.execute(
        select(Container.id).where(Container.topology_node_id == node_id)
    )
    container_ids = [r[0] for r in containers_q.all()]
    if not container_ids:
        return None

    # All snapshots within the lookback window, ordered by container + time
    snapshots_q = await db.execute(
        select(ContainerMetricSnapshot)
        .where(
            ContainerMetricSnapshot.container_id.in_(container_ids),
            ContainerMetricSnapshot.timestamp >= cutoff,
        )
        .order_by(
            ContainerMetricSnapshot.container_id,
            ContainerMetricSnapshot.timestamp.desc(),
        )
    )
    snapshots = snapshots_q.scalars().all()
    if not snapshots:
        return None

    def _net_bytes(snap: ContainerMetricSnapshot) -> tuple[float, float]:
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

    # Group by container_id → find the two most recent snapshots for delta
    from collections import defaultdict

    per_container: dict[int, list] = defaultdict(list)
    for snap in snapshots:
        per_container[snap.container_id].append(snap)

    total_rx_rate = 0.0  # bytes/sec
    total_tx_rate = 0.0  # bytes/sec
    latest_ts: Optional[datetime] = None

    for cid, snaps in per_container.items():
        # snaps are ordered desc by timestamp
        if latest_ts is None or snaps[0].timestamp > latest_ts:
            latest_ts = snaps[0].timestamp

        if len(snaps) >= 2:
            newer = snaps[0]
            older = snaps[1]

            rx_new, tx_new = _net_bytes(newer)
            rx_old, tx_old = _net_bytes(older)

            elapsed = (newer.timestamp - older.timestamp).total_seconds()
            if elapsed > 0:
                total_rx_rate += max(0, rx_new - rx_old) / elapsed
                total_tx_rate += max(0, tx_new - tx_old) / elapsed
        # If only one snapshot, we can't compute a rate — skip

    # Convert bytes/sec → Mbps
    ingress = round((total_rx_rate * 8) / 1_000_000, 3)
    egress = round((total_tx_rate * 8) / 1_000_000, 3)

    return NodeTelemetry(
        ingressMbps=ingress,
        egressMbps=egress,
        latencyMs=None,  # Not derivable from cAdvisor
        errorRate=None,  # Not derivable from cAdvisor
        lastSeen=latest_ts.isoformat() if latest_ts else None,
    )


def _compute_node_status(
    current_status: str,
    telemetry: Optional[NodeTelemetry],
    detection_severity: Optional[str] = None,
    last_snapshot_ts: Optional[datetime] = None,
) -> str:
    """Deterministic status engine.

    Rules (applied in priority order):
    1. If detection lane produced a warning or critical finding → at
       least ``warning``.
    2. If no telemetry data exists at all → keep current DB status (may be
       freshly imported and no containers matched yet).
    3. If the most recent snapshot is older than ``_STALE_SECONDS`` → ``warning``
       (stale data).
    4. If egress > ``_EGRESS_WARNING_MBPS`` → ``warning``.
    5. Otherwise → ``healthy``.

    This engine never promotes a node to *compromised* – that requires
    stronger evidence (e.g. LLM-driven analysis or manual action).
    """
    # Fast-lane detection escalation
    if detection_severity in ("warning", "critical"):
        return "warning"

    if telemetry is None:
        return current_status  # no mapped containers or no data yet

    # Staleness check
    if telemetry.lastSeen:
        try:
            ls = telemetry.lastSeen
            if ls.endswith("Z"):
                ls = ls[:-1] + "+00:00"
            last_seen_dt = datetime.fromisoformat(ls)
            age = (datetime.now(UTC) - last_seen_dt).total_seconds()
            if age > _STALE_SECONDS:
                return "warning"
        except Exception:
            pass

    # Egress threshold
    if telemetry.egressMbps > _EGRESS_WARNING_MBPS:
        return "warning"

    return "healthy"


async def _compute_effective_node_statuses(
    db: AsyncSession,
) -> List[tuple]:
    """Return (node, effective_status, telemetry) for every topology node.

    This is the **single source of truth** for effective node status used
    by both ``GET /topology`` and ``GET /security-score``.

    Incorporates detection-lane summaries so nodes react immediately
    when suspicious behaviour is detected, without waiting for LLM.
    """
    from app.services.detection import run_detectors

    nodes_q = await db.execute(select(DBNode))
    nodes = nodes_q.scalars().all()

    # Run fast-lane detectors to get per-node severity
    detection_map: dict[str, str] = {}
    try:
        _events, summaries = await run_detectors(db)
        for s in summaries:
            detection_map[s.node_id] = s.max_severity
    except Exception as exc:
        logger.warning("Detection lane failed during status computation: %s", exc)

    results = []
    for n in nodes:
        telem = await _aggregate_node_telemetry(n.id, db)
        det_severity = detection_map.get(n.id)
        effective = _compute_node_status(n.status, telem, detection_severity=det_severity)
        results.append((n, effective, telem))
    return results


async def _compute_security_score(db: AsyncSession) -> SecurityScore:
    score = 100
    breakdown = []

    # Use effective (telemetry-aware) statuses — same logic as /topology
    node_statuses = await _compute_effective_node_statuses(db)
    compromised = sum(1 for _, s, _ in node_statuses if s == "compromised")
    warning = sum(1 for _, s, _ in node_statuses if s == "warning")
    if compromised:
        impact = -20 * compromised
        breakdown.append(
            {
                "label": f"{compromised} compromised node{'s' if compromised > 1 else ''}",
                "impact": impact,
            }
        )
        score += impact
    if warning:
        impact = -10 * warning
        breakdown.append(
            {
                "label": f"{warning} warning node{'s' if warning > 1 else ''}",
                "impact": impact,
            }
        )
        score += impact

    vulns_q = await db.execute(select(DBVuln))
    vulns = vulns_q.scalars().all()
    crit_vulns = sum(
        1 for v in vulns if v.severity == "critical" and v.status == "open"
    )
    high_vulns = sum(1 for v in vulns if v.severity == "high" and v.status == "open")
    if crit_vulns:
        impact = -8 * crit_vulns
        breakdown.append(
            {
                "label": f"{crit_vulns} critical vuln{'s' if crit_vulns > 1 else ''}",
                "impact": impact,
            }
        )
        score += impact
    if high_vulns:
        impact = -5 * high_vulns
        breakdown.append(
            {
                "label": f"{high_vulns} high vuln{'s' if high_vulns > 1 else ''}",
                "impact": impact,
            }
        )
        score += impact

    rbac_q = await db.execute(select(DBRBAC))
    rbacs = rbac_q.scalars().all()
    high_risk = sum(1 for p in rbacs if p.riskLevel == "high")
    if high_risk:
        impact = -3 * high_risk
        breakdown.append({"label": f"{high_risk} high-risk RBAC", "impact": impact})
        score += impact

    return SecurityScore(score=max(0, score), breakdown=breakdown)


# ────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────


@router.post("/topology/seed")
async def seed_topology(db: AsyncSession = Depends(get_db_session)) -> dict:
    """Creates the tables and seeds them with initial data if empty."""
    from app.core.database import Base

    # Create the tables if they don't exist
    conn = await db.connection()
    await conn.run_sync(Base.metadata.create_all)

    # Check if empty
    res = await db.execute(select(DBNode).limit(1))
    if res.scalar_one_or_none():
        return {"status": "already_seeded"}

    for n in MOCK_NODES:
        db.add(
            DBNode(
                id=n.id,
                label=n.label,
                service_id=n.serviceId,
                status=n.status,
                type=n.type,
                position=n.position,
                description=n.description,
            )
        )
    for e in MOCK_EDGES:
        db.add(
            DBEdge(
                id=e.id,
                source_id=e.source,
                target_id=e.target,
                kind=e.kind,
                label=e.label,
                animated=e.animated,
            )
        )
    await db.commit()
    return {"status": "seeded"}


@router.post("/topology/import")
async def import_topology(
    body: ComposeImportRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Import topology from a Docker Compose YAML document.

    This endpoint **merges** (upserts) imported topology with any
    existing runtime-discovered nodes.  It enriches the graph with
    declared edges (``depends_on``, shared networks) and descriptions
    from the Compose file without destroying live data.

    Pass ``project_name`` to scope node IDs so they align with
    runtime-discovered containers from the same Compose project.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    node_dicts, edge_dicts = _parse_compose_to_topology(
        body.yaml_content, body.project_name
    )

    # Upsert nodes — merge with existing runtime-discovered nodes
    for nd in node_dicts:
        stmt = (
            pg_insert(DBNode)
            .values(**nd)
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "description": nd.get("description"),
                    "type": nd.get("type"),
                    # Preserve existing status and position from runtime
                },
            )
        )
        await db.execute(stmt)

    # Upsert edges — add declared edges without removing inferred ones
    for ed in edge_dicts:
        stmt = (
            pg_insert(DBEdge)
            .values(**ed)
            .on_conflict_do_nothing(
                index_elements=["id"],
            )
        )
        await db.execute(stmt)

    await db.commit()

    return {
        "status": "imported",
        "nodes": len(node_dicts),
        "edges": len(edge_dicts),
    }


def _build_group_membership(
    containers: list,
) -> tuple[dict[str, tuple[str, str, str]], list[TopologyGroup]]:
    """Derive group membership for topology nodes from container metadata.

    Returns ``(node_id → (groupId, groupKind, groupLabel), groups_list)``.

    Grouping priority:
    1. Shared Docker network (from compose labels)
    2. Compose project
    3. Ungrouped / misc
    """
    from collections import defaultdict

    # network → set of node_ids
    net_members: dict[str, set[str]] = defaultdict(set)
    # node_id → project
    node_project: dict[str, str] = {}

    for c in containers:
        node_id = c.topology_node_id
        if not node_id:
            continue
        labels = c.labels if isinstance(c.labels, dict) else {}
        project = labels.get("com.docker.compose.project")
        if project:
            node_project[node_id] = project
            net_members[f"{project}_default"].add(node_id)
        networks_csv = labels.get("com.docker.compose.networks")
        if networks_csv:
            for net in networks_csv.split(","):
                net = net.strip()
                if net:
                    net_members[net].add(node_id)

    # Assign each node to its best group.
    # Priority: largest shared network first, then project, then ungrouped.
    node_group: dict[str, tuple[str, str, str]] = {}
    groups_map: dict[str, TopologyGroup] = {}

    # Sort networks by member count descending so nodes join their biggest network
    for net_name in sorted(net_members, key=lambda n: len(net_members[n]), reverse=True):
        members = net_members[net_name]
        if len(members) < 2:
            continue
        gid = f"net:{net_name}"
        if gid not in groups_map:
            groups_map[gid] = TopologyGroup(id=gid, label=net_name, kind="network")
        for nid in members:
            if nid not in node_group:
                node_group[nid] = (gid, "network", net_name)

    # Fall back to project grouping for remaining nodes
    for nid, project in node_project.items():
        if nid not in node_group:
            gid = f"proj:{project}"
            if gid not in groups_map:
                groups_map[gid] = TopologyGroup(id=gid, label=project, kind="project")
            node_group[nid] = (gid, "project", project)

    return node_group, list(groups_map.values())


def _derive_groups_from_node_ids(
    node_ids: list[str],
) -> tuple[dict[str, tuple[str, str, str]], list[TopologyGroup]]:
    """Fallback grouping based only on the project prefix in node IDs.

    Used when no container metadata is available (e.g. imported topologies
    or mock/seed data).
    """
    node_group: dict[str, tuple[str, str, str]] = {}
    groups_map: dict[str, TopologyGroup] = {}

    for nid in node_ids:
        if "__" in nid:
            project, _ = nid.split("__", 1)
        else:
            project = "ungrouped"
        gid = f"proj:{project}"
        if gid not in groups_map:
            groups_map[gid] = TopologyGroup(id=gid, label=project, kind="project")
        node_group[nid] = (gid, "project", project)

    return node_group, list(groups_map.values())


def _classify_edge_display(edge_kind: str, edge_label: str, source_group: str | None, target_group: str | None) -> str:
    """Determine whether an edge should be visible or hidden in the default view.

    Rules:
    - Declared dependency / API edges → always visible
    - Inferred edges within the same group → hidden (reduces clutter)
    - Cross-group inferred edges → visible
    """
    if edge_kind != "inferred":
        return "visible"
    # Cross-group inferred edges remain visible
    if source_group and target_group and source_group != target_group:
        return "visible"
    return "hidden"


@router.get("/topology", response_model=TopologyData)
async def get_topology(db: AsyncSession = Depends(get_db_session)) -> TopologyData:
    import time as _time

    global _last_reconcile_ts

    # Lazy reconciliation: if topology is empty, attempt to rebuild from
    # live container metadata (throttled to at most once every 30 s).
    now = _time.monotonic()
    if now - _last_reconcile_ts > 30:
        check = await db.execute(select(DBNode.id).limit(1))
        if check.scalar_one_or_none() is None:
            await reconcile_topology_from_containers(db)
        _last_reconcile_ts = now

    # Use the shared helper for node statuses — also covers the "any nodes?" check
    node_statuses = await _compute_effective_node_statuses(db)
    edges_q = await db.execute(select(DBEdge))

    # Build group membership from container metadata
    containers_q = await db.execute(select(Container))
    containers = containers_q.scalars().all()

    all_node_ids = [n.id for n, _, _ in node_statuses]
    if containers:
        node_group, groups = _build_group_membership(containers)
    else:
        node_group, groups = {}, []

    # For nodes not covered by container metadata, fall back to ID-based grouping
    ungrouped_ids = [nid for nid in all_node_ids if nid not in node_group]
    if ungrouped_ids:
        fallback_groups, fallback_list = _derive_groups_from_node_ids(ungrouped_ids)
        node_group.update(fallback_groups)
        existing_gids = {g.id for g in groups}
        for g in fallback_list:
            if g.id not in existing_gids:
                groups.append(g)

    nodes = []
    for n, status, telem in node_statuses:
        grp = node_group.get(n.id)
        nodes.append(
            TopologyNode(
                id=n.id,
                label=n.label,
                serviceId=n.service_id,
                status=status,
                type=n.type,
                position=n.position,
                description=n.description,
                telemetry=telem,
                analysis=n.analysis if isinstance(n.analysis, dict) else None,
                groupId=grp[0] if grp else None,
                groupKind=grp[1] if grp else None,
                groupLabel=grp[2] if grp else None,
            )
        )

    edges = []
    for e in edges_q.scalars().all():
        src_entry = node_group.get(e.source_id)
        tgt_entry = node_group.get(e.target_id)
        src_grp = src_entry[0] if src_entry else None
        tgt_grp = tgt_entry[0] if tgt_entry else None
        edges.append(
            TopologyEdge(
                id=e.id,
                source=e.source_id,
                target=e.target_id,
                kind=e.kind,
                label=e.label,
                animated=e.animated,
                display=_classify_edge_display(e.kind, e.label, src_grp, tgt_grp),
            )
        )

    return TopologyData(
        nodes=nodes,
        edges=edges,
        groups=groups,
        lastUpdated=datetime.now(UTC).isoformat(),
        scanStatus="idle",
    )


@router.post("/topology/scan", response_model=TopologyData)
async def run_scan(db: AsyncSession = Depends(get_db_session)) -> dict:
    # Trigger the background LangGraph DAG topology agent.
    # Failures here must not prevent returning the topology graph.
    try:
        _ = await run_topology_analysis(db)
    except Exception as exc:
        logger.error("Topology analysis failed during scan: %s", exc)
        # Ensure the session is clean for the subsequent topology fetch
        try:
            await db.rollback()
        except Exception:
            pass

    # Return topology with scanning status true (frontend usually polls afterward)
    topo = await get_topology(db)
    topo.scanStatus = "complete"
    return topo


@router.post("/topology/{node_id}/isolate")
async def isolate_node(
    node_id: str, db: AsyncSession = Depends(get_db_session)
) -> dict:
    """Soft-isolate a node (simulated).

    Persists an "isolated" status on the node so the state is visible
    in the topology graph.  This is a **simulated** action — no real
    network isolation is performed.  A production implementation would
    integrate with the container runtime or firewall.
    """
    result = await db.execute(select(DBNode).where(DBNode.id == node_id))
    node = result.scalar_one_or_none()
    if node is None:
        return {
            "success": False,
            "nodeId": node_id,
            "action": "isolate",
            "simulated": True,
            "detail": "Node not found",
        }
    node.status = "isolated"
    await db.commit()
    return {
        "success": True,
        "nodeId": node_id,
        "action": "isolate",
        "simulated": True,
        "detail": "Node status set to isolated (simulated — no real network isolation)",
    }


@router.get("/vulnerabilities", response_model=List[Vulnerability])
async def get_vulnerabilities(
    db: AsyncSession = Depends(get_db_session),
) -> List[Vulnerability]:
    q = await db.execute(select(DBVuln))
    return [
        Vulnerability(
            id=v.id,
            title=v.title,
            severity=v.severity,
            affectedNode=v.affected_node_id,
            affectedNodeId=v.affected_node_id,
            description=v.description,
            discoveredAt=v.discovered_at.isoformat(),
            status=v.status,
            cve=v.cve,
        )
        for v in q.scalars().all()
    ]


@router.get("/insights", response_model=List[LLMInsight])
async def get_insights(db: AsyncSession = Depends(get_db_session)) -> List[LLMInsight]:
    q = await db.execute(select(DBInsight))
    return [
        LLMInsight(
            id=i.id,
            nodeId=i.node_id,
            nodeName=i.node_id,
            type=i.type,
            summary=i.summary,
            details=i.details,
            timestamp=i.timestamp.isoformat(),
            confidence=i.confidence,
        )
        for i in q.scalars().all()
    ]


@router.get("/rbac", response_model=List[RBACPolicy])
async def get_rbac(db: AsyncSession = Depends(get_db_session)) -> List[RBACPolicy]:
    q = await db.execute(select(DBRBAC))
    return [
        RBACPolicy(
            id=r.id,
            role=r.role,
            subject=r.subject,
            permissions=r.permissions,
            scope=r.scope,
            lastModified=r.last_modified.isoformat(),
            riskLevel=r.risk_level,
        )
        for r in q.scalars().all()
    ]


@router.post("/rbac/{node_id}/revoke")
async def revoke_rbac(node_id: str, db: AsyncSession = Depends(get_db_session)) -> dict:
    """Revoke RBAC policies for a node (simulated).

    Sets the node status to "compromised" to reflect the revocation in
    the topology graph.  This is a **simulated** action — no real
    credential revocation is performed.
    """
    result = await db.execute(select(DBNode).where(DBNode.id == node_id))
    node = result.scalar_one_or_none()
    if node is None:
        return {
            "success": False,
            "nodeId": node_id,
            "action": "rbac_revoke",
            "simulated": True,
            "detail": "Node not found",
        }
    node.status = "compromised"
    await db.commit()
    return {
        "success": True,
        "nodeId": node_id,
        "action": "rbac_revoke",
        "simulated": True,
        "detail": "Node status set to compromised, RBAC revoked (simulated)",
    }


@router.get("/security-score", response_model=SecurityScore)
async def get_security_score(
    db: AsyncSession = Depends(get_db_session),
) -> SecurityScore:
    return await _compute_security_score(db)


@router.get("/reports", response_model=List[SecurityReportResponse])
async def get_reports(
    db: AsyncSession = Depends(get_db_session),
) -> List[SecurityReportResponse]:
    q = await db.execute(
        select(DBReport).order_by(DBReport.created_at.desc())
    )
    return [
        SecurityReportResponse(
            id=r.id,
            reportKind=r.report_kind,
            title=r.title,
            summary=r.summary,
            detailsMarkdown=r.details_markdown,
            createdAt=r.created_at.isoformat(),
            maxStatus=r.max_status,
            fingerprint=r.fingerprint,
            trigger=r.trigger,
            payload=r.payload,
        )
        for r in q.scalars().all()
    ]


@router.get("/detections")
async def get_detections(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Run deterministic detectors and return current detection events + summaries."""
    from app.services.detection import run_detectors

    events, summaries = await run_detectors(db)
    return {
        "events": [e.model_dump() for e in events],
        "summaries": [s.model_dump() for s in summaries],
    }
