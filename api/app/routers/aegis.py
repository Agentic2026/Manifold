from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete, func

from app.core.database import get_db_session
from app.models.topology import TopologyNode as DBNode, TopologyEdge as DBEdge, Vulnerability as DBVuln, LLMInsight as DBInsight, RBACPolicy as DBRBAC
from app.models.telemetry import Container, ContainerMetricSnapshot
from app.agents.topology import run_topology_analysis

router = APIRouter(prefix="/api", tags=["aegis"])


# ────────────────────────────────────────────────────────────
# Pydantic models (match frontend TypeScript types exactly)
# ────────────────────────────────────────────────────────────


class NodeTelemetry(BaseModel):
    ingressMbps: float
    egressMbps: float
    latencyMs: Optional[float] = None   # Not derivable from cAdvisor today
    errorRate: Optional[float] = None    # Not derivable from cAdvisor today
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


class TopologyEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: str  # "network" | "api"
    label: str
    animated: Optional[bool] = False


class TopologyData(BaseModel):
    nodes: List[TopologyNode]
    edges: List[TopologyEdge]
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
        telemetry=NodeTelemetry(ingressMbps=45.2, egressMbps=38.7, latencyMs=12, errorRate=0.01),
        analysis=NodeAnalysis(
            summary="Operating within normal parameters. No anomalous traffic patterns detected in the last 24 hours.",
            findings=[],
            recommendations=["Consider enabling WAF rules for SQL-injection signatures."],
        ),
    ),
    TopologyNode(
        id="web-front",
        label="Web Frontend",
        serviceId="WEB-FRONT",
        status="healthy",
        type="frontend",
        position={"x": 320, "y": 120},
        description="React SPA served via CDN. Communicates with backend APIs and Auth Service.",
        telemetry=NodeTelemetry(ingressMbps=12.4, egressMbps=8.1, latencyMs=22, errorRate=0.02),
        analysis=NodeAnalysis(
            summary="No client-side injection risks detected. CSP headers are configured correctly.",
            findings=[],
            recommendations=["Rotate the service account token used for auth-read."],
        ),
    ),
    TopologyNode(
        id="auth-svc",
        label="Auth Service",
        serviceId="AUTH-SVC",
        status="healthy",
        type="service",
        position={"x": 620, "y": 50},
        description="Handles authentication and session management. Issues short-lived JWTs.",
        telemetry=NodeTelemetry(ingressMbps=3.1, egressMbps=2.8, latencyMs=18, errorRate=0.0),
        analysis=NodeAnalysis(
            summary="Auth flows healthy. No brute-force or credential stuffing patterns observed.",
            findings=[],
            recommendations=["Enable passkey (WebAuthn) as a primary factor."],
        ),
    ),
    TopologyNode(
        id="api-core",
        label="Core API Hub",
        serviceId="API-CORE",
        status="warning",
        type="api",
        position={"x": 400, "y": 320},
        description="Node.js backend hub. Routes requests to downstream services and the LLM agent via MCP bridge.",
        telemetry=NodeTelemetry(ingressMbps=24.5, egressMbps=12.4, latencyMs=67, errorRate=0.8),
        analysis=NodeAnalysis(
            summary="WARNING: Core API Hub is routing requests to the compromised LLM agent. While the API itself shows no sign of RCE, it lacks an egress rate-limiter, allowing the compromised agent to exfiltrate data back through the API's return channels.",
            findings=[
                "No egress rate limiter on mcp_bridge_role connection.",
                "Outdated auth dependencies (passport@0.4.1).",
                "High latency spike detected — possible resource contention.",
            ],
            recommendations=[
                "Enforce strict egress policies on mcp_bridge_role.",
                "Rotate the mcp_bridge_role JWT immediately.",
                "Upgrade passport to latest LTS.",
            ],
        ),
    ),
    TopologyNode(
        id="llm-agent",
        label="Context Agent",
        serviceId="LLM-AGENT",
        status="compromised",
        type="agent",
        position={"x": 660, "y": 320},
        description="LLM-powered context agent with MCP tool access. Reads from Vector Store and returns augmented responses.",
        telemetry=NodeTelemetry(ingressMbps=8.2, egressMbps=31.4, latencyMs=340, errorRate=4.2),
        analysis=NodeAnalysis(
            summary="CRITICAL: Prompt injection attack detected. The agent is executing instructions embedded in user-supplied documents. Exfiltration of vector embeddings observed via crafted tool calls.",
            findings=[
                "Prompt injection via PDF ingestion endpoint.",
                "Anomalous tool call volume: 412 calls/min (baseline: 18).",
                "Outbound data 3.8x above baseline — likely exfiltration.",
                "Agent bypassing content policy filters via role-play jailbreak.",
            ],
            recommendations=[
                "Isolate this entity immediately.",
                "Revoke vector_read_role and mcp_bridge_role.",
                "Audit all tool call logs from the last 6 hours.",
                "Re-deploy agent with input sanitisation middleware.",
            ],
        ),
    ),
    TopologyNode(
        id="db-main",
        label="Primary Database",
        serviceId="DB-MAIN",
        status="healthy",
        type="database",
        position={"x": 840, "y": 160},
        description="PostgreSQL primary. Stores user records, session data, and application state.",
        telemetry=NodeTelemetry(ingressMbps=6.3, egressMbps=5.9, latencyMs=4, errorRate=0.0),
        analysis=NodeAnalysis(
            summary="No anomalous query patterns. Row-level security is enforced. Connections are limited to db_auth_admin and db_api_rw roles.",
            findings=[],
            recommendations=["Schedule next backup verification."],
        ),
    ),
    TopologyNode(
        id="db-vector",
        label="Vector Store",
        serviceId="DB-VECTOR",
        status="warning",
        type="database",
        position={"x": 950, "y": 420},
        description="Qdrant vector database. Holds document embeddings used by the Context Agent for RAG.",
        telemetry=NodeTelemetry(ingressMbps=14.7, egressMbps=28.3, latencyMs=11, errorRate=0.3),
        analysis=NodeAnalysis(
            summary="WARNING: Egress traffic is 2x baseline. Likely caused by the compromised LLM agent bulk-reading embeddings. Access should be suspended until the agent is remediated.",
            findings=[
                "Bulk read operations from LLM-AGENT account.",
                "Egress 2x above 7-day baseline.",
            ],
            recommendations=[
                "Suspend vector_read_role until LLM-AGENT is remediated.",
                "Enable query-level audit logging.",
            ],
        ),
    ),
]

