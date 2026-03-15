"""Interactive chat agent — delegates to the evidence-first chat workflow.

Public API is preserved: ``stream_agent_response`` returns an async
generator of SSE-compatible dicts.
"""

import json
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.workflows.chat_workflow import stream_chat_workflow

logger = logging.getLogger(__name__)


async def stream_agent_response(
    user_msg: str,
    context: Dict[str, Any] | None,
    db: AsyncSession,
    thread_id: str = "default",
    history: Optional[List[Dict[str, str]]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream an evidence-first chat response via SSE events.

    Delegates entirely to :func:`stream_chat_workflow` which implements
    the route→gather→synthesize→verify pipeline.
    """
    async for event in stream_chat_workflow(
        user_msg=user_msg,
        context=context,
        db=db,
        thread_id=thread_id,
        history=history,
    ):
        yield event
