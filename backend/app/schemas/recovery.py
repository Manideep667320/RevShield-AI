from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.enums import (
    ActionType, ExperimentGroup, InterventionStatus, OpportunityStatus, Priority
)


# ── Recovery Opportunity ───────────────────────────────────────────────────

class RecoveryOpportunityCreate(BaseModel):
    payment_id: str
    recoverability_score: float = Field(..., ge=0.0, le=1.0)
    expected_revenue: Decimal
    priority: Priority
    status: OpportunityStatus = OpportunityStatus.OPEN


class RecoveryOpportunityRead(RecoveryOpportunityCreate):
    opportunity_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Recovery Decision ──────────────────────────────────────────────────────

class CandidateAction(BaseModel):
    action: ActionType
    p_success: float = Field(..., ge=0.0, le=1.0)
    expected_value: Decimal
    cost: Decimal
    confidence: float = Field(..., ge=0.0, le=1.0)


class RecoveryDecisionCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    opportunity_id: UUID
    candidate_actions: list[CandidateAction]
    selected_action: ActionType
    expected_value: Decimal
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    model_version: str = "rules-v1.0"


class RecoveryDecisionRead(RecoveryDecisionCreate):
    decision_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


# ── Intervention ───────────────────────────────────────────────────────────

class InterventionCreate(BaseModel):
    decision_id: UUID
    type: ActionType
    cost: Decimal = Decimal("0.00")
    external_ref: str | None = None


class InterventionRead(InterventionCreate):
    intervention_id: UUID
    status: InterventionStatus
    executed_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Recovery Outcome ───────────────────────────────────────────────────────

class RecoveryOutcomeCreate(BaseModel):
    intervention_id: UUID
    payment_status: str
    recovered_amount: Decimal = Decimal("0.00")
    time_to_recovery: timedelta | None = None
    incremental_recovery: Decimal = Decimal("0.00")
    experiment_group: ExperimentGroup = ExperimentGroup.TREATMENT


class RecoveryOutcomeRead(RecoveryOutcomeCreate):
    outcome_id: UUID
    recorded_at: datetime

    model_config = {"from_attributes": True}
