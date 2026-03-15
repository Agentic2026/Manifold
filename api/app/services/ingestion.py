from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.telemetry import Machine, Container, ContainerMetricSnapshot
from app.schemas.cadvisor import CadvisorBatchPayloadSchema
from app.services.discovery import reconcile_topology_from_containers


def _resolve_topology_node_id(sample) -> str | None:
    """Deterministically resolve a topology node id from container metadata.

    Priority:
    1. ``com.docker.compose.project`` + ``com.docker.compose.service`` labels
       → ``<project>__<service>`` (project-scoped, avoids collisions)
    2. ``com.docker.compose.service`` label only → bare service name
    3. First alias that is not the reference name
    4. ``None`` – container stays unmatched
    """
    spec = sample.container_spec or {}
    labels = spec.get("labels") or {}

    compose_svc = labels.get("com.docker.compose.service")
    compose_project = labels.get("com.docker.compose.project")

    if compose_svc and compose_project:
        return f"{compose_project}__{compose_svc}"
    if compose_svc:
        return compose_svc

    aliases = sample.container_reference.aliases or []
    ref_name = sample.container_reference.name
    for alias in aliases:
        if alias != ref_name:
            return alias

    return None


async def process_cadvisor_batch(
    payload: CadvisorBatchPayloadSchema, db: AsyncSession
) -> int:
    # 1. UPSERT Machine
    stmt = insert(Machine).values(name=payload.machine_name).on_conflict_do_nothing()
    await db.execute(stmt)

    result = await db.execute(
        select(Machine.id).where(Machine.name == payload.machine_name)
    )
    machine_id = result.scalar()

    if not machine_id:
        return 0

    # Process all containers
    container_values = []
    for sample in payload.samples:
        spec = sample.container_spec or {}
        container_values.append(
            {
                "machine_id": machine_id,
                "reference_name": sample.container_reference.name,
                "aliases": sample.container_reference.aliases or [],
                "namespace": sample.container_reference.namespace,
                "image": spec.get("image"),
                "labels": spec.get("labels", {}),
                "topology_node_id": _resolve_topology_node_id(sample),
            }
        )

    if not container_values:
        return 0

    # 2. UPSERT Containers
    stmt_containers = insert(Container).values(container_values)
    stmt_containers = stmt_containers.on_conflict_do_update(
        index_elements=["reference_name"],
        set_={
            "aliases": stmt_containers.excluded.aliases,
            "namespace": stmt_containers.excluded.namespace,
            "image": stmt_containers.excluded.image,
            "labels": stmt_containers.excluded.labels,
            "topology_node_id": stmt_containers.excluded.topology_node_id,
        },
    ).returning(Container.id, Container.reference_name)

    container_result = await db.execute(stmt_containers)
    container_map = {row.reference_name: row.id for row in container_result}

    # 3. Bulk Insert Snapshots
    snapshot_values = []
    for sample in payload.samples:
        container_id = container_map.get(sample.container_reference.name)
        if not container_id:
            continue

        stats = sample.stats
        try:
            ts_str = stats.get("timestamp")
            if ts_str:
                if ts_str.endswith("Z"):
                    ts_str = ts_str[:-1] + "+00:00"
                ts = datetime.fromisoformat(ts_str)
            else:
                ts = datetime.now(timezone.utc)
        except Exception:
            ts = datetime.now(timezone.utc)

        snapshot_values.append(
            {
                "container_id": container_id,
                "timestamp": ts,
                "cpu_stats": stats.get("cpu", {}),
                "memory_stats": stats.get("memory", {}),
                "network_stats": stats.get("network") or None,
                "filesystem_stats": stats.get("filesystem") or None,
            }
        )

    if snapshot_values:
        stmt_snapshots = insert(ContainerMetricSnapshot).values(snapshot_values)
        await db.execute(stmt_snapshots)

    await db.commit()

    # 4. Auto-discover topology nodes from container metadata
    await reconcile_topology_from_containers(db)

    return len(snapshot_values)
