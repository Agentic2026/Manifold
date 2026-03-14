from datetime import UTC, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete

from app.core.database import get_db_session
from app.models.topology import TopologyNode as DBNode, TopologyEdge as DBEdge, Vulnerability as DBVuln, LLMInsight as DBInsight, RBACPolicy as DBRBAC
from app.agents.topology import run_topology_analysis

router = APIRouter(prefix="/api", tags=["aegis"])


# ────────────────────────────────────────────────────────────
# Pydantic models (match frontend TypeScript types exactly)
# ────────────────────────────────────────────────────────────


class NodeTelemetry(BaseModel):
    ingressMbps: float
    egressMbps: float
    latencyMs: float
    errorRate: float


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
    TopologyEdge(id="e-ext-web", source="ext-lb", target="web-front", kind="network", label="NETWORK: public:443"),
    TopologyEdge(id="e-web-auth", source="web-front", target="auth-svc", kind="api", label="API: service_account:auth_read"),
    TopologyEdge(id="e-web-api", source="web-front", target="api-core", kind="api", label="API: frontend_role"),
    TopologyEdge(id="e-ext-api", source="ext-lb", target="api-core", kind="api", label="API: public:443 → internal:8080"),
    TopologyEdge(id="e-auth-db", source="auth-svc", target="db-main", kind="network", label="NETWORK: db_auth_admin"),
    TopologyEdge(id="e-api-db", source="api-core", target="db-main", kind="network", label="NETWORK: db_api_rw"),
    TopologyEdge(id="e-api-agent", source="api-core", target="llm-agent", kind="api", label="mcp_bridge_role", animated=True),
    TopologyEdge(id="e-agent-vector", source="llm-agent", target="db-vector", kind="api", label="vector_read_role", animated=True),
]

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
        db.add(DBNode(
            id=n.id, label=n.label, service_id=n.serviceId, status=n.status, type=n.type,
            position=n.position, description=n.description
        ))
    for e in MOCK_EDGES:
        db.add(DBEdge(
            id=e.id, source_id=e.source, target_id=e.target, kind=e.kind, label=e.label, animated=e.animated
        ))
    await db.commit()
    return {"status": "seeded"}


@router.get("/topology", response_model=TopologyData)
async def get_topology(db: AsyncSession = Depends(get_db_session)) -> TopologyData:
    nodes_q = await db.execute(select(DBNode))
    edges_q = await db.execute(select(DBEdge))
    
    nodes = []
    for n in nodes_q.scalars().all():
        nodes.append(TopologyNode(
            id=n.id, label=n.label, serviceId=n.service_id, status=n.status, type=n.type,
            position=n.position, description=n.description, telemetry=None, analysis=None
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
async def run_scan(db: AsyncSession = Depends(get_db_session)) -> dict:
    # Trigger the background LangGraph DAG topology agent
    analysis_update = await run_topology_analysis(db)
    
    # Return topology with scanning status true (frontend usually polls afterward)
    topo = await get_topology(db)
    topo.scanStatus = "complete"
    return topo


@router.post("/topology/{node_id}/isolate")
async def isolate_node(node_id: str, db: AsyncSession = Depends(get_db_session)) -> dict:
    return {"success": True, "nodeId": node_id, "action": "isolated"}


@router.get("/vulnerabilities", response_model=List[Vulnerability])
async def get_vulnerabilities(db: AsyncSession = Depends(get_db_session)) -> List[Vulnerability]:
    q = await db.execute(select(DBVuln))
    return [
        Vulnerability(
            id=v.id, title=v.title, severity=v.severity, affectedNode=v.affected_node_id,
            affectedNodeId=v.affected_node_id, description=v.description, 
            discoveredAt=v.discovered_at.isoformat(), status=v.status, cve=v.cve
        ) for v in q.scalars().all()
    ]


@router.get("/insights", response_model=List[LLMInsight])
async def get_insights(db: AsyncSession = Depends(get_db_session)) -> List[LLMInsight]:
    q = await db.execute(select(DBInsight))
    return [
        LLMInsight(
            id=i.id, nodeId=i.node_id, nodeName=i.node_id, type=i.type, summary=i.summary,
            details=i.details, timestamp=i.timestamp.isoformat(), confidence=i.confidence
        ) for i in q.scalars().all()
    ]


@router.get("/rbac", response_model=List[RBACPolicy])
async def get_rbac(db: AsyncSession = Depends(get_db_session)) -> List[RBACPolicy]:
    q = await db.execute(select(DBRBAC))
    return [
        RBACPolicy(
            id=r.id, role=r.role, subject=r.subject, permissions=r.permissions,
            scope=r.scope, lastModified=r.last_modified.isoformat(), riskLevel=r.risk_level
        ) for r in q.scalars().all()
    ]


@router.post("/rbac/{node_id}/revoke")
async def revoke_rbac(node_id: str, db: AsyncSession = Depends(get_db_session)) -> dict:
    return {"success": True, "nodeId": node_id, "action": "rbac_revoked"}


@router.get("/security-score", response_model=SecurityScore)
async def get_security_score(db: AsyncSession = Depends(get_db_session)) -> SecurityScore:
    return await _compute_security_score(db)
