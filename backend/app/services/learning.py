"""
Learning Agent & Service — Phase 7
Evaluates recovery outcome attribution, updates strategy feedback store,
calculates system recovery metrics (Incremental Net Revenue, ROI %, Recovery Rate %),
and manages opportunity lifecycle finalization.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.recovery import Intervention, RecoveryOpportunity, RecoveryOutcome
from app.models.workflow import WorkflowState
from app.repositories.audit import AuditLogRepository
from app.repositories.decision import RecoveryDecisionRepository
from app.repositories.intervention import InterventionRepository
from app.repositories.opportunity import RecoveryOpportunityRepository
from app.repositories.outcome import RecoveryOutcomeRepository
from app.repositories.workflow_state import WorkflowStateRepository
from app.schemas.agents import LearningInput, LearningOutput
from app.schemas.enums import ActionType, ExperimentGroup, FailureCause, OpportunityStatus, WorkflowStatus
from app.services.attribution import AttributionEngine, AttributionResult
from app.services.strategy import P_SUCCESS_MATRIX

logger = get_logger(__name__)


class LearningAgent:
    """Core Learning Agent — updates strategy feedback loops based on observed outcomes."""

    def update_strategy_feedback(self, action: ActionType, cause: FailureCause, success: bool) -> None:
        """Dynamically adjusts probability matrix based on outcome feedback."""
        if cause in P_SUCCESS_MATRIX and action in P_SUCCESS_MATRIX[cause]:
            current_p = P_SUCCESS_MATRIX[cause][action]
            # Learning rate alpha = 0.05
            target = 1.0 if success else 0.0
            new_p = current_p + 0.05 * (target - current_p)
            P_SUCCESS_MATRIX[cause][action] = round(max(0.01, min(0.95, new_p)), 3)
            logger.info(
                f"message=Strategy feedback updated | cause={cause.value} | action={action.value} "
                f"| old_p={current_p} | new_p={P_SUCCESS_MATRIX[cause][action]}"
            )

    def run(self, input_data: LearningInput) -> LearningOutput:
        return LearningOutput(
            metrics_updated=["incremental_recovery", "recovery_rate", "action_success_rate"],
            model_retrain_triggered=False,
            strategy_adjustment={"status": "feedback_recorded"},
        )


class LearningService:
    """Service layer connecting LearningAgent with DB repositories & metric aggregations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent = LearningAgent()
        self.opp_repo = RecoveryOpportunityRepository(db)
        self.decision_repo = RecoveryDecisionRepository(db)
        self.intervention_repo = InterventionRepository(db)
        self.outcome_repo = RecoveryOutcomeRepository(db)
        self.wf_repo = WorkflowStateRepository(db)
        self.audit_repo = AuditLogRepository(db)

    async def record_opportunity_outcome(
        self,
        opportunity_id: UUID,
        payment_status: str,
        recovered_amount: Decimal | None = None,
        experiment_group: ExperimentGroup = ExperimentGroup.TREATMENT,
    ) -> tuple[AttributionResult, RecoveryOutcome, WorkflowState]:
        """
        Records recovery outcome for an opportunity:
        1. Loads opportunity, decision, and intervention
        2. Evaluates time-window attribution & TREATMENT vs CONTROL incremental lift
        3. Persists RecoveryOutcome ORM record
        4. Updates strategy probability feedback matrix
        5. Updates RecoveryOpportunity & WorkflowState to RECOVERED or FAILED
        6. Writes AuditLog record
        """
        opp_model = await self.opp_repo.get_or_raise(opportunity_id)
        decision_model = await self.decision_repo.get_by_opportunity_id(opportunity_id)
        if not decision_model:
            raise NotFoundError(f"RecoveryDecision for opportunity_id '{opportunity_id}' not found")

        interventions = await self.intervention_repo.get_by_decision_id(UUID(str(decision_model.decision_id)))
        intervention = interventions[0] if interventions else None

        action_type = ActionType(decision_model.selected_action)
        # Derive actual failure cause from the decision's stored reasoning context
        # (we fall back to TEMPORARY_FAILURE only if unavailable, not always)
        cause_str = getattr(decision_model, "failure_cause", None)
        try:
            cause = FailureCause(cause_str) if cause_str else FailureCause.UNKNOWN
        except ValueError:
            cause = FailureCause.UNKNOWN
        amount = recovered_amount if recovered_amount is not None else opp_model.expected_revenue
        now = datetime.now(tz=timezone.utc)
        executed_at = intervention.executed_at if intervention else None

        # Evaluate Attribution
        attrib_res = AttributionEngine.evaluate_attribution(
            payment_status=payment_status,
            amount=amount,
            executed_at=executed_at,
            recorded_at=now,
            action_type=action_type,
            cause=cause,
            experiment_group=experiment_group,
        )

        # Persist RecoveryOutcome ORM record
        outcome_model = RecoveryOutcome(
            outcome_id=uuid4(),
            intervention_id=UUID(str(intervention.intervention_id)) if intervention else None,
            payment_status=payment_status,
            recovered_amount=attrib_res.recovered_amount,
            time_to_recovery=attrib_res.time_to_recovery,
            incremental_recovery=attrib_res.incremental_recovery,
            experiment_group=experiment_group.value,
            recorded_at=now,
        )
        outcome = await self.outcome_repo.create(outcome_model)

        # Update Strategy Store Feedback Loop
        self.agent.update_strategy_feedback(action_type, cause, success=attrib_res.attributed)

        # Update Opportunity & WorkflowState
        is_success = attrib_res.attributed and attrib_res.recovered_amount > Decimal("0.00")
        opp_status = OpportunityStatus.RECOVERED if is_success else OpportunityStatus.FAILED
        new_wf_state = WorkflowStatus.RECOVERED if is_success else WorkflowStatus.FAILED
        action_log = "OUTCOME_RECOVERED" if is_success else "OUTCOME_FAILED"

        await self.opp_repo.update_status(opportunity_id, opp_status.value)

        wf = await self.wf_repo.get_by_opportunity_id(opportunity_id)
        if not wf:
            raise NotFoundError(f"WorkflowState for opportunity_id '{opportunity_id}' not found")

        updated_wf = await self.wf_repo.update_state(
            workflow_id=UUID(str(wf.workflow_id)),
            new_state=new_wf_state,
            audit_entry={
                "actor": f"learning_agent:v1.0",
                "action": action_log,
                "recovered_amount": str(attrib_res.recovered_amount),
                "incremental_recovery": str(attrib_res.incremental_recovery),
                "experiment_group": experiment_group.value,
                "timestamp": now.isoformat(),
            },
        )

        # Log AuditLog
        audit_entry = AuditLog(
            audit_id=uuid4(),
            entity_type="RecoveryOpportunity",
            entity_id=opportunity_id,
            actor="learning_agent:v1.0",
            action=action_log,
            input_snapshot={"payment_status": payment_status, "amount": str(amount), "group": experiment_group.value},
            output_snapshot=attrib_res.model_dump(mode="json"),
            model_version="v1.0",
            confidence=1.0 if is_success else 0.0,
            timestamp=now,
        )
        await self.audit_repo.create(audit_entry)

        return attrib_res, outcome, updated_wf

    async def get_recovery_summary_metrics(self) -> dict:
        """Computes aggregate dashboard KPIs: Recovery Rate, Incremental Net Revenue, ROI %."""
        # Opportunities count
        total_opps = (await self.db.execute(select(func.count(RecoveryOpportunity.opportunity_id)))).scalar() or 0
        recovered_opps = (await self.db.execute(
            select(func.count(RecoveryOpportunity.opportunity_id)).where(RecoveryOpportunity.status == OpportunityStatus.RECOVERED.value)
        )).scalar() or 0

        # Totals
        total_expected = (await self.db.execute(
            select(func.coalesce(func.sum(RecoveryOpportunity.expected_revenue), Decimal("0.00")))
        )).scalar() or Decimal("0.00")

        total_recovered = (await self.db.execute(
            select(func.coalesce(func.sum(RecoveryOutcome.recovered_amount), Decimal("0.00")))
        )).scalar() or Decimal("0.00")

        total_incremental = (await self.db.execute(
            select(func.coalesce(func.sum(RecoveryOutcome.incremental_recovery), Decimal("0.00")))
        )).scalar() or Decimal("0.00")

        total_cost = (await self.db.execute(
            select(func.coalesce(func.sum(Intervention.cost), Decimal("0.00")))
        )).scalar() or Decimal("0.00")

        net_incremental = total_incremental - total_cost
        recovery_rate = (recovered_opps / total_opps * 100.0) if total_opps > 0 else 0.0
        roi_pct = (float(net_incremental) / float(total_cost) * 100.0) if total_cost > 0 else 0.0

        return {
            "total_opportunities": total_opps,
            "recovered_opportunities": recovered_opps,
            "recovery_rate_pct": round(recovery_rate, 2),
            "total_expected_revenue": str(total_expected),
            "total_recovered_amount": str(total_recovered),
            "total_incremental_recovery": str(total_incremental),
            "total_intervention_cost": str(total_cost),
            "net_incremental_revenue": str(net_incremental),
            "roi_pct": round(roi_pct, 2),
        }
