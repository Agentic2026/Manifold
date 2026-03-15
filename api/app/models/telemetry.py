import datetime
from typing import Any
from sqlalchemy import String, DateTime, func, Index, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

class Machine(Base):
    __tablename__ = "machines"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Container(Base):
    __tablename__ = "containers"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id", ondelete="CASCADE"), index=True)
    reference_name: Mapped[str] = mapped_column(String, unique=True, index=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, server_default='[]')
    namespace: Mapped[str | None] = mapped_column(String, nullable=True)
    image: Mapped[str | None] = mapped_column(String, nullable=True)
    labels: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default='{}')
    # Deterministic mapping to a topology node (compose service name)
    topology_node_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ContainerMetricSnapshot(Base):
    __tablename__ = "container_metric_snapshots"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    cpu_stats: Mapped[dict[str, Any]] = mapped_column(JSONB)
    memory_stats: Mapped[dict[str, Any]] = mapped_column(JSONB)
    network_stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    filesystem_stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

Index("ix_container_metric_snapshots_container_id_timestamp", ContainerMetricSnapshot.container_id, ContainerMetricSnapshot.timestamp)
