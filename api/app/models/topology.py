from datetime import datetime
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
)
from app.core.database import Base


class TopologyNode(Base):
    """
    SQLAlchemy model storing a DAG node representing a service in the architecture.
    """

    __tablename__ = "topology_nodes"

    id = Column(String, primary_key=True, index=True)
    label = Column(String, nullable=False)
    service_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False)  # e.g., "healthy", "warning", "compromised"
    type = Column(
        String, nullable=False
    )  # e.g., "gateway", "frontend", "service", "api", "agent", "database"
    position = Column(JSON, nullable=False)  # {"x": ..., "y": ...}
    description = Column(String, nullable=True)

    # Telemetry and analysis are stored as JSONB in Postgres for flexibility
    telemetry = Column(JSON, nullable=True)
    analysis = Column(JSON, nullable=True)


class TopologyEdge(Base):
    """
    SQLAlchemy model storing a directional edge in the DAG linking two DAG nodes.
    """

    __tablename__ = "topology_edges"

    id = Column(String, primary_key=True, index=True)
    source_id = Column(
        String,
        ForeignKey("topology_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_id = Column(
        String,
        ForeignKey("topology_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind = Column(String, nullable=False)  # e.g., "network", "api"
    label = Column(String, nullable=False)
    animated = Column(Boolean, default=False)


class Vulnerability(Base):
    """
    SQLAlchemy model storing identified security vulnerabilities.
    """

    __tablename__ = "vulnerabilities"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    severity = Column(
        String, nullable=False
    )  # e.g., "critical", "high", "medium", "low"
    affected_node_id = Column(
        String,
        ForeignKey("topology_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description = Column(String, nullable=False)
    discovered_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    status = Column(String, nullable=False)  # e.g., "open", "in-progress", "resolved"
    cve = Column(String, nullable=True)


class LLMInsight(Base):
    """
    SQLAlchemy model storing LLM-generated security insights.
    """

    __tablename__ = "llm_insights"

    id = Column(String, primary_key=True, index=True)
    node_id = Column(
        String,
        ForeignKey("topology_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type = Column(String, nullable=False)  # e.g., "anomaly", "threat", "info"
    summary = Column(String, nullable=False)
    details = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)
    confidence = Column(Float, nullable=False)  # e.g., 0.0 to 1.0


class RBACPolicy(Base):
    """
    SQLAlchemy model representing an RBAC policy binding for nodes in the infrastructure.
    """

    __tablename__ = "rbac_policies"

    id = Column(String, primary_key=True, index=True)
    role = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    permissions = Column(JSON, nullable=False)  # List[str]
    scope = Column(String, nullable=False)
    last_modified = Column(DateTime(timezone=True), default=datetime.utcnow)
    risk_level = Column(String, nullable=False)  # e.g., "low", "medium", "high"


class SecurityReport(Base):
    """
    Persisted deep-scan and security-posture reports.

    Each /topology/scan invocation produces exactly two report rows:
    one ``deep_scan`` and one ``security_posture``.  Even when nothing
    materially changed, a report is stored with a stable fingerprint so
    unchanged runs can be recognised.
    """

    __tablename__ = "security_reports"

    id = Column(String, primary_key=True, index=True)
    report_kind = Column(String, nullable=False)  # "deep_scan" | "security_posture"
    title = Column(String, nullable=False)
    summary = Column(String, nullable=False)
    details_markdown = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    max_status = Column(String, nullable=False)  # "healthy" | "warning" | "compromised"
    fingerprint = Column(String, nullable=False)  # stable hash of meaningful scan state
    trigger = Column(String, nullable=False, default="manual")  # "manual" | "scheduled" | "api"
    payload = Column(JSON, nullable=True)  # arbitrary structured metadata
