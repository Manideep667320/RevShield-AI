"""
Strict Pydantic input/output contracts for all agents.
No agent passes raw dicts. All inter-agent communication uses these models.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.enums import ActionType, FailureCause, InterventionStatus, Priority, WorkflowStatus
from app.schemas.customer import CustomerContext
from app.schemas.payment_event import PaymentEventRead
from app.schemas.policy import PolicyRead
from app.schemas.recovery import CandidateAction, RecoveryOpportunityRead
from app.schemas.audit import AuditLogCreate


# ── Agent 1: Detection Agent ───────────────────────────────────────────────

class DetectionInput(BaseModel):
    payment_event: PaymentEventRead
    customer_context: CustomerContext
    merchant_policy: PolicyRead


class DetectionOutput(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    eligible: bool
    recoverability_score: float = Field(0.0, ge=0.0, le=1.0)
    priority: Priority = Priority.LOW
    reason: str = ""
    model_version: str = "detection-rules-v1.0"


# ── Agent 2: Diagnosis Agent ───────────────────────────────────────────────

class CustomerHistory(BaseModel):
    customer_id: UUID
    total_payments: int
    successful_payments: int
    recent_failure_codes: list[str] = Field(default_factory=list)
    days_since_last_success: int | None = None


class DiagnosisInput(BaseModel):
    payment_event: PaymentEventRead
    customer_history: CustomerHistory
    failure_code: str
    context: dict = Field(default_factory=dict)


class DiagnosisOutput(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    cause: FailureCause
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    retriable: bool = False
    suggested_wait_minutes: int | None = None
    llm_assisted: bool = False
    fallback_used: bool = False
    model_version: str = "diagnosis-rules-v1.0"


# ── Agent 3: Recovery Strategy Agent ──────────────────────────────────────

class StrategyInput(BaseModel):
    opportunity: RecoveryOpportunityRead
    diagnosis: DiagnosisOutput
    customer_context: CustomerContext
    policy: PolicyRead
    available_actions: list[ActionType] = Field(
        default_factory=lambda: list(ActionType)
    )


class StrategyOutput(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    candidate_actions: list[CandidateAction]
    selected_action: ActionType
    expected_value: Decimal
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    model_version: str = "strategy-rules-v1.0"


# ── Agent 4: Policy Gateway ────────────────────────────────────────────────

class PolicyRequest(BaseModel):
    strategy: StrategyOutput
    opportunity: RecoveryOpportunityRead
    merchant_policy: PolicyRead
    current_retry_count: int = 0


class PolicyClearance(BaseModel):
    approved: bool
    rejection_reason: str | None = None
    requires_human_approval: bool = False
    approved_action: ActionType | None = None
    policy_version: str
    clearance_token: str = ""     # signed JWT — populated by gateway


# ── Agent 5: Action Agent ──────────────────────────────────────────────────

class ActionRequest(BaseModel):
    opportunity_id: UUID
    action_type: ActionType
    clearance: PolicyClearance
    customer_contact: dict = Field(default_factory=dict)
    payment_details: dict = Field(default_factory=dict)
    idempotency_key: str


class ActionResponse(BaseModel):
    success: bool
    intervention_id: UUID
    external_ref: str | None = None
    status: str
    error_message: str | None = None
    executed_at: datetime


class ActionInput(BaseModel):
    clearance: PolicyClearance
    strategy: StrategyOutput
    opportunity: RecoveryOpportunityRead
    customer_context: CustomerContext


class ActionResult(BaseModel):
    intervention_id: UUID
    status: InterventionStatus
    external_ref: str | None = None
    executed_at: str             # ISO datetime string
    audit_event: AuditLogCreate
    error: str | None = None


# ── Agent 6: Learning Agent ────────────────────────────────────────────────

class LearningInput(BaseModel):
    decision_id: UUID
    intervention_id: UUID
    outcome_id: UUID
    experiment_group: str    # TREATMENT | CONTROL


class LearningOutput(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    metrics_updated: list[str]
    model_retrain_triggered: bool = False
    strategy_adjustment: dict | None = None


# ── Orchestrator I/O ───────────────────────────────────────────────────────

class RecoveryWorkflowInput(BaseModel):
    payment_event_id: UUID
    payment_id: str
    merchant_id: UUID
    customer_id: UUID


class WorkflowResult(BaseModel):
    workflow_id: str
    status: WorkflowStatus
    recovered_amount: Decimal = Decimal("0.00")
    action_taken: ActionType | None = None
    reasoning: str = ""
