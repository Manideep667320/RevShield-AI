"""
Unit & Service tests for Phase 6 — Action Agent & Circuit Breaker.
Tests clearance token verification enforcement, Razorpay sandbox action execution,
circuit breaker activation on error rates > 20%, and DB persistence.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from app.core.exceptions import CircuitOpenError, PolicyViolationError
from app.models.customer import Customer
from app.models.merchant import Merchant
from app.models.payment_event import PaymentEvent
from app.models.recovery import RecoveryDecision, RecoveryOpportunity
from app.models.workflow import WorkflowState
from app.schemas.agents import ActionRequest, PolicyClearance
from app.schemas.enums import ActionType, FailureCause, WorkflowStatus
from app.services.action_agent import ActionAgent, ActionService
from app.services.circuit_breaker import CircuitBreaker
from app.services.policy_gateway import generate_clearance_token
from app.services.razorpay_client import RazorpaySandboxClient


@pytest.fixture
def sample_action_request():
    opp_id = uuid4()
    token = generate_clearance_token(opp_id, ActionType.RETRY, "v1")

    clearance = PolicyClearance(
        approved=True,
        requires_human_approval=False,
        approved_action=ActionType.RETRY,
        policy_version="v1",
        clearance_token=token,
    )

    return ActionRequest(
        opportunity_id=opp_id,
        action_type=ActionType.RETRY,
        clearance=clearance,
        customer_contact={"email": "cust@example.com", "phone": "+919876543210"},
        payment_details={"payment_id": "pay_test123", "amount": "2500.00"},
        idempotency_key=f"action-{opp_id}",
    )


class TestActionAgentUnit:

    def test_clearance_token_required_for_execution(self, sample_action_request):
        agent = ActionAgent()

        # Modify token to invalid value
        req = sample_action_request.model_copy()
        req.clearance = req.clearance.model_copy(update={"clearance_token": "invalid_tampered_token"})

        with pytest.raises(PolicyViolationError) as exc_info:
            agent.execute_action(req)

        assert "verification failed" in str(exc_info.value).lower()

    def test_execute_retry_action(self, sample_action_request):
        agent = ActionAgent()
        resp, cost = agent.execute_action(sample_action_request)

        assert resp.success is True
        assert resp.status == "CAPTURED"
        assert resp.external_ref.startswith("pay_retry_")
        assert cost == Decimal("0.00")

    def test_execute_payment_link_action(self, sample_action_request):
        opp_id = uuid4()
        token = generate_clearance_token(opp_id, ActionType.PAYMENT_LINK, "v1")

        clearance = PolicyClearance(
            approved=True,
            requires_human_approval=False,
            approved_action=ActionType.PAYMENT_LINK,
            policy_version="v1",
            clearance_token=token,
        )

        req = sample_action_request.model_copy(
            update={
                "opportunity_id": opp_id,
                "action_type": ActionType.PAYMENT_LINK,
                "clearance": clearance,
            }
        )

        agent = ActionAgent()
        resp, cost = agent.execute_action(req)

        assert resp.success is True
        assert resp.status == "CREATED"
        assert resp.external_ref.startswith("plink_")
        assert cost == Decimal("2.00")


class TestCircuitBreaker:

    def test_circuit_breaker_opens_on_high_failure_rate(self):
        cb = CircuitBreaker(window_size=10, failure_threshold=0.20, cooldown_seconds=30)

        # 7 successes + 3 failures = 30% failure rate (> 20%)
        for _ in range(7):
            cb.record_success()

        for _ in range(3):
            cb.record_failure()

        assert cb.is_open is True

        # Next check_state should raise CircuitOpenError
        with pytest.raises(CircuitOpenError):
            cb.check_state()

    def test_circuit_breaker_blocks_razorpay_client(self):
        failing_razorpay = RazorpaySandboxClient(simulate_failure=True)
        agent = ActionAgent(razorpay_client=failing_razorpay)

        opp_id = uuid4()
        token = generate_clearance_token(opp_id, ActionType.RETRY, "v1")
        clearance = PolicyClearance(
            approved=True,
            requires_human_approval=False,
            approved_action=ActionType.RETRY,
            policy_version="v1",
            clearance_token=token,
        )
        req = ActionRequest(
            opportunity_id=opp_id,
            action_type=ActionType.RETRY,
            clearance=clearance,
            customer_contact={},
            payment_details={"payment_id": "pay_test"},
            idempotency_key=f"action-{opp_id}",
        )

        # Execute multiple failing requests
        for _ in range(3):
            resp, cost = agent.execute_action(req)
            assert resp.success is False


class TestActionServiceIntegration:

    @pytest.mark.asyncio
    async def test_execute_opportunity_intervention_pipeline(self, db):
        merchant = Merchant(
            merchant_id=uuid4(),
            name="Action Test Merchant",
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
            amount=Decimal("4000.00"),
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
            expected_revenue=Decimal("4000.00"),
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
                "expected_value": "2998.00",
                "cost": "0.00",
                "confidence": 0.85,
            }],
            selected_action="RETRY",
            expected_value=Decimal("2998.00"),
            confidence=Decimal("0.85"),
            reasoning="Selected RETRY",
            model_version="v1.0",
        )
        db.add(decision)
        await db.flush()

        wf = WorkflowState(
            workflow_id=uuid4(),
            opportunity_id=opp.opportunity_id,
            current_state=WorkflowStatus.AWAITING_POLICY.value,
            state_entered_at=datetime.now(tz=timezone.utc),
            idempotency_key=f"recovery-{payment_id}",
            audit_log=[],
        )
        db.add(wf)
        await db.commit()

        # Generate clearance token
        token = generate_clearance_token(opp.opportunity_id, ActionType.RETRY, "v1")

        # Execute Action Service
        svc = ActionService(db)
        resp, intervention, updated_wf = await svc.execute_opportunity_intervention(opp.opportunity_id, token)

        assert resp.success is True
        assert intervention.decision_id == decision.decision_id
        assert intervention.type == "RETRY"
        assert intervention.status == "CAPTURED"
        assert updated_wf.current_state == WorkflowStatus.EXECUTING.value

        # Verify Audit Log created
        from app.repositories.audit import AuditLogRepository
        audits = await AuditLogRepository(db).list_by_entity("RecoveryOpportunity", opp.opportunity_id)
        assert len(audits) == 1
        assert audits[0].action == "ACTION_EXECUTED"