MOCK_EDGES: List[TopologyEdge] = [
    TopologyEdge(id="e-ext-web", source="ext-lb", target="web-front", kind="network", label="NETWORK: public:443"),
    TopologyEdge(id="e-web-auth", source="web-front", target="auth-svc", kind="api", label="API: service_account:auth_read"),
    TopologyEdge(id="e-web-api", source="web-front", target="api-core", kind="api", label="API: frontend_role"),
    TopologyEdge(id="e-ext-api", source="ext-lb", target="api-core", kind="api", label="API: public:443 → internal:8080"),
    TopologyEdge(id="e-auth-db", source="auth-svc", target="db-main", kind="network", label="NETWORK: db_auth_admin"),
    TopologyEdge(id="e-api-db", source="api-core", target="db-main", kind="network", label="NETWORK: db_api_rw"),
    TopologyEdge(id="e-api-agent", source="api-core", target="llm-agent", kind="api", label="mcp_bridge_role", animated=True),
    TopologyEdge(id="e-agent-vector", source="llm-agent", target="db-vector", kind="api", label="vector_read_role", animated=True),
]

MOCK_VULNERABILITIES: List[dict] = [
    {
        "id": "vuln-001",
        "title": "Prompt Injection via PDF Ingestion",
        "severity": "critical",
        "affected_node_id": "llm-agent",
        "description": "Malicious instructions embedded in uploaded PDF documents are being executed by the LLM agent without sanitisation, allowing arbitrary tool-call sequences.",
        "status": "open",
    },
    {
        "id": "vuln-002",
        "title": "Missing Egress Rate Limiter on MCP Bridge",
        "severity": "high",
        "affected_node_id": "api-core",
        "description": "The mcp_bridge_role connection has no outbound rate limit, enabling a compromised agent to exfiltrate large volumes of data through normal API return channels.",
        "status": "open",
    },
    {
        "id": "vuln-003",
        "title": "Outdated Auth Dependency (passport@0.4.1)",
        "severity": "medium",
        "affected_node_id": "api-core",
        "description": "passport@0.4.1 has known session fixation vulnerabilities. Upgrade to v0.7.0+.",
        "status": "in-progress",
        "cve": "CVE-2022-25896",
    },
    {
        "id": "vuln-004",
        "title": "Bulk Embedding Reads by Compromised Agent",
        "severity": "high",
        "affected_node_id": "db-vector",
        "description": "The Context Agent is performing bulk reads of vector embeddings at 2x baseline rate, consistent with exfiltration of sensitive document content.",
        "status": "open",
    },
    {
        "id": "vuln-005",
        "title": "Jailbreak via Role-Play Prompt",
        "severity": "high",
        "affected_node_id": "llm-agent",
        "description": "Agent content-policy filters are being bypassed via a role-play framing jailbreak present in attacker-controlled document content.",
        "status": "open",
    },
    {
        "id": "vuln-006",
        "title": "Service Account Token Rotation Overdue",
        "severity": "low",
        "affected_node_id": "web-front",
        "description": "The auth_read service account token has not been rotated in 90+ days. Rotation policy recommends 30-day intervals.",
        "status": "open",
    },
]

