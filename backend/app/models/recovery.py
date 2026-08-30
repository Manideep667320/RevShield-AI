from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, Interval, Numeric, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDType, JSONType


class RecoveryOpportunity(Base, TimestampMixin):
    __tablename__ = "recovery_opportunities"
    __table_args__ = (
        Index("ix_recovery_opportunities_payment_id", "payment_id"),
        Index("ix_recovery_opportunities_status", "status"),
    )

    opportunity_id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=uuid4)
    payment_id: Mapped[str] = mapped_column(Text, nullable=False)
    recoverability_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.000"))
    expected_revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    priority: Mapped[str] = mapped_column(Text, default="LOW")
    status: Mapped[str] = mapped_column(Text, default="OPEN")

    decisions: Mapped[list["RecoveryDecision"]] = relationship(back_populates="opportunity")
    workflow_states: Mapped[list["WorkflowState"]] = relationship(back_populates="opportunity")


class RecoveryDecision(Base, TimestampMixin):
    __tablename__ = "recovery_decisions"

    decision_id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=uuid4)
    opportunity_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("recovery_opportunities.opportunity_id"))
    candidate_actions: Mapped[list] = mapped_column(JSONType, default=list)
    selected_action: Mapped[str] = mapped_column(Text, nullable=False)
    expected_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.000"))
    reasoning: Mapped[str] = mapped_column(Text, default="")
    model_version: Mapped[str] = mapped_column(Text, default="rules-v1.0")

    opportunity: Mapped["RecoveryOpportunity"] = relationship(back_populates="decisions")
    interventions: Mapped[list["Intervention"]] = relationship(back_populates="decision")


class Intervention(Base):
    __tablename__ = "interventions"

    intervention_id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=uuid4)
    decision_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("recovery_decisions.decision_id"))
    type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="PENDING")
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    external_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    decision: Mapped["RecoveryDecision"] = relationship(back_populates="interventions")
    outcomes: Mapped[list["RecoveryOutcome"]] = relationship(back_populates="intervention")


class RecoveryOutcome(Base):
    __tablename__ = "recovery_outcomes"

    outcome_id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=uuid4)
    intervention_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("interventions.intervention_id"))
    payment_status: Mapped[str] = mapped_column(Text, nullable=False)
    recovered_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    time_to_recovery: Mapped[str | None] = mapped_column(Interval, nullable=True)
    incremental_recovery: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    experiment_group: Mapped[str] = mapped_column(Text, default="TREATMENT")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    intervention: Mapped["Intervention"] = relationship(back_populates="outcomes")
