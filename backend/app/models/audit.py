from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import DateTime, Float, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDType, JSONType


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_timestamp", "timestamp"),
    )

    audit_id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=uuid4)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(UUIDType, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)       # "agent_name:version"
    action: Mapped[str] = mapped_column(Text, nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSONType, nullable=False)
    output_snapshot: Mapped[dict] = mapped_column(JSONType, nullable=False)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    policy_applied: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
