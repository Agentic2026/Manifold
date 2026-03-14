import json
import logging
from typing import Dict, List, Any, TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.topology import TopologyNode, TopologyEdge, Vulnerability, LLMInsight
from app.agents.tools.telemetry import get_resource_spikes_impl

logger = logging.getLogger(__name__)

# --- State Definitions ---

class TopologyState(TypedDict):
    db: AsyncSession
    recent_spikes: str
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    messages: Annotated[Sequence[BaseMessage], "messages"]
    analysis_result: Dict[str, Any]


# --- Structured Output Schema for LLM ---

class NodeUpdate(BaseModel):
    id: str = Field(description="The ID of the TopologyNode to update")
    status: str = Field(description="The new status: 'healthy', 'warning', or 'compromised'")
    rationale: str = Field(description="Brief explanation for the status change")

class NewVulnerability(BaseModel):
    title: str = Field(description="Title of the vulnerability")
    severity: str = Field(description="'critical', 'high', 'medium', or 'low'")
    affected_node_id: str = Field(description="ID of the affected node")
    description: str = Field(description="Detailed description")

class NewInsight(BaseModel):
    node_id: str = Field(description="ID of the node this insight relates to")
    type: str = Field(description="'anomaly', 'threat', or 'info'")
    summary: str = Field(description="Short summary")
    details: str = Field(description="Detailed explanation")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")

class ImpactAnalysisOutput(BaseModel):
    node_updates: List[NodeUpdate] = Field(description="Nodes whose status should be updated based on telemetry spikes and DAG propagation")
    new_vulnerabilities: List[NewVulnerability] = Field(description="Any new vulnerabilities discovered")
    new_insights: List[NewInsight] = Field(description="Any new LLM insights generated")


# --- Graph Nodes ---

async def fetch_telemetry_and_dag(state: TopologyState) -> TopologyState:
    """Fetch the latest topology DAG from PostgreSQL and grab recent container spikes."""
    db = state["db"]
    
    # Grab recent spikes (last 5 minutes)
    try:
        spikes = await get_resource_spikes_impl(300, db)
    except Exception as e:
        logger.error(f"Failed to fetch spikes: {e}")
        spikes = "Error fetching spikes."
        
    # Grab DAG
    nodes_result = await db.execute(select(TopologyNode))
    edges_result = await db.execute(select(TopologyEdge))
    
    # We serialize them to dicts to feed to the LLM easily
    nodes = [
        {"id": n.id, "label": n.label, "status": n.status, "type": n.type}
        for n in nodes_result.scalars().all()
    ]
    edges = [
        {"source": e.source_id, "target": e.target_id, "kind": e.kind}
        for e in edges_result.scalars().all()
    ]
    
    return {"recent_spikes": spikes, "nodes": nodes, "edges": edges}


async def analyze_impact(state: TopologyState) -> TopologyState:
    """Use an LLM with structured output to analyze the DAG and telemetry."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0).with_structured_output(ImpactAnalysisOutput)
    
    sys_prompt = f"""You are an autonomous AI security architect analyzing a live system topology DAG.
    
    Here is the current System DAG:
    Nodes: {json.dumps(state['nodes'], indent=2)}
    Edges: {json.dumps(state['edges'], indent=2)}
    
    Here are the recent container resource spikes (from cAdvisor telemetry):
    {state['recent_spikes']}
    
    Your goal:
    1. Identify if any nodes in the DAG represent the containers showing massive spikes (fuzzy match container names to node labels/types).
    2. If a node is spiking, mark it as 'warning' or 'compromised'.
    3. Analyze the edges. If a compromised node has an edge to a downstream node, propagate the risk (e.g., mark the downstream node as 'warning').
    4. Generate Vulnerabilities and Insights explaining your reasoning.
    
    Return the structured output containing the updates you intend to apply.
    """
    
    try:
        result = await llm.ainvoke([SystemMessage(content=sys_prompt)])
        # Pydantic model returned directly because of with_structured_output
        return {"analysis_result": result.model_dump()}
    except Exception as e:
        logger.error(f"LLM Impact analysis failed: {e}")
        return {"analysis_result": {"node_updates": [], "new_vulnerabilities": [], "new_insights": []}}


async def apply_updates(state: TopologyState) -> TopologyState:
    """Write the LLM's suggested updates back to PostgreSQL."""
    db = state["db"]
    analysis = state.get("analysis_result", {})
    
    # 1. Update Nodes
    for update in analysis.get("node_updates", []):
        node_id = update["id"]
        new_status = update["status"]
        
        # A bit inefficient, but safe: select then update
        node_q = await db.execute(select(TopologyNode).where(TopologyNode.id == node_id))
        node = node_q.scalar_one_or_none()
        if node and node.status != "compromised": # Once compromised, stay compromised manually
            node.status = new_status
            
    # 2. Insert new Vulnerabilities
    import uuid
    for v in analysis.get("new_vulnerabilities", []):
        new_vuln = Vulnerability(
            id=f"vuln-{uuid.uuid4().hex[:8]}",
            title=v["title"],
            severity=v["severity"],
            affected_node_id=v["affected_node_id"],
            description=v["description"],
            status="open"
        )
        db.add(new_vuln)
        
    # 3. Insert new Insights
    for i in analysis.get("new_insights", []):
        new_ins = LLMInsight(
            id=f"ins-{uuid.uuid4().hex[:8]}",
            node_id=i["node_id"],
            type=i["type"],
            summary=i["summary"],
            details=i["details"],
            confidence=i["confidence"]
        )
        db.add(new_ins)
        
    await db.commit()
    logger.info("DAG Topology updates applied successfully based on LangGraph analysis.")
    return state


# --- Build Graph ---
builder = StateGraph(TopologyState)
builder.add_node("fetch", fetch_telemetry_and_dag)
builder.add_node("analyze", analyze_impact)
builder.add_node("apply", apply_updates)

builder.add_edge(START, "fetch")
builder.add_edge("fetch", "analyze")
builder.add_edge("analyze", "apply")
builder.add_edge("apply", END)

topology_agent = builder.compile()

# --- Entrypoint ---
async def run_topology_analysis(db: AsyncSession) -> Dict[str, Any]:
    """Execute the topology background agent."""
    initial_state = {"db": db, "messages": []}
    
    # Execute the graph
    try:
        final_state = await topology_agent.ainvoke(initial_state)
        return final_state.get("analysis_result", {})
    except Exception as e:
        logger.error(f"Topology Analysis workflow failed: {e}")
        return {}
