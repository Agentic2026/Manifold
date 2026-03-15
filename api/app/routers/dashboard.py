import asyncio
import json
from datetime import UTC, datetime
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse
from h4ckath0n.auth import require_user
from h4ckath0n.realtime import sse_response, authenticate_sse_request, AuthError

router = APIRouter(tags=["dashboard"])

class UploadItem(BaseModel):
    id: str
    original_filename: str
    content_type: str
    byte_size: int
    extraction_job_id: Optional[str]
    created_at: str

class JobItem(BaseModel):
    id: str
    kind: str
    status: str
    progress: int
    error: Optional[str]
    created_at: str

@router.get("/uploads", response_model=List[UploadItem])
def get_uploads(user: Any = Depends(require_user)) -> List[UploadItem]:
    # Mock uploads list for dashboard
    return []

@router.post("/uploads", response_model=dict)
def create_upload(file: UploadFile = File(...), user: Any = Depends(require_user)) -> dict:
    # Accept file upload
    return {"status": "ok", "filename": file.filename}

@router.get("/jobs", response_model=List[JobItem])
def get_jobs(user: Any = Depends(require_user)) -> List[JobItem]:
    # Mock jobs list for dashboard
    return []

class ChatRequest(BaseModel):
    message: str
    context: Optional[dict] = None
    thread_id: Optional[str] = None
    history: Optional[list] = None


from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db_session
from app.agents.chat import stream_agent_response

import logging
logger = logging.getLogger(__name__)

@router.post("/llm/chat/stream")
async def chat_stream(request: Request, db: AsyncSession = Depends(get_db_session)) -> Any:
    """Stream an AI security analysis response via SSE.

    Accepts JSON body:
      - message: str
      - context?: {nodeId, nodeName, status}
      - thread_id?: str  (for conversation continuity)
      - history?: [{role, content}, ...]  (recent messages)
    Returns SSE events with {"token": str} data.
    """
    # Auth is optional for the chat endpoint during hackathon demo
    try:
        await authenticate_sse_request(request)
    except (AuthError, Exception):
        pass  # Allow unauthenticated access for demo

    try:
        body = await request.json()
        user_msg = body.get("message", "")
        context = body.get("context")
        thread_id = body.get("thread_id", "default")
        history = body.get("history")
    except Exception:
        user_msg = ""
        context = None
        thread_id = "default"
        history = None

    # Async wrapper to ensure we catch disconnects
    async def generate_response():
        try:
            async for sse_dict in stream_agent_response(
                user_msg, context, db,
                thread_id=thread_id,
                history=history,
            ):
                if await request.is_disconnected():
                    break
                yield sse_dict
        except Exception as e:
            logger.error(f"SSE stream failed: {e}")
            yield {
                "event": "message",
                "data": json.dumps({"token": "\\n\\n**Connection Error:** Stream interrupted."})
            }

    return sse_response(generate_response())