MOCK_INSIGHTS: List[dict] = [
    {
        "id": "ins-001",
        "node_id": "llm-agent",
        "type": "threat",
        "summary": "Prompt injection attack confirmed",
        "details": "Cross-referencing tool call logs with ingested documents reveals a structured prompt injection payload in 3 of the last 12 PDF uploads. The attacker is using indirect injection to instruct the agent to call the file_read tool with arbitrary paths.",
        "confidence": 0.97,
    },
    {
        "id": "ins-002",
        "node_id": "api-core",
        "type": "anomaly",
        "summary": "Latency spike correlates with agent exfiltration bursts",
        "details": "P99 latency on /api/chat increased from 120ms to 680ms in the last 2 hours. Timing analysis correlates spikes with vector store bulk reads — the agent is blocking the response thread while staging exfiltration payloads.",
        "confidence": 0.88,
    },
    {
        "id": "ins-003",
        "node_id": "db-vector",
        "type": "anomaly",
        "summary": "Embedding namespace enumeration detected",
        "details": "Query logs show systematic reads across all embedding namespaces in alphabetical order — a pattern consistent with automated enumeration rather than semantic retrieval.",
        "confidence": 0.82,
    },
    {
        "id": "ins-004",
        "node_id": "ext-lb",
        "type": "info",
        "summary": "Traffic from 3 new ASNs in the last hour",
        "details": "New source ASNs detected: AS14618 (AWS), AS16509 (AWS), AS15169 (Google). Volume is within normal bounds; likely legitimate cloud-to-cloud traffic. No action required.",
        "confidence": 0.65,
    },
]

