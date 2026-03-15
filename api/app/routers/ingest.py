from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.core.database import get_db_session
from app.core.config import settings
from app.schemas.cadvisor import CadvisorBatchPayloadSchema
from app.services.ingestion import process_cadvisor_batch
from app.models.telemetry import Machine, Container, ContainerMetricSnapshot

router = APIRouter(tags=["ingest"])
security = HTTPBearer()


def verify_cadvisor_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    # Validate the token against configured secret
    expected_token = settings.cadvisor_metrics_api_token
    if credentials.credentials != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    return credentials.credentials


@router.post("/cadvisor/batch", status_code=status.HTTP_202_ACCEPTED)
async def ingest_cadvisor_batch(
    payload: CadvisorBatchPayloadSchema,
    token: str = Depends(verify_cadvisor_token),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    processed_count = await process_cadvisor_batch(payload, db)
    return {"status": "accepted", "samples_processed": processed_count}


@router.get("/ingest/stats")
async def ingest_stats(db: AsyncSession = Depends(get_db_session)) -> dict:
    """Quick readiness / verification endpoint showing ingest counts."""
    machines = (await db.execute(select(func.count(Machine.id)))).scalar() or 0
    containers = (await db.execute(select(func.count(Container.id)))).scalar() or 0
    snapshots = (
        await db.execute(select(func.count(ContainerMetricSnapshot.id)))
    ).scalar() or 0

    latest_ts = (
        await db.execute(
            select(ContainerMetricSnapshot.timestamp)
            .order_by(ContainerMetricSnapshot.timestamp.desc())
            .limit(1)
        )
    ).scalar()

    return {
        "machines": machines,
        "containers": containers,
        "snapshots": snapshots,
        "latest_snapshot_ts": latest_ts.isoformat() if latest_ts else None,
    }
