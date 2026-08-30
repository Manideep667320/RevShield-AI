"""
Recovery Strategy Engine Service — Phase 4
Mathematically defensible action selection based on Expected Net Recovery formula:
  E[Net Recovery] = P(success | action, cause, context) * Revenue - Cost(action) - ChurnPenalty(action)
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.models.recovery import RecoveryDecision
from app.models.workflow import WorkflowState
from app.repositories.audit import AuditLogRepository
from app.repositories.customer import CustomerRepository
from app.repositories.decision import RecoveryDecisionRepository
from app.repositories.merchant import MerchantRepository
from app.repositories.opportunity import RecoveryOpportunityRepository
from app.repositories.payment_event import PaymentEventRepository
from app.repositories.workflow_state import WorkflowStateRepository
from app.schemas.agents import DiagnosisInput, StrategyInput, StrategyOutput
from app.schemas.customer import CustomerContext
from app.schemas.enums import ActionType, FailureCause, WorkflowStatus
from app.schemas.payment_event import PaymentEventRead
from app.schemas.policy import PolicyRead
from app.schemas.recovery import CandidateAction, RecoveryOpportunityRead
from app.services.customer_history import CustomerHistoryService
from app.services.diagnosis import DiagnosisAgent

logger = get_logger(__name__)

# Action Costs (INR)
ACTION_COSTS: dict[ActionType, Decimal] = {
    ActionType.RETRY: Decimal("0.00"),
    ActionType.PAYMENT_LINK: Decimal("2.00"),
    ActionType.REMINDER: Decimal("0.50"),
    ActionType.NO_ACTION: Decimal("0.00"),
    ActionType.HUMAN_ESCALATION: Decimal("50.00"),
}

# Action Churn Friction Penalties (INR)
ACTION_CHURN_PENALTIES: dict[ActionType, Decimal] = {
    ActionType.RETRY: Decimal("0.00"),
    ActionType.PAYMENT_LINK: Decimal("1.00"),
    ActionType.REMINDER: Decimal("0.50"),
    ActionType.NO_ACTION: Decimal("0.00"),
    ActionType.HUMAN_ESCALATION: Decimal("10.00"),
}

# Base Probability Table: P(success | action_type, failure_cause)
P_SUCCESS_MATRIX: dict[FailureCause, dict[ActionType, float]] = {
    FailureCause.TEMPORARY_FAILURE: {
        ActionType.RETRY: 0.75,
        ActionType.PAYMENT_LINK: 0.45,
        ActionType.REMINDER: 0.20,
        ActionType.HUMAN_ESCALATION: 0.70,
        ActionType.NO_ACTION: 0.05,
    },
    FailureCause.INSUFFICIENT_FUNDS: {
        ActionType.PAYMENT_LINK: 0.65,
        ActionType.REMINDER: 0.45,
        ActionType.RETRY: 0.25,
        ActionType.HUMAN_ESCALATION: 0.50,
        ActionType.NO_ACTION: 0.05,
    },
    FailureCause.PAYMENT_METHOD_FAILURE: {
        ActionType.PAYMENT_LINK: 0.75,
        ActionType.REMINDER: 0.35,
        ActionType.RETRY: 0.05,
        ActionType.HUMAN_ESCALATION: 0.50,
        ActionType.NO_ACTION: 0.02,
    },
    FailureCause.EXPIRED_PAYMENT: {
        ActionType.PAYMENT_LINK: 0.70,
        ActionType.REMINDER: 0.25,
        ActionType.RETRY: 0.10,
        ActionType.HUMAN_ESCALATION: 0.40,
        ActionType.NO_ACTION: 0.01,
    },
    FailureCause.CUSTOMER_ABANDONMENT: {
        ActionType.PAYMENT_LINK: 0.55,
        ActionType.REMINDER: 0.50,
        ActionType.RETRY: 0.10,
        ActionType.HUMAN_ESCALATION: 0.40,
        ActionType.NO_ACTION: 0.05,
    },
    FailureCause.RISK_REJECTION: {
        ActionType.HUMAN_ESCALATION: 0.40,
        ActionType.NO_ACTION: 0.00,
        ActionType.RETRY: 0.00,
        ActionType.PAYMENT_LINK: 0.00,
        ActionType.REMINDER: 0.00,
    },
    FailureCause.UNKNOWN: {
        ActionType.PAYMENT_LINK: 0.35,
        ActionType.REMINDER: 0.25,
        ActionType.RETRY: 0.20,
        ActionType.HUMAN_ESCALATION: 0.30,
        ActionType.NO_ACTION: 0.05,
    },
}


class StrategyAgent:
    """Core Strategy Agent logic — expected net recovery formula & candidate action ranking."""

    @staticmethod
    def calculate_expected_net_recovery(
        p_success: float, revenue: Decimal, cost: Decimal, churn_penalty: Decimal
    ) -> Decimal:
        """
        Formula: E[Net Recovery] = p_success * revenue - cost - churn_penalty
        """
        raw_val = (Decimal(str(p_success)) * revenue) - cost - churn_penalty
        return raw_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def estimate_p_success(
        action: ActionType,
        cause: FailureCause,
        customer_context: CustomerContext,
        diagnosis_confidence: float,
    ) -> float:
        """Estimates P(success | action, cause, context)."""
        cause_matrix = P_SUCCESS_MATRIX.get(cause, P_SUCCESS_MATRIX[FailureCause.UNKNOWN])
        base_p = cause_matrix.get(action, 0.05)

        # Scale by diagnosis confidence
        p = base_p * (0.5 + 0.5 * diagnosis_confidence)

        # Bonus for high-history reliable customers
        if customer_context.successful_payment_count >= 3:
            p += 0.05

        return round(max(0.00, min(0.95, p)), 3)

    def evaluate_strategy(self, input_data: StrategyInput) -> StrategyOutput:
        """Generates candidate actions, ranks by expected net recovery, and selects top strategy."""
        cause = input_data.diagnosis.cause
        revenue = input_data.opportunity.expected_revenue
        candidates: list[CandidateAction] = []

        for action in input_data.available_actions:
            cost = ACTION_COSTS.get(action, Decimal("0.00"))
            penalty = ACTION_CHURN_PENALTIES.get(action, Decimal("0.00"))
            p_succ = self.estimate_p_success(
                action, cause, input_data.customer_context, input_data.diagnosis.confidence
            )
            ev = self.calculate_expected_net_recovery(p_succ, revenue, cost, penalty)
            action_conf = round(input_data.diagnosis.confidence * (0.8 if action == ActionType.NO_ACTION else 1.0), 3)

            candidates.append(
                CandidateAction(
                    action=action,
                    p_success=p_succ,
                    expected_value=ev,
                    cost=cost,
                    confidence=action_conf,
                )
            )

        # Sort candidate actions by expected_value descending
        candidates.sort(key=lambda c: c.expected_value, reverse=True)
        top_candidate = candidates[0]

        # Build decision reasoning
        runner_up = candidates[1] if len(candidates) > 1 else None
        reasoning = (
            f"Selected {top_candidate.action.value} for {cause.value} failure "
            f"with expected net recovery ₹{top_candidate.expected_value} (P(success)={top_candidate.p_success*100:.1f}%). "
        )
        if runner_up:
            reasoning += (
                f"Ranked over {runner_up.action.value} (expected net recovery ₹{runner_up.expected_value}, "
                f"P(success)={runner_up.p_success*100:.1f}%)."
            )

        logger.info(
            f"message=Strategy selected | opp_id={input_data.opportunity.opportunity_id} "
            f"| selected={top_candidate.action.value} | expected_value=₹{top_candidate.expected_value}"
        )

        return StrategyOutput(
            candidate_actions=candidates,
            selected_action=top_candidate.action,
            expected_value=top_candidate.expected_value,
            confidence=top_candidate.confidence,
            reasoning=reasoning,
            model_version="strategy-rules-v1.0",
        )

    def run(self, input_data: StrategyInput) -> StrategyOutput:
        """Alias for evaluate_strategy()."""
        return self.evaluate_strategy(input_data)


class StrategyService:
    """Service layer connecting StrategyAgent with DB repositories & workflow state."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent = StrategyAgent()
        self.opp_repo = RecoveryOpportunityRepository(db)
        self.decision_repo = RecoveryDecisionRepository(db)
        self.event_repo = PaymentEventRepository(db)
        self.customer_repo = CustomerRepository(db)
        self.merchant_repo = MerchantRepository(db)
        self.wf_repo = WorkflowStateRepository(db)
        self.audit_repo = AuditLogRepository(db)
        self.history_svc = CustomerHistoryService(db)

    async def select_strategy_for_opportunity(
        self, opportunity_id: UUID
    ) -> tuple[StrategyOutput, RecoveryDecision, WorkflowState]:
        """
        Runs strategy selection for a diagnosed opportunity:
        1. Loads opportunity, merchant policy, customer context, and diagnosis result
        2. Invokes StrategyAgent
        3. Persists RecoveryDecision ORM record
        4. Transitions WorkflowState to STRATEGY_SELECTED
        5. Logs AuditLog record
        """
        opp_model = await self.opp_repo.get_or_raise(opportunity_id)
        event_model = await self.event_repo.get_by_payment_id(opp_model.payment_id)
        if not event_model:
            raise NotFoundError(f"PaymentEvent for payment_id '{opp_model.payment_id}' not found")

        merchant_model = await self.merchant_repo.get(UUID(str(event_model.merchant_id)))
        customer_model = await self.customer_repo.get(UUID(str(event_model.customer_id)))

        # Build CustomerContext
        cust_context = CustomerContext(
            customer_id=UUID(str(event_model.customer_id)),
            historical_payment_count=customer_model.historical_payment_count if customer_model else 0,
            successful_payment_count=customer_model.successful_payment_count if customer_model else 0,
            average_transaction_value=customer_model.average_transaction_value if customer_model else Decimal("0.00"),
            risk_score=customer_model.risk_score if customer_model else 0.5,
            last_successful_payment=customer_model.last_successful_payment if customer_model else None,
        )

        # Build PolicyRead
        policy = PolicyRead(
            policy_id=uuid4(),
            merchant_id=UUID(str(event_model.merchant_id)),
            max_retry_count=merchant_model.recovery_policy.get("max_retry_count", 2) if merchant_model and merchant_model.recovery_policy else 2,
            max_discount_pct=Decimal(str(merchant_model.recovery_policy.get("max_discount_pct", "5.00"))) if merchant_model and merchant_model.recovery_policy else Decimal("5.00"),
            allowed_channels=merchant_model.recovery_policy.get("allowed_channels", ["RETRY", "PAYMENT_LINK", "REMINDER"]) if merchant_model and merchant_model.recovery_policy else ["RETRY", "PAYMENT_LINK", "REMINDER"],
            approval_threshold=Decimal(str(merchant_model.recovery_policy.get("approval_threshold", "25000.00"))) if merchant_model and merchant_model.recovery_policy else Decimal("25000.00"),
            max_intervention_cost=Decimal("50.00"),
            active=True,
            version=1,
        )

        # Run Diagnosis Agent
        event_schema = PaymentEventRead.model_validate(event_model)
        cust_history = await self.history_svc.get_customer_history(UUID(str(event_model.customer_id)))
        diagnosis_input = DiagnosisInput(
            payment_event=event_schema,
            customer_history=cust_history,
            failure_code=event_model.failure_code or "UNKNOWN",
        )
        diagnosis_output = DiagnosisAgent().run(diagnosis_input)

        opp_schema = RecoveryOpportunityRead.model_validate(opp_model)
        strategy_input = StrategyInput(
            opportunity=opp_schema,
            diagnosis=diagnosis_output,
            customer_context=cust_context,
            policy=policy,
        )

        strategy_output = self.agent.run(strategy_input)

        # Persist RecoveryDecision record
        decision_model = RecoveryDecision(
            decision_id=uuid4(),
            opportunity_id=opportunity_id,
            candidate_actions=[ca.model_dump(mode="json") for ca in strategy_output.candidate_actions],
            selected_action=strategy_output.selected_action.value,
            expected_value=strategy_output.expected_value,
            confidence=Decimal(str(strategy_output.confidence)),
            reasoning=strategy_output.reasoning,
            model_version=strategy_output.model_version,
        )
        decision = await self.decision_repo.create(decision_model)

        # Transition WorkflowState and update Opportunity status
        await self.opp_repo.update_status(opportunity_id, "STRATEGY_SELECTED")
        wf = await self.wf_repo.get_by_opportunity_id(opportunity_id)
        if not wf:
            raise NotFoundError(f"WorkflowState for opportunity_id '{opportunity_id}' not found")

        updated_wf = await self.wf_repo.update_state(
            workflow_id=UUID(str(wf.workflow_id)),
            new_state=WorkflowStatus.STRATEGY_SELECTED,
            audit_entry={
                "actor": f"strategy_agent:{strategy_output.model_version}",
                "action": "STRATEGY_SELECTED",
                "selected_action": strategy_output.selected_action.value,
                "expected_value": str(strategy_output.expected_value),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

        # Log AuditLog
        audit_entry = AuditLog(
            audit_id=uuid4(),
            entity_type="RecoveryOpportunity",
            entity_id=opportunity_id,
            actor=f"strategy_agent:{strategy_output.model_version}",
            action="STRATEGY_SELECTED",
            input_snapshot=strategy_input.model_dump(mode="json"),
            output_snapshot=strategy_output.model_dump(mode="json"),
            model_version=strategy_output.model_version,
            confidence=strategy_output.confidence,
            timestamp=datetime.now(tz=timezone.utc),
        )
        await self.audit_repo.create(audit_entry)

        return strategy_output, decision, updated_wf
