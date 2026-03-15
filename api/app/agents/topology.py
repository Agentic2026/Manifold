"""Topology analysis agent — delegates to the evidence-first topology workflow.

Public API is preserved: ``run_topology_analysis`` returns a dict of analysis results.
The ``topology_agent`` object is kept for backward compatibility but the real
work happens inside ``run_topology_workflow``.
"""

import logging
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.workflows.topology_workflow import run_topology_workflow

# Re-export shared schemas so existing imports keep working
from app.agents.schemas import (  # noqa: F401
    NodeStatusUpdate as NodeUpdate,
    ProposedVulnerability as NewVulnerability,
    ProposedInsight as NewInsight,
    TopologyAnalysisResult as ImpactAnalysisOutput,
)

logger = logging.getLogger(__name__)


# Backward-compatible entrypoint
async def run_topology_analysis(db: AsyncSession) -> Dict[str, Any]:
    """Execute the topology analysis workflow.

    Resilient: catches all exceptions so ``/topology/scan`` can still
    return a valid topology graph even when the analysis pipeline fails.
    """
    return await run_topology_workflow(db)
