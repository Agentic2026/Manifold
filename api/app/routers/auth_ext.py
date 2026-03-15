from typing import Any, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from h4ckath0n.auth import require_user

router = APIRouter(prefix="/auth", tags=["auth_ext"])


class SessionResponse(BaseModel):
    user_id: str
    device_id: str
    role: str
    scopes: List[str]
    display_name: Optional[str] = None
    email: Optional[str] = None


@router.get("/session", response_model=SessionResponse)
def get_session(user: Any = Depends(require_user)) -> SessionResponse:
    # Hydrate session for the frontend using the current user object
    # The actual attributes depend on the h4ckath0n user model
    return SessionResponse(
        user_id=getattr(user, "user_id", getattr(user, "id", "unknown")),
        device_id=getattr(user, "device_id", "unknown"),
        role=getattr(user, "role", "user"),
        scopes=getattr(user, "scopes", []),
        display_name=getattr(user, "display_name", None),
        email=getattr(user, "email", None),
    )
