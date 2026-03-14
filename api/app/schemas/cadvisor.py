from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class ContainerReferenceSchema(BaseModel):
    name: str
    aliases: Optional[List[str]] = None
    namespace: Optional[str] = None

class CadvisorSampleSchema(BaseModel):
    container_reference: ContainerReferenceSchema
    container_spec: Optional[Dict[str, Any]] = None
    stats: Dict[str, Any]

class CadvisorBatchPayloadSchema(BaseModel):
    schema_version: str
    sent_at: str
    machine_name: str
    source: Dict[str, str]
    samples: List[CadvisorSampleSchema]
