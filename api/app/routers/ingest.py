import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

router = APIRouter(tags=["ingest"])
security = HTTPBearer()

def verify_cadvisor_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    # Validate the token against configured secret
    expected_token = os.getenv("CADVISOR_METRICS_API_TOKEN", "my-secret-token")
    if credentials.credentials != expected_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials.credentials

class ContainerReference(BaseModel):
    name: str
    aliases: Optional[List[str]] = None
    namespace: Optional[str] = None

class CadvisorSample(BaseModel):
    container_reference: ContainerReference
    container_spec: Optional[Dict[str, Any]] = None
    stats: Dict[str, Any]

class CadvisorBatchPayload(BaseModel):
    schema_version: str
    sent_at: str
    machine_name: str
    source: Dict[str, str]
    samples: List[CadvisorSample]

@router.post("/cadvisor/batch", status_code=204)
def ingest_cadvisor_batch(
    payload: CadvisorBatchPayload, 
    token: str = Depends(verify_cadvisor_token)
) -> None:
    # In a real scenario, push samples to timeseries DB, Kafka, etc.
    # For now, we accept them successfully.
    pass
