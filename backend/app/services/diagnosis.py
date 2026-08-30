"""
Diagnosis Agent Service — Phase 3
Deterministic failure classification using failure_taxonomy.yaml + customer history.
Target: >90% accuracy on known Razorpay failure codes.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.workflow import WorkflowState
from app.repositories.audit import AuditLogRepository
from app.repositories.opportunity import RecoveryOpportunityRepository
from app.repositories.payment_event import PaymentEventRepository
from app.repositories.workflow_state import WorkflowStateRepository
from app.schemas.agents import CustomerHistory, DiagnosisInput, DiagnosisOutput
from app.schemas.enums import FailureCause, WorkflowStatus
from app.schemas.payment_event import PaymentEventRead
from app.services.customer_history import CustomerHistoryService
from app.services.taxonomy import TaxonomyEntry, classify_failure_code

logger = get_logger(__name__)


class DiagnosisAgent:
    """Core Diagnosis Agent logic — deterministic taxonomy classification & evidence gathering."""

    def diagnose(self, input_data: DiagnosisInput) -> DiagnosisOutput:
        """
        Classifies failure cause using failure_taxonomy.yaml and gathers evidence
        from customer history and payment metadata.
        """
        raw_code = input_data.failure_code or input_data.payment_event.failure_code
        taxonomy: TaxonomyEntry = classify_failure_code(raw_code)

        evidence: list[str] = []

        # 1. Taxonomy Evidence
        if taxonomy.internal_cause == FailureCause.UNKNOWN:
            evidence.append(f"Unmapped Razorpay code '{raw_code}': assigned UNKNOWN taxonomy fallback")
            confidence = 0.30
            fallback_used = True
        else:
            evidence.append(
                f"Taxonomy match: '{raw_code}' -> {taxonomy.internal_cause.value} ({taxonomy.notes})"
            )
            fallback_used = False
            # Confidence calibration
            if taxonomy.internal_cause in {FailureCause.INSUFFICIENT_FUNDS, FailureCause.PAYMENT_METHOD_FAILURE, FailureCause.RISK_REJECTION}:
                confidence = 0.95
            elif taxonomy.internal_cause == FailureCause.TEMPORARY_FAILURE:
                confidence = 0.85
            else:
                confidence = 0.80

        # 2. Customer History Evidence
        ch = input_data.customer_history
        if ch.total_payments > 0:
            rate = round((ch.successful_payments / ch.total_payments) * 100, 1)
            evidence.append(
                f"Customer history: {rate}% success rate ({ch.successful_payments}/{ch.total_payments} successful)"
            )
        else:
            evidence.append("Customer history: New customer (0 prior transactions)")

        if ch.recent_failure_codes:
            evidence.append(f"Recent customer failure codes: {', '.join(ch.recent_failure_codes[:3])}")

        if ch.days_since_last_success is not None:
            evidence.append(f"Days since last successful payment: {ch.days_since_last_success}")

        # 3. Payment Method Evidence
        evidence.append(f"Payment method used: {input_data.payment_event.payment_method}")

        logger.info(
            f"message=Diagnosis completed | code={raw_code} | cause={taxonomy.internal_cause.value} "
            f"| confidence={confidence} | fallback={fallback_used}"
        )

        return DiagnosisOutput(
            cause=taxonomy.internal_cause,
            confidence=confidence,
            evidence=evidence,
            retriable=taxonomy.retriable if taxonomy.retriable is not None else False,
            suggested_wait_minutes=taxonomy.suggested_wait_minutes,
            llm_assisted=taxonomy.llm_assist,
            fallback_used=fallback_used,
            model_version="diagnosis-rules-v1.0",
        )

    def run(self, input_data: DiagnosisInput) -> DiagnosisOutput:
        """Alias for diagnose()."""
        return self.diagnose(input_data)


class DiagnosisService:
    """Service layer connecting DiagnosisAgent with DB repositories & workflow state."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent = DiagnosisAgent()
        self.opp_repo = RecoveryOpportunityRepository(db)
        self.event_repo = PaymentEventRepository(db)
        self.wf_repo = WorkflowStateRepository(db)
        self.audit_repo = AuditLogRepository(db)
        self.history_svc = CustomerHistoryService(db)

    async def diagnose_opportunity(
        self, opportunity_id: UUID
    ) -> tuple[DiagnosisOutput, WorkflowState]:
        """
        Runs failure diagnosis on an opportunity:
        1. Loads opportunity & payment event
        2. Extracts customer history
        3. Invokes DiagnosisAgent
        4. Updates WorkflowState (transitions to DIAGNOSED)
        5. Logs AuditLog record
        """
        opp = await self.opp_repo.get_or_raise(opportunity_id)
        event_model = await self.event_repo.get_by_payment_id(opp.payment_id)
        if not event_model:
            raise NotFoundError(f"PaymentEvent for payment_id '{opp.payment_id}' not found")

        # Convert ORM model to Pydantic schema
        event_schema = PaymentEventRead.model_validate(event_model)

        # Extract customer history
        cust_history = await self.history_svc.get_customer_history(UUID(str(event_model.customer_id)))

        input_data = DiagnosisInput(
            payment_event=event_schema,
            customer_history=cust_history,
            failure_code=event_model.failure_code or "UNKNOWN",
        )

        diagnosis = self.agent.run(input_data)

        # Transition WorkflowState and update Opportunity status
        await self.opp_repo.update_status(opportunity_id, "DIAGNOSED")
        wf = await self.wf_repo.get_by_opportunity_id(opportunity_id)
        if not wf:
            raise NotFoundError(f"WorkflowState for opportunity_id '{opportunity_id}' not found")

        updated_wf = await self.wf_repo.update_state(
            workflow_id=UUID(str(wf.workflow_id)),
            new_state=WorkflowStatus.DIAGNOSED,
            audit_entry={
                "actor": f"diagnosis_agent:{diagnosis.model_version}",
                "action": "DIAGNOSIS_COMPLETED",
                "cause": diagnosis.cause.value,
                "confidence": diagnosis.confidence,
                "retriable": diagnosis.retriable,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

        # Log AuditLog
        audit_entry = AuditLog(
            audit_id=uuid4(),
            entity_type="RecoveryOpportunity",
            entity_id=opportunity_id,
            actor=f"diagnosis_agent:{diagnosis.model_version}",
            action="DIAGNOSIS_COMPLETED",
            input_snapshot=input_data.model_dump(mode="json"),
            output_snapshot=diagnosis.model_dump(mode="json"),
            model_version=diagnosis.model_version,
            confidence=diagnosis.confidence,
            timestamp=datetime.now(tz=timezone.utc),
        )
        await self.audit_repo.create(audit_entry)

        return diagnosis, updated_wf
