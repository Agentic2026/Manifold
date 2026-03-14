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
    user: str

@router.post("/llm/chat/stream")
async def chat_stream(request: Request) -> Any:
    # Simulate an LLM streaming response
    try:
        ctx = await authenticate_sse_request(request)
    except AuthError as exc:
        return JSONResponse({"detail": exc.detail}, status_code=401)
        
    try:
        body = await request.json()
        user_msg = body.get("user", "")
    except Exception:
        user_msg = ""
        
    chunks = [
        "Analyzing your request: ",
        f"'{user_msg}'... ",
        "Scanning internal knowledge base... ",
        "No issues found.",
    ]

    async def generate():  # type: ignore[no-untyped-def]
        for text in chunks:
            if await request.is_disconnected():
                return
            yield {
                "event": "message",
                "data": json.dumps({"token": text})
            }
            await asyncio.sleep(0.3)

    return sse_response(generate())
