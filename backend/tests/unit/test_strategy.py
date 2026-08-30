"""
Unit & Service tests for Phase 4 — Recovery Strategy Engine.
Tests Expected Net Recovery formula, candidate action ranking, cause-specific strategy selection,
and DB persistence (RecoveryDecision + WorkflowState + AuditLog).
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from app.models.customer import Customer
from app.models.merchant import Merchant
from app.models.payment_event import PaymentEvent
from app.models.recovery import RecoveryOpportunity
from app.models.workflow import WorkflowState
from app.schemas.agents import DiagnosisOutput, StrategyInput
from app.schemas.customer import CustomerContext
from app.schemas.enums import ActionType, FailureCause, Priority, WorkflowStatus
from app.schemas.policy import PolicyRead
from app.schemas.recovery import RecoveryOpportunityRead
from app.services.strategy import StrategyAgent, StrategyService


@pytest.fixture
def sample_strategy_input():
    merchant_id = uuid4()
    customer_id = uuid4()
    opp_id = uuid4()

    opp = RecoveryOpportunityRead(
        opportunity_id=opp_id,
        payment_id=f"pay_{uuid4().hex[:16]}",
        recoverability_score=0.75,
        expected_revenue=Decimal("2000.00"),
        priority=Priority.HIGH,
        status="OPEN",
        created_at=datetime.now(tz=timezone.utc),
    )

    diagnosis = DiagnosisOutput(
        cause=FailureCause.TEMPORARY_FAILURE,
        confidence=0.85,
        evidence=["Taxonomy match: GATEWAY_ERROR"],
        retriable=True,
        suggested_wait_minutes=30,
        llm_assisted=False,
        fallback_used=False,
    )

    customer = CustomerContext(
        customer_id=customer_id,
        historical_payment_count=5,
        successful_payment_count=4,
        average_transaction_value=Decimal("1500.00"),
        risk_score=0.20,
    )

    policy = PolicyRead(
        policy_id=uuid4(),
        merchant_id=merchant_id,
        max_retry_count=2,
        max_discount_pct=Decimal("5.00"),
        allowed_channels=["RETRY", "PAYMENT_LINK", "REMINDER"],
        approval_threshold=Decimal("25000.00"),
        max_intervention_cost=Decimal("50.00"),
        active=True,
        version=1,
    )

    return StrategyInput(
        opportunity=opp,
        diagnosis=diagnosis,
        customer_context=customer,
        policy=policy,
    )


class TestStrategyAgentUnit:

    def test_expected_net_recovery_formula(self):
        # E[Net Recovery] = 0.75 * 2000 - 2.00 - 1.00 = 1500.00 - 3.00 = 1497.00
        ev = StrategyAgent.calculate_expected_net_recovery(
            p_success=0.75,
            revenue=Decimal("2000.00"),
            cost=Decimal("2.00"),
            churn_penalty=Decimal("1.00"),
        )
        assert ev == Decimal("1497.00")

    def test_candidate_actions_ranking(self, sample_strategy_input):
        agent = StrategyAgent()
        out = agent.evaluate_strategy(sample_strategy_input)

        assert len(out.candidate_actions) == 5
        # Verify sorted descending by expected_value
        evs = [ca.expected_value for ca in out.candidate_actions]
        assert evs == sorted(evs, reverse=True)
        assert out.selected_action == out.candidate_actions[0].action
        assert "Selected" in out.reasoning

    def test_temporary_failure_prefers_retry(self, sample_strategy_input):
        agent = StrategyAgent()
        out = agent.evaluate_strategy(sample_strategy_input)
        # For TEMPORARY_FAILURE with 0 cost, RETRY should yield highest expected value
        assert out.selected_action == ActionType.RETRY

    def test_insufficient_funds_prefers_payment_link(self, sample_strategy_input):
        diag_insuff = sample_strategy_input.diagnosis.model_copy(update={"cause": FailureCause.INSUFFICIENT_FUNDS})
        inp = sample_strategy_input.model_copy(update={"diagnosis": diag_insuff})
        agent = StrategyAgent()
        out = agent.evaluate_strategy(inp)
        # For INSUFFICIENT_FUNDS, PAYMENT_LINK provides time/alternate method -> higher EV than RETRY
        assert out.selected_action == ActionType.PAYMENT_LINK

    def test_card_expired_prefers_payment_link(self, sample_strategy_input):
        diag_expired = sample_strategy_input.diagnosis.model_copy(update={"cause": FailureCause.PAYMENT_METHOD_FAILURE})
        inp = sample_strategy_input.model_copy(update={"diagnosis": diag_expired})
        agent = StrategyAgent()
        out = agent.evaluate_strategy(inp)
        # For PAYMENT_METHOD_FAILURE, RETRY has ~0.05 p_success -> PAYMENT_LINK selected
        assert out.selected_action == ActionType.PAYMENT_LINK


class TestStrategyServiceIntegration:

    @pytest.mark.asyncio
    async def test_select_strategy_opportunity_pipeline(self, db):
        merchant = Merchant(
            merchant_id=uuid4(),
            name="Strategy Test Merchant",
            recovery_policy={"max_retry_count": 2, "approval_threshold": 25000},
        )
        customer = Customer(
            customer_id=uuid4(),
            merchant_id=merchant.merchant_id,
            historical_payment_count=5,
            successful_payment_count=4,
        )
        db.add_all([merchant, customer])
        await db.flush()

        payment_id = f"pay_{uuid4().hex[:16]}"
        event = PaymentEvent(
            event_id=uuid4(),
            merchant_id=str(merchant.merchant_id),
            customer_id=str(customer.customer_id),
            payment_id=payment_id,
            amount=Decimal("3000.00"),
            currency="INR",
            payment_method="CARD",
            status="failed",
            failure_code="GATEWAY_ERROR",
            failure_category=FailureCause.TEMPORARY_FAILURE.value,
            timestamp=datetime.now(tz=timezone.utc),
            metadata_={},
        )
        db.add(event)
        await db.flush()

        opp = RecoveryOpportunity(
            opportunity_id=uuid4(),
            payment_id=payment_id,
            recoverability_score=Decimal("0.80"),
            expected_revenue=Decimal("3000.00"),
            priority="HIGH",
            status="OPEN",
        )
        db.add(opp)
        await db.flush()

        wf = WorkflowState(
            workflow_id=uuid4(),
            opportunity_id=opp.opportunity_id,
            current_state=WorkflowStatus.DIAGNOSING.value,
            state_entered_at=datetime.now(tz=timezone.utc),
            idempotency_key=f"recovery-{payment_id}",
            audit_log=[],
        )
        db.add(wf)
        await db.commit()

        # Run Strategy Service
        svc = StrategyService(db)
        strategy, decision, updated_wf = await svc.select_strategy_for_opportunity(opp.opportunity_id)

        assert strategy.selected_action == ActionType.RETRY
        assert decision.opportunity_id == opp.opportunity_id
        assert len(decision.candidate_actions) == 5
        assert updated_wf.current_state == WorkflowStatus.STRATEGY_SELECTED.value

        # Verify Audit Log created
        from app.repositories.audit import AuditLogRepository
        audits = await AuditLogRepository(db).list_by_entity("RecoveryOpportunity", opp.opportunity_id)
        assert len(audits) == 1
        assert audits[0].action == "STRATEGY_SELECTED"
