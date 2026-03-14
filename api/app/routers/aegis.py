from datetime import UTC, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

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
# Mock data (mirrors frontend aegis.ts exactly)
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

MOCK_VULNERABILITIES: List[Vulnerability] = [
    Vulnerability(
        id="vuln-001",
        title="Prompt Injection via PDF Ingestion",
        severity="critical",
        affectedNode="Context Agent",
        affectedNodeId="llm-agent",
        description="Malicious instructions embedded in uploaded PDF documents are being executed by the LLM agent without sanitisation, allowing arbitrary tool-call sequences.",
        discoveredAt=_iso(2),
        status="open",
    ),
    Vulnerability(
        id="vuln-002",
        title="Missing Egress Rate Limiter on MCP Bridge",
        severity="high",
        affectedNode="Core API Hub",
        affectedNodeId="api-core",
        description="The mcp_bridge_role connection has no outbound rate limit, enabling a compromised agent to exfiltrate large volumes of data through normal API return channels.",
        discoveredAt=_iso(4),
        status="open",
    ),
    Vulnerability(
        id="vuln-003",
        title="Outdated Auth Dependency (passport@0.4.1)",
        severity="medium",
        affectedNode="Core API Hub",
        affectedNodeId="api-core",
        description="passport@0.4.1 has known session fixation vulnerabilities. Upgrade to v0.7.0+.",
        discoveredAt=_iso(24),
        status="in-progress",
        cve="CVE-2022-25896",
    ),
    Vulnerability(
        id="vuln-004",
        title="Bulk Embedding Reads by Compromised Agent",
        severity="high",
        affectedNode="Vector Store",
        affectedNodeId="db-vector",
        description="The Context Agent is performing bulk reads of vector embeddings at 2x baseline rate, consistent with exfiltration of sensitive document content.",
        discoveredAt=_iso(1),
        status="open",
    ),
    Vulnerability(
        id="vuln-005",
        title="Jailbreak via Role-Play Prompt",
        severity="high",
        affectedNode="Context Agent",
        affectedNodeId="llm-agent",
        description="Agent content-policy filters are being bypassed via a role-play framing jailbreak present in attacker-controlled document content.",
        discoveredAt=_iso(3),
        status="open",
    ),
    Vulnerability(
        id="vuln-006",
        title="Service Account Token Rotation Overdue",
        severity="low",
        affectedNode="Web Frontend",
        affectedNodeId="web-front",
        description="The auth_read service account token has not been rotated in 90+ days. Rotation policy recommends 30-day intervals.",
        discoveredAt=_iso(168),  # 7 days
        status="open",
    ),
]

MOCK_INSIGHTS: List[LLMInsight] = [
    LLMInsight(
        id="ins-001",
        nodeId="llm-agent",
        nodeName="Context Agent",
        type="threat",
        summary="Prompt injection attack confirmed",
        details="Cross-referencing tool call logs with ingested documents reveals a structured prompt injection payload in 3 of the last 12 PDF uploads. The attacker is using indirect injection to instruct the agent to call the file_read tool with arbitrary paths.",
        timestamp=_iso(0.5),
        confidence=0.97,
    ),
    LLMInsight(
        id="ins-002",
        nodeId="api-core",
        nodeName="Core API Hub",
        type="anomaly",
        summary="Latency spike correlates with agent exfiltration bursts",
        details="P99 latency on /api/chat increased from 120ms to 680ms in the last 2 hours. Timing analysis correlates spikes with vector store bulk reads — the agent is blocking the response thread while staging exfiltration payloads.",
        timestamp=_iso(0.75),
        confidence=0.88,
    ),
    LLMInsight(
        id="ins-003",
        nodeId="db-vector",
        nodeName="Vector Store",
        type="anomaly",
        summary="Embedding namespace enumeration detected",
        details="Query logs show systematic reads across all embedding namespaces in alphabetical order — a pattern consistent with automated enumeration rather than semantic retrieval.",
        timestamp=_iso(1),
        confidence=0.82,
    ),
    LLMInsight(
        id="ins-004",
        nodeId="ext-lb",
        nodeName="External Gateway",
        type="info",
        summary="Traffic from 3 new ASNs in the last hour",
        details="New source ASNs detected: AS14618 (AWS), AS16509 (AWS), AS15169 (Google). Volume is within normal bounds; likely legitimate cloud-to-cloud traffic. No action required.",
        timestamp=_iso(1.5),
        confidence=0.65,
    ),
]

