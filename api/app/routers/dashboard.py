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


# Context-aware mock responses for security analysis
_CHAT_RESPONSES: dict = {
    "compromised": (
        "**CRITICAL: Node Compromise Detected**\n\n"
        "This entity is actively compromised. Analysis shows:\n\n"
        "- **Attack Vector**: Prompt injection via malicious PDF documents uploaded through the ingestion endpoint\n"
        "- **Impact**: The agent is executing attacker-controlled instructions, bypassing content policy filters via role-play jailbreak\n"
        "- **Exfiltration**: Anomalous tool call volume at 412 calls/min (baseline: 18). Outbound data transfer 3.8x above normal\n\n"
        "**Immediate Remediation Steps**:\n"
        "1. Isolate this entity to block all network traffic\n"
        "2. Revoke all RBAC role bindings\n"
        "3. Preserve tool call logs for forensic analysis\n"
        "4. Redeploy with input sanitization middleware"
    ),
    "warning": (
        "**WARNING: Anomalous Behavior Detected**\n\n"
        "This node shows concerning patterns that warrant investigation:\n\n"
        "- Traffic patterns deviate from 7-day baseline by 2x\n"
        "- Potential downstream impact from compromised upstream services\n"
        "- RBAC policies may need tightening\n\n"
        "**Recommendations**:\n"
        "1. Monitor egress traffic closely\n"
        "2. Review and rotate credentials\n"
        "3. Enable query-level audit logging"
    ),
    "healthy": (
        "**Node Status: Healthy**\n\n"
        "This entity is operating within normal parameters.\n\n"
        "- All telemetry metrics within expected ranges\n"
        "- No anomalous traffic patterns detected\n"
        "- RBAC policies are correctly scoped\n\n"
        "No immediate action required. Consider scheduling routine credential rotation."
    ),
    "default": (
        "**Security Analysis Complete**\n\n"
        "Based on the current system topology, I've identified the following:\n\n"
        "1. **Active Threat**: The Context Agent (LLM-AGENT) shows signs of prompt injection compromise. "
        "Egress traffic is 3.8x above baseline.\n\n"
        "2. **Lateral Movement Risk**: The compromised agent has active MCP bridge access to the Core API Hub, "
        "creating a potential exfiltration channel.\n\n"
        "3. **Recommended Actions**:\n"
        "   - Isolate the Context Agent immediately\n"
        "   - Revoke `vector_read_role` and `mcp_bridge_role`\n"
        "   - Audit all tool call logs from the last 6 hours\n"
        "   - Deploy input sanitization middleware before restoring service"
    ),
}


@router.post("/llm/chat/stream")
async def chat_stream(request: Request) -> Any:
    """Stream an AI security analysis response via SSE.

    Accepts JSON body: {"message": str, "context"?: {"nodeId": str, "nodeName": str, "status": str}}
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
    except Exception:
        user_msg = ""
        context = None

    # Pick response based on context status
    status = context.get("status", "default") if context else "default"
    response_text = _CHAT_RESPONSES.get(status, _CHAT_RESPONSES["default"])

    # Stream token by token (simulating LLM output)
    async def generate():  # type: ignore[no-untyped-def]
        # Stream in chunks of ~3 characters for realistic feel
        i = 0
        while i < len(response_text):
            if await request.is_disconnected():
                return
            chunk = response_text[i : i + 3]
            yield {
                "event": "message",
                "data": json.dumps({"token": chunk}),
            }
            i += 3
            await asyncio.sleep(0.015)

    return sse_response(generate())
