"""
Unit & Service tests for Phase 7 — Outcome Attribution & Learning Agent.
Tests time-window attribution rules, TREATMENT vs CONTROL baseline incrementality calculations,
strategy probability store feedback loops, and DB outcome recording pipeline.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from app.models.customer import Customer
from app.models.merchant import Merchant
from app.models.payment_event import PaymentEvent
from app.models.recovery import Intervention, RecoveryDecision, RecoveryOpportunity
from app.models.workflow import WorkflowState
from app.schemas.enums import ActionType, ExperimentGroup, FailureCause, OpportunityStatus, WorkflowStatus
from app.services.attribution import AttributionEngine
from app.services.learning import LearningAgent, LearningService
from app.services.strategy import P_SUCCESS_MATRIX


class TestAttributionEngineUnit:

    def test_attribution_within_time_window_treatment(self):
        now = datetime.now(tz=timezone.utc)
        executed_at = now - timedelta(hours=2)

        res = AttributionEngine.evaluate_attribution(
            payment_status="CAPTURED",
            amount=Decimal("1000.00"),
            executed_at=executed_at,
            recorded_at=now,
            action_type=ActionType.RETRY,
            cause=FailureCause.TEMPORARY_FAILURE,  # organic baseline 10%
            experiment_group=ExperimentGroup.TREATMENT,
        )

        assert res.attributed is True
        assert res.recovered_amount == Decimal("1000.00")
        # 1000 - 10% organic (100) = 900.00
        assert res.incremental_recovery == Decimal("900.00")

    def test_attribution_outside_time_window_rejected(self):
        now = datetime.now(tz=timezone.utc)
        executed_at = now - timedelta(hours=30)  # max window for RETRY is 24h

        res = AttributionEngine.evaluate_attribution(
            payment_status="CAPTURED",
            amount=Decimal("1000.00"),
            executed_at=executed_at,
            recorded_at=now,
            action_type=ActionType.RETRY,
            cause=FailureCause.TEMPORARY_FAILURE,
            experiment_group=ExperimentGroup.TREATMENT,
        )

        assert res.attributed is False
        assert res.incremental_recovery == Decimal("0.00")
        assert "outside attribution window" in res.reason.lower()

    def test_attribution_control_group_baseline(self):
        now = datetime.now(tz=timezone.utc)
        executed_at = now - timedelta(hours=2)

        res = AttributionEngine.evaluate_attribution(
            payment_status="CAPTURED",
            amount=Decimal("1000.00"),
            executed_at=executed_at,
            recorded_at=now,
            action_type=ActionType.RETRY,
            cause=FailureCause.TEMPORARY_FAILURE,
            experiment_group=ExperimentGroup.CONTROL,
        )

        assert res.attributed is True
        assert res.recovered_amount == Decimal("1000.00")
        assert res.incremental_recovery == Decimal("0.00")  # Control = 0 incremental lift


class TestLearningAgentFeedback:

    def test_strategy_feedback_matrix_update(self):
        agent = LearningAgent()
        initial_p = P_SUCCESS_MATRIX[FailureCause.TEMPORARY_FAILURE][ActionType.RETRY]

        agent.update_strategy_feedback(ActionType.RETRY, FailureCause.TEMPORARY_FAILURE, success=True)
        new_p = P_SUCCESS_MATRIX[FailureCause.TEMPORARY_FAILURE][ActionType.RETRY]

        # Success should increase probability estimate
        assert new_p > initial_p


class TestLearningServiceIntegration:

    @pytest.mark.asyncio
    async def test_record_opportunity_outcome_pipeline(self, db):
        merchant = Merchant(
            merchant_id=uuid4(),
            name="Learning Test Merchant",
        )
        customer = Customer(
            customer_id=uuid4(), merchant_id=merchant.merchant_id
        )
        db.add_all([merchant, customer])
        await db.flush()

        payment_id = f"pay_{uuid4().hex[:16]}"
        event = PaymentEvent(
            event_id=uuid4(),
            merchant_id=str(merchant.merchant_id),
            customer_id=str(customer.customer_id),
            payment_id=payment_id,
            amount=Decimal("2000.00"),
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
            recoverability_score=Decimal("0.85"),
            expected_revenue=Decimal("2000.00"),
            priority="HIGH",
            status="OPEN",
        )
        db.add(opp)
        await db.flush()

        decision = RecoveryDecision(
            decision_id=uuid4(),
            opportunity_id=opp.opportunity_id,
            candidate_actions=[{
                "action": "RETRY",
                "p_success": 0.75,
                "expected_value": "1498.00",
                "cost": "0.00",
                "confidence": 0.85,
            }],
            selected_action="RETRY",
            expected_value=Decimal("1498.00"),
            confidence=Decimal("0.85"),
            reasoning="Selected RETRY",
            model_version="v1.0",
        )
        db.add(decision)
        await db.flush()

        intervention = Intervention(
            intervention_id=uuid4(),
            decision_id=decision.decision_id,
            type="RETRY",
            status="CAPTURED",
            executed_at=datetime.now(tz=timezone.utc),
            cost=Decimal("0.00"),
            external_ref=f"pay_retry_{uuid4().hex[:8]}",
        )
        db.add(intervention)

        wf = WorkflowState(
            workflow_id=uuid4(),
            opportunity_id=opp.opportunity_id,
            current_state=WorkflowStatus.EXECUTING.value,
            state_entered_at=datetime.now(tz=timezone.utc),
            idempotency_key=f"recovery-{payment_id}",
            audit_log=[],
        )
        db.add(wf)
        await db.commit()

        # Execute Learning Service
        svc = LearningService(db)
        attrib, outcome, updated_wf = await svc.record_opportunity_outcome(
            opportunity_id=opp.opportunity_id,
            payment_status="CAPTURED",
            recovered_amount=Decimal("2000.00"),
            experiment_group=ExperimentGroup.TREATMENT,
        )

        assert attrib.attributed is True
        assert outcome.recovered_amount == Decimal("2000.00")
        assert updated_wf.current_state == WorkflowStatus.RECOVERED.value

        # Verify Opportunity status updated to RECOVERED
        opp_refreshed = await svc.opp_repo.get(opp.opportunity_id)
        assert opp_refreshed.status == OpportunityStatus.RECOVERED.value