MOCK_RBAC: List[RBACPolicy] = [
    RBACPolicy(id="rbac-001", role="mcp_bridge_role", subject="LLM-AGENT", permissions=["api:invoke", "api:stream", "api:read"], scope="api-core/*", lastModified=_iso_days(30), riskLevel="high"),
    RBACPolicy(id="rbac-002", role="vector_read_role", subject="LLM-AGENT", permissions=["vector:read", "vector:search"], scope="db-vector/*", lastModified=_iso_days(45), riskLevel="high"),
    RBACPolicy(id="rbac-003", role="frontend_role", subject="WEB-FRONT", permissions=["api:read", "api:write"], scope="api-core/public/*", lastModified=_iso_days(60), riskLevel="low"),
    RBACPolicy(id="rbac-004", role="service_account:auth_read", subject="WEB-FRONT", permissions=["auth:verify", "auth:refresh"], scope="auth-svc/*", lastModified=_iso_days(90), riskLevel="medium"),
    RBACPolicy(id="rbac-005", role="db_auth_admin", subject="AUTH-SVC", permissions=["db:read", "db:write", "db:admin"], scope="db-main/auth_schema", lastModified=_iso_days(120), riskLevel="medium"),
    RBACPolicy(id="rbac-006", role="db_api_rw", subject="API-CORE", permissions=["db:read", "db:write"], scope="db-main/app_schema", lastModified=_iso_days(90), riskLevel="low"),
]


def _build_topology() -> TopologyData:
    return TopologyData(
        nodes=MOCK_NODES,
        edges=MOCK_EDGES,
        lastUpdated=datetime.now(UTC).isoformat(),
        scanStatus="idle",
    )


def _compute_security_score() -> SecurityScore:
    score = 100
    breakdown = []

    compromised = sum(1 for n in MOCK_NODES if n.status == "compromised")
    warning = sum(1 for n in MOCK_NODES if n.status == "warning")
    if compromised:
        impact = -20 * compromised
        breakdown.append({"label": f"{compromised} compromised node{'s' if compromised > 1 else ''}", "impact": impact})
        score += impact
    if warning:
        impact = -10 * warning
        breakdown.append({"label": f"{warning} warning node{'s' if warning > 1 else ''}", "impact": impact})
        score += impact

    crit_vulns = sum(1 for v in MOCK_VULNERABILITIES if v.severity == "critical" and v.status == "open")
    high_vulns = sum(1 for v in MOCK_VULNERABILITIES if v.severity == "high" and v.status == "open")
    if crit_vulns:
        impact = -8 * crit_vulns
        breakdown.append({"label": f"{crit_vulns} critical vuln{'s' if crit_vulns > 1 else ''}", "impact": impact})
        score += impact
    if high_vulns:
        impact = -5 * high_vulns
        breakdown.append({"label": f"{high_vulns} high vuln{'s' if high_vulns > 1 else ''}", "impact": impact})
        score += impact

    high_risk = sum(1 for p in MOCK_RBAC if p.riskLevel == "high")
    if high_risk:
        impact = -3 * high_risk
        breakdown.append({"label": f"{high_risk} high-risk RBAC", "impact": impact})
        score += impact

    return SecurityScore(score=max(0, score), breakdown=breakdown)


# ────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────


@router.get("/topology", response_model=TopologyData)
def get_topology() -> TopologyData:
    return _build_topology()


@router.post("/topology/scan", response_model=TopologyData)
def run_scan() -> TopologyData:
    data = _build_topology()
    data.scanStatus = "complete"
    return data


@router.post("/topology/{node_id}/isolate")
def isolate_node(node_id: str) -> dict:
    return {"success": True, "nodeId": node_id, "action": "isolated"}


@router.get("/vulnerabilities", response_model=List[Vulnerability])
def get_vulnerabilities() -> List[Vulnerability]:
    return MOCK_VULNERABILITIES


@router.get("/insights", response_model=List[LLMInsight])
def get_insights() -> List[LLMInsight]:
    return MOCK_INSIGHTS


@router.get("/rbac", response_model=List[RBACPolicy])
def get_rbac() -> List[RBACPolicy]:
    return MOCK_RBAC


@router.post("/rbac/{node_id}/revoke")
def revoke_rbac(node_id: str) -> dict:
    return {"success": True, "nodeId": node_id, "action": "rbac_revoked"}


@router.get("/security-score", response_model=SecurityScore)
def get_security_score() -> SecurityScore:
    return _compute_security_score()
