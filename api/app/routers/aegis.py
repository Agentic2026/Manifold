from typing import Any, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["aegis"])

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
    status: str
    type: str
    position: dict
    description: Optional[str] = None
    telemetry: Optional[NodeTelemetry] = None
    analysis: Optional[NodeAnalysis] = None

class TopologyEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: str
    label: str
    animated: Optional[bool] = False

class TopologyData(BaseModel):
    nodes: List[TopologyNode]
    edges: List[TopologyEdge]
    lastUpdated: str
    scanStatus: str

class Vulnerability(BaseModel):
    id: str
    title: str
    severity: str
    affectedNode: str
    affectedNodeId: str
    description: str
    discoveredAt: str
    status: str
    cve: Optional[str] = None

class LLMInsight(BaseModel):
    id: str
    nodeId: str
    nodeName: str
    type: str
    summary: str
    details: str
    timestamp: str
    confidence: float

class RBACPolicy(BaseModel):
    id: str
    role: str
    subject: str
    permissions: List[str]
    scope: str
    lastModified: str
    riskLevel: str

# MOCK DATA
MOCK_TOPOLOGY = TopologyData(
    nodes=[],
    edges=[],
    lastUpdated="2026-01-01T00:00:00Z",
    scanStatus="idle"
)

@router.get("/topology", response_model=TopologyData)
def get_topology() -> TopologyData:
    return MOCK_TOPOLOGY

@router.post("/topology/scan", response_model=TopologyData)
def run_scan() -> TopologyData:
    return MOCK_TOPOLOGY

@router.post("/topology/{node_id}/isolate")
def isolate_node(node_id: str) -> dict:
    return {"success": True}

@router.get("/vulnerabilities", response_model=List[Vulnerability])
def get_vulnerabilities() -> List[Vulnerability]:
    return []

@router.get("/insights", response_model=List[LLMInsight])
def get_insights() -> List[LLMInsight]:
    return []

@router.get("/rbac", response_model=List[RBACPolicy])
def get_rbac() -> List[RBACPolicy]:
    return []

@router.post("/rbac/{node_id}/revoke")
def revoke_rbac(node_id: str) -> dict:
    return {"success": True}
