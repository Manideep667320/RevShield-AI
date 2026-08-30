from datetime import datetime
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, UUIDType, JSONType


class WorkflowState(Base):
    __tablename__ = "workflow_states"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_workflow_idempotency"),)

    workflow_id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=uuid4)
    opportunity_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("recovery_opportunities.opportunity_id"))
    temporal_run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_state: Mapped[str] = mapped_column(Text, default="PENDING")
    state_entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timeout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)   # "recovery-{payment_id}"
    audit_log: Mapped[list] = mapped_column(JSONType, default=list)

    opportunity: Mapped["RecoveryOpportunity"] = relationship(back_populates="workflow_states")