MOCK_RBAC: List[dict] = [
    {
        "id": "rbac-001",
        "role": "mcp_bridge_role",
        "subject": "LLM-AGENT",
        "permissions": ["api:invoke", "api:stream", "api:read"],
        "scope": "api-core/*",
        "risk_level": "high",
    },
    {
        "id": "rbac-002",
        "role": "vector_read_role",
        "subject": "LLM-AGENT",
        "permissions": ["vector:read", "vector:search"],
        "scope": "db-vector/*",
        "risk_level": "high",
    },
    {
        "id": "rbac-003",
        "role": "frontend_role",
        "subject": "WEB-FRONT",
        "permissions": ["api:read", "api:write"],
        "scope": "api-core/public/*",
        "risk_level": "low",
    },
    {
        "id": "rbac-004",
        "role": "service_account:auth_read",
        "subject": "WEB-FRONT",
        "permissions": ["auth:verify", "auth:refresh"],
        "scope": "auth-svc/*",
        "risk_level": "medium",
    },
    {
        "id": "rbac-005",
        "role": "db_auth_admin",
        "subject": "AUTH-SVC",
        "permissions": ["db:read", "db:write", "db:admin"],
        "scope": "db-main/auth_schema",
        "risk_level": "medium",
    },
    {
        "id": "rbac-006",
        "role": "db_api_rw",
        "subject": "API-CORE",
        "permissions": ["db:read", "db:write"],
        "scope": "db-main/app_schema",
        "risk_level": "low",
    },
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


def _parse_compose_to_topology(compose_text: str) -> tuple[list[dict], list[dict]]:
    """Parse a Docker Compose YAML string into topology node/edge dicts.

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

        nodes.append({
            "id": svc_name,
            "label": svc_name,
            "service_id": svc_name,
            "status": "healthy",
            "type": _guess_type(svc_name, svc),
            "position": {"x": 60 + col * COL_WIDTH, "y": 60 + row * ROW_HEIGHT},
            "description": f"Imported from Docker Compose.{ports_desc}",
        })

        # Edges from depends_on
        depends = svc.get("depends_on") or []
        if isinstance(depends, dict):
            depends = list(depends.keys())
        for dep in depends:
            edge_id = f"e-{svc_name}-{dep}"
            if edge_id not in seen_edges and dep in services:
                edges.append({
                    "id": edge_id,
                    "source_id": svc_name,
                    "target_id": dep,
                    "kind": "network",
                    "label": f"depends_on",
                    "animated": False,
                })
                seen_edges.add(edge_id)

    # Edges from shared networks
    network_members: dict[str, list[str]] = {}
    for svc_name, svc in services.items():
        nets = svc.get("networks")
        if isinstance(nets, list):
            for n in nets:
                network_members.setdefault(n, []).append(svc_name)
        elif isinstance(nets, dict):
            for n in nets:
                network_members.setdefault(n, []).append(svc_name)

    for net_name, members in network_members.items():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                edge_id = f"e-net-{net_name}-{a}-{b}"
                if edge_id not in seen_edges:
                    edges.append({
                        "id": edge_id,
                        "source_id": a,
                        "target_id": b,
                        "kind": "network",
                        "label": f"network:{net_name}",
                        "animated": False,
                    })
                    seen_edges.add(edge_id)

    return nodes, edges


def _bytes_to_mbps(byte_count: float, interval_seconds: float = 15.0) -> float:
    """Convert a byte count over an interval to Mbps (megabits per second)."""
    if interval_seconds <= 0:
        return 0.0
    return round((byte_count * 8) / (interval_seconds * 1_000_000), 3)


async def _aggregate_node_telemetry(
    node_id: str,
    db: AsyncSession,
    lookback_seconds: int = 60,
) -> Optional[NodeTelemetry]:
    """Aggregate recent network telemetry for containers mapped to *node_id*.

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

    # Latest snapshot per container within the lookback window
    snapshots_q = await db.execute(
        select(ContainerMetricSnapshot)
        .where(
            ContainerMetricSnapshot.container_id.in_(container_ids),
            ContainerMetricSnapshot.timestamp >= cutoff,
        )
        .order_by(ContainerMetricSnapshot.timestamp.desc())
    )
    snapshots = snapshots_q.scalars().all()
    if not snapshots:
        return None

    # Use the most recent snapshot per container for throughput calculation
    seen_containers: set[int] = set()
    total_rx_bytes = 0.0
    total_tx_bytes = 0.0
    latest_ts: Optional[datetime] = None

    for snap in snapshots:
        # Only take the latest snapshot per container
        if snap.container_id in seen_containers:
            continue
        seen_containers.add(snap.container_id)

        net = snap.network_stats
        if net and isinstance(net, dict):
            # cAdvisor network stats may be a dict of interfaces or a flat dict
            if "interfaces" in net:
                for iface in net["interfaces"]:
                    total_rx_bytes += iface.get("rx_bytes", 0)
                    total_tx_bytes += iface.get("tx_bytes", 0)
            else:
                total_rx_bytes += net.get("rx_bytes", 0)
                total_tx_bytes += net.get("tx_bytes", 0)

        if latest_ts is None or snap.timestamp > latest_ts:
            latest_ts = snap.timestamp

    ingress = _bytes_to_mbps(total_rx_bytes)
    egress = _bytes_to_mbps(total_tx_bytes)

    return NodeTelemetry(
        ingressMbps=ingress,
        egressMbps=egress,
        latencyMs=None,    # Not derivable from cAdvisor
        errorRate=None,     # Not derivable from cAdvisor
        lastSeen=latest_ts.isoformat() if latest_ts else None,
    )


def _compute_node_status(
    current_status: str,
    telemetry: Optional[NodeTelemetry],
    last_snapshot_ts: Optional[datetime] = None,
) -> str:
    """Deterministic status engine.

    Rules (applied in priority order):
    1. ``compromised`` is sticky — only manual action can clear it.
    2. If no telemetry data exists at all → keep current DB status.
    3. If the most recent snapshot is stale → ``warning``.
    4. If egress > threshold → ``warning``.
    5. Otherwise → keep current DB status (preserves seeded warnings).

    This engine never promotes a node to *compromised* – that requires
    stronger evidence (e.g. LLM-driven analysis).
    """
    # Compromised is sticky — never auto-downgrade
    if current_status == "compromised":
        return "compromised"

    if telemetry is None:
        return current_status  # no mapped containers or no data yet

    # Staleness check (only for live telemetry with lastSeen timestamps)
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

    # Preserve DB status (keeps seeded "warning" states)
    return current_status


async def _compute_security_score(db: AsyncSession) -> SecurityScore:
    score = 100
    breakdown = []

    nodes_q = await db.execute(select(DBNode))
    nodes = nodes_q.scalars().all()
    compromised = sum(1 for n in nodes if n.status == "compromised")
    warning = sum(1 for n in nodes if n.status == "warning")
    if compromised:
        impact = -20 * compromised
        breakdown.append({"label": f"{compromised} compromised node{'s' if compromised > 1 else ''}", "impact": impact})
        score += impact
    if warning:
        impact = -10 * warning
        breakdown.append({"label": f"{warning} warning node{'s' if warning > 1 else ''}", "impact": impact})
        score += impact

    vulns_q = await db.execute(select(DBVuln))
    vulns = vulns_q.scalars().all()
    crit_vulns = sum(1 for v in vulns if v.severity == "critical" and v.status == "open")
    high_vulns = sum(1 for v in vulns if v.severity == "high" and v.status == "open")
    if crit_vulns:
        impact = -8 * crit_vulns
        breakdown.append({"label": f"{crit_vulns} critical vuln{'s' if crit_vulns > 1 else ''}", "impact": impact})
        score += impact
    if high_vulns:
        impact = -5 * high_vulns
        breakdown.append({"label": f"{high_vulns} high vuln{'s' if high_vulns > 1 else ''}", "impact": impact})
        score += impact

    rbac_q = await db.execute(select(DBRBAC))
    rbacs = rbac_q.scalars().all()
    high_risk = sum(1 for p in rbacs if p.risk_level == "high")
    if high_risk:
        impact = -3 * high_risk
        breakdown.append({"label": f"{high_risk} high-risk RBAC", "impact": impact})
        score += impact

    return SecurityScore(score=max(0, score), breakdown=breakdown)


# ────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────


async def seed_demo_data(db: AsyncSession) -> str:
    """Seed all demo data if the database is empty. Returns status string."""
    # Check if already seeded
    res = await db.execute(select(DBNode).limit(1))
    if res.scalar_one_or_none():
        return "already_seeded"

    # Seed topology nodes (must flush before edges due to FK constraints)
    for n in MOCK_NODES:
        db.add(DBNode(
            id=n.id, label=n.label, service_id=n.serviceId, status=n.status, type=n.type,
            position=n.position, description=n.description,
            telemetry=n.telemetry.model_dump() if n.telemetry else None,
            analysis=n.analysis.model_dump() if n.analysis else None,
        ))
    await db.flush()

    # Seed topology edges
    for e in MOCK_EDGES:
        db.add(DBEdge(
            id=e.id, source_id=e.source, target_id=e.target, kind=e.kind, label=e.label, animated=e.animated
        ))
    await db.flush()
    # Seed vulnerabilities
    for v in MOCK_VULNERABILITIES:
        db.add(DBVuln(**v))
    # Seed LLM insights
    for i in MOCK_INSIGHTS:
        db.add(DBInsight(**i))
    # Seed RBAC policies
    for r in MOCK_RBAC:
        db.add(DBRBAC(**r))

    await db.commit()
    return "seeded"


@router.post("/topology/seed")
async def seed_topology(db: AsyncSession = Depends(get_db_session)) -> dict:
    """Creates the tables and seeds them with initial data if empty."""
    from app.core.database import Base
    conn = await db.connection()
    await conn.run_sync(Base.metadata.create_all)

    status = await seed_demo_data(db)
    return {"status": status}


@router.post("/topology/import")
async def import_topology(
    body: ComposeImportRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Import topology from a Docker Compose YAML document.

    Parses services, depends_on, and shared networks to create topology
    nodes and edges.  Existing nodes/edges are deleted first so each import
    is idempotent.

    Example payload::

        {
            "yaml_content": "<raw docker-compose YAML>"
        }
    """
    node_dicts, edge_dicts = _parse_compose_to_topology(body.yaml_content)

    # Clear existing topology (idempotent import)
    await db.execute(delete(DBEdge))
    await db.execute(delete(DBNode))

    for nd in node_dicts:
        db.add(DBNode(**nd))
    for ed in edge_dicts:
        db.add(DBEdge(**ed))
    await db.commit()

    return {
        "status": "imported",
        "nodes": len(node_dicts),
        "edges": len(edge_dicts),
    }


@router.get("/topology", response_model=TopologyData)
async def get_topology(db: AsyncSession = Depends(get_db_session)) -> TopologyData:
    nodes_q = await db.execute(select(DBNode))
    edges_q = await db.execute(select(DBEdge))

    nodes = []
    for n in nodes_q.scalars().all():
        # Try live telemetry first, fall back to stored/seeded telemetry
        telem = await _aggregate_node_telemetry(n.id, db)
        if telem is None and n.telemetry and isinstance(n.telemetry, dict):
            telem = NodeTelemetry(**n.telemetry)

        # Deterministic status engine (preserves DB status when no live telemetry)
        status = _compute_node_status(n.status, telem)

        # Parse stored analysis
        analysis = None
        if n.analysis and isinstance(n.analysis, dict):
            analysis = NodeAnalysis(**n.analysis)

        nodes.append(TopologyNode(
            id=n.id, label=n.label, serviceId=n.service_id, status=status, type=n.type,
            position=n.position, description=n.description,
            telemetry=telem,
            analysis=analysis,
        ))

    edges = []
    for e in edges_q.scalars().all():
        edges.append(TopologyEdge(
            id=e.id, source=e.source_id, target=e.target_id, kind=e.kind, label=e.label, animated=e.animated
        ))

    return TopologyData(
        nodes=nodes,
        edges=edges,
        lastUpdated=datetime.now(UTC).isoformat(),
        scanStatus="idle"
    )


@router.post("/topology/scan", response_model=TopologyData)
async def run_scan(db: AsyncSession = Depends(get_db_session)) -> TopologyData:
    # Try the LangGraph agent; fall back gracefully if OpenAI key missing
    try:
        await run_topology_analysis(db)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Topology scan agent skipped: {e}")

    topo = await get_topology(db)
    topo.scanStatus = "complete"
    return topo


@router.post("/topology/{node_id}/isolate")
async def isolate_node(node_id: str, db: AsyncSession = Depends(get_db_session)) -> dict:
    return {"success": True, "nodeId": node_id, "action": "isolated"}


@router.get("/vulnerabilities", response_model=List[Vulnerability])
async def get_vulnerabilities(db: AsyncSession = Depends(get_db_session)) -> List[Vulnerability]:
    q = await db.execute(select(DBVuln))
    # Build a node_id → label lookup for human-readable affectedNode name
    nodes_q = await db.execute(select(DBNode.id, DBNode.label))
    node_labels = {r[0]: r[1] for r in nodes_q.all()}

    return [
        Vulnerability(
            id=v.id, title=v.title, severity=v.severity,
            affectedNode=node_labels.get(v.affected_node_id, v.affected_node_id),
            affectedNodeId=v.affected_node_id, description=v.description,
            discoveredAt=v.discovered_at.isoformat() if v.discovered_at else _iso(),
            status=v.status, cve=v.cve
        ) for v in q.scalars().all()
    ]


@router.get("/insights", response_model=List[LLMInsight])
async def get_insights(db: AsyncSession = Depends(get_db_session)) -> List[LLMInsight]:
    q = await db.execute(select(DBInsight))
    # Build a node_id → label lookup for human-readable nodeName
    nodes_q = await db.execute(select(DBNode.id, DBNode.label))
    node_labels = {r[0]: r[1] for r in nodes_q.all()}

    return [
        LLMInsight(
            id=i.id, nodeId=i.node_id,
            nodeName=node_labels.get(i.node_id, i.node_id),
            type=i.type, summary=i.summary,
            details=i.details,
            timestamp=i.timestamp.isoformat() if i.timestamp else _iso(),
            confidence=i.confidence
        ) for i in q.scalars().all()
    ]


@router.get("/rbac", response_model=List[RBACPolicy])
async def get_rbac(db: AsyncSession = Depends(get_db_session)) -> List[RBACPolicy]:
    q = await db.execute(select(DBRBAC))
    return [
        RBACPolicy(
            id=r.id, role=r.role, subject=r.subject, permissions=r.permissions,
            scope=r.scope,
            lastModified=r.last_modified.isoformat() if r.last_modified else _iso(),
            riskLevel=r.risk_level
        ) for r in q.scalars().all()
    ]


@router.post("/rbac/{node_id}/revoke")
async def revoke_rbac(node_id: str, db: AsyncSession = Depends(get_db_session)) -> dict:
    return {"success": True, "nodeId": node_id, "action": "rbac_revoked"}


@router.get("/security-score", response_model=SecurityScore)
async def get_security_score(db: AsyncSession = Depends(get_db_session)) -> SecurityScore:
    return await _compute_security_score(db)
