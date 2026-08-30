"""
Detection Agent Service — Phase 2
Deterministic Eligibility Rules Engine + Rule-Based Recoverability Scoring V1.

Objective: Detect recoverable revenue, calculate recoverability score,
assign priority, and persist RecoveryOpportunity + WorkflowState.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.recovery import RecoveryOpportunity
from app.models.workflow import WorkflowState
from app.repositories.audit import AuditLogRepository
from app.repositories.customer import CustomerRepository
from app.repositories.merchant import MerchantRepository
from app.repositories.opportunity import RecoveryOpportunityRepository
from app.repositories.payment_event import PaymentEventRepository
from app.repositories.workflow_state import WorkflowStateRepository
from app.schemas.agents import DetectionInput, DetectionOutput
from app.schemas.customer import CustomerContext
from app.schemas.enums import FailureCause, Priority, WorkflowStatus
from app.schemas.payment_event import PaymentEventRead
from app.schemas.policy import PolicyRead
from app.services.taxonomy import classify_failure_code

logger = get_logger(__name__)

FAILED_STATUSES = {"failed", "payment.failed", "payment_failed"}


class DetectionAgent:
    """Core Detection Agent logic — deterministic rules & V1 scoring."""

    @staticmethod
    def evaluate_eligibility(
        payment_event: PaymentEventRead,
        customer_context: CustomerContext,
        policy: PolicyRead,
    ) -> tuple[bool, str]:
        """Evaluates strict deterministic eligibility rules."""

        if payment_event.status.lower() not in FAILED_STATUSES:
            return False, "Payment status is not failed"

        if not policy.active:
            return False, "Merchant recovery policy is disabled"

        if payment_event.amount <= Decimal("0.00"):
            return False, "Payment amount must be greater than zero"

        if customer_context.risk_score >= 0.90:
            return False, "Customer risk score exceeds max threshold (0.90)"

        if payment_event.failure_category == FailureCause.RISK_REJECTION.value:
            return False, "Payment rejected due to high risk/fraud flag"

        return True, "Passed all deterministic eligibility checks"

    @staticmethod
    def calculate_recoverability_score(
        payment_event: PaymentEventRead,
        customer_context: CustomerContext,
    ) -> float:
        """
        Rule-based recoverability scoring model V1.
        Returns score clamped between 0.050 and 0.990.
        """
        score = 0.0

        # 1. Customer History Weight (0.35 max)
        hist_count = customer_context.historical_payment_count
        succ_count = customer_context.successful_payment_count
        success_rate = (succ_count / hist_count) if hist_count > 0 else 0.5
        score += success_rate * 0.25
        if hist_count >= 3:
            score += 0.10

        # 2. Failure Category Retriability Weight (0.35 max)
        category_weights = {
            FailureCause.TEMPORARY_FAILURE.value: 0.35,
            FailureCause.INSUFFICIENT_FUNDS.value: 0.25,
            FailureCause.PAYMENT_METHOD_FAILURE.value: 0.20,
            FailureCause.EXPIRED_PAYMENT.value: 0.15,
            FailureCause.CUSTOMER_ABANDONMENT.value: 0.15,
            FailureCause.UNKNOWN.value: 0.15,
            FailureCause.RISK_REJECTION.value: 0.05,
        }
        score += category_weights.get(payment_event.failure_category or "", 0.15)

        # 3. Recency & Risk Score Weight (0.20 max)
        if customer_context.risk_score < 0.30:
            score += 0.15
        elif customer_context.risk_score < 0.60:
            score += 0.10

        if customer_context.last_successful_payment:
            days = (datetime.now(tz=timezone.utc) - customer_context.last_successful_payment).days
            if days <= 30:
                score += 0.05

        # 4. Value Calibration Weight (0.10 max)
        if customer_context.average_transaction_value > 0:
            if payment_event.amount >= customer_context.average_transaction_value * Decimal("0.8"):
                score += 0.10

        return round(max(0.050, min(0.990, score)), 3)

    @staticmethod
    def assign_priority(score: float, amount: Decimal) -> Priority:
        """Assigns priority based on recoverability score and transaction value."""
        if score >= 0.70 or (score >= 0.50 and amount >= Decimal("10000.00")):
            return Priority.HIGH
        elif score >= 0.40 or amount >= Decimal("2500.00"):
            return Priority.MEDIUM
        return Priority.LOW

    def run(self, input_data: DetectionInput) -> DetectionOutput:
        """Runs complete detection evaluation."""
        eligible, reason = self.evaluate_eligibility(
            input_data.payment_event,
            input_data.customer_context,
            input_data.merchant_policy,
        )

        if not eligible:
            return DetectionOutput(
                eligible=False,
                recoverability_score=0.0,
                priority=Priority.LOW,
                reason=reason,
            )

        score = self.calculate_recoverability_score(
            input_data.payment_event,
            input_data.customer_context,
        )
        priority = self.assign_priority(score, input_data.payment_event.amount)

        return DetectionOutput(
            eligible=True,
            recoverability_score=score,
            priority=priority,
            reason=reason,
        )


class DetectionService:
    """Service layer connecting DetectionAgent with DB repositories & workflow state."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent = DetectionAgent()
        self.opp_repo = RecoveryOpportunityRepository(db)
        self.wf_repo = WorkflowStateRepository(db)
        self.audit_repo = AuditLogRepository(db)

    async def detect_and_create_opportunity(
        self, input_data: DetectionInput
    ) -> tuple[DetectionOutput, RecoveryOpportunity | None, WorkflowState | None]:
        """
        Runs detection evaluation. If eligible, idempotently creates
        RecoveryOpportunity and WorkflowState in DB with audit trail.
        """
        output = self.agent.run(input_data)
        payment_id = input_data.payment_event.payment_id

        if not output.eligible:
            logger.info(f"message=Detection ineligible | payment_id={payment_id} | reason={output.reason}")
            return output, None, None

        # 1. Create RecoveryOpportunity
        opp_model = RecoveryOpportunity(
            opportunity_id=uuid4(),
            payment_id=payment_id,
            recoverability_score=Decimal(str(output.recoverability_score)),
            expected_revenue=input_data.payment_event.amount,
            priority=output.priority.value,
            status="OPEN",
        )
        opp, opp_created = await self.opp_repo.create_idempotent(opp_model)

        # 2. Create WorkflowState ("recovery-{payment_id}")
        idempotency_key = f"recovery-{payment_id}"
        wf_model = WorkflowState(
            workflow_id=uuid4(),
            opportunity_id=opp.opportunity_id,
            current_state=WorkflowStatus.PENDING.value,
            state_entered_at=datetime.now(tz=timezone.utc),
            idempotency_key=idempotency_key,
            audit_log=[{
                "actor": f"detection_agent:{output.model_version}",
                "action": "DETECTION_COMPLETED",
                "score": output.recoverability_score,
                "priority": output.priority.value,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            }],
        )
        wf, wf_created = await self.wf_repo.create_idempotent(wf_model)

        # 3. Create AuditLog entry
        audit_entry = AuditLog(
            audit_id=uuid4(),
            entity_type="RecoveryOpportunity",
            entity_id=opp.opportunity_id,
            actor=f"detection_agent:{output.model_version}",
            action="OPPORTUNITY_DETECTED",
            input_snapshot=input_data.model_dump(mode="json"),
            output_snapshot=output.model_dump(mode="json"),
            model_version=output.model_version,
            confidence=output.recoverability_score,
            policy_applied=input_data.merchant_policy.model_dump(mode="json"),
            timestamp=datetime.now(tz=timezone.utc),
        )
        await self.audit_repo.create(audit_entry)

        logger.info(
            f"message=Opportunity created | payment_id={payment_id} | opp_id={opp.opportunity_id} "
            f"| score={output.recoverability_score} | priority={output.priority.value}"
        )
        return output, opp, wf
