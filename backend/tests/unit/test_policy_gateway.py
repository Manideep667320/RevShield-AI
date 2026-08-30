"""
Unit & Service tests for Phase 5 — Policy Gateway.
Tests hard policy rules, cryptographic clearance token signing/verification,
and human approval queue operations (list, approve, reject).
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from app.models.customer import Customer
from app.models.merchant import Merchant
from app.models.payment_event import PaymentEvent
from app.models.recovery import RecoveryDecision, RecoveryOpportunity
from app.models.workflow import WorkflowState
from app.schemas.agents import PolicyClearance, PolicyRequest, StrategyOutput
from app.schemas.customer import CustomerContext
from app.schemas.enums import ActionType, FailureCause, Priority, WorkflowStatus
from app.schemas.policy import PolicyRead
from app.schemas.recovery import CandidateAction, RecoveryOpportunityRead
from app.services.policy_gateway import (
    PolicyGatewayAgent,
    PolicyGatewayService,
    generate_clearance_token,
    verify_clearance_token,
)


@pytest.fixture
def sample_policy_request():
    merchant_id = uuid4()
    opp_id = uuid4()

    opp = RecoveryOpportunityRead(
        opportunity_id=opp_id,
        payment_id=f"pay_{uuid4().hex[:16]}",
        recoverability_score=0.80,
        expected_revenue=Decimal("5000.00"),
        priority=Priority.HIGH,
        status="OPEN",
        created_at=datetime.now(tz=timezone.utc),
    )

    strategy = StrategyOutput(
        candidate_actions=[
            CandidateAction(
                action=ActionType.RETRY,
                p_success=0.75,
                expected_value=Decimal("3748.00"),
                cost=Decimal("2.00"),
                confidence=0.85,
            )
        ],
        selected_action=ActionType.RETRY,
        expected_value=Decimal("3748.00"),
        confidence=0.85,
        reasoning="Selected RETRY",
    )

    policy = PolicyRead(
        policy_id=uuid4(),
        merchant_id=merchant_id,
        max_retry_count=2,
        max_discount_pct=Decimal("5.00"),
        allowed_channels=["RETRY", "PAYMENT_LINK", "REMINDER", "HUMAN_ESCALATION"],
        approval_threshold=Decimal("25000.00"),
        max_intervention_cost=Decimal("50.00"),
        active=True,
        version=1,
    )

    return PolicyRequest(
        strategy=strategy,
        opportunity=opp,
        merchant_policy=policy,
        current_retry_count=0,
    )


class TestPolicyGatewayAgentUnit:

    def test_policy_cleared_for_valid_request(self, sample_policy_request):
        agent = PolicyGatewayAgent()
        clearance = agent.evaluate(sample_policy_request)

        assert clearance.approved is True
        assert clearance.requires_human_approval is False
        assert clearance.approved_action == ActionType.RETRY
        assert clearance.clearance_token != ""

        # Verify issued token
        valid, msg = verify_clearance_token(
            clearance.clearance_token,
            sample_policy_request.opportunity.opportunity_id,
            ActionType.RETRY,
        )
        assert valid is True

    def test_inactive_policy_rejection(self, sample_policy_request):
        req = sample_policy_request.model_copy()
        req.merchant_policy = req.merchant_policy.model_copy(update={"active": False})

        agent = PolicyGatewayAgent()
        clearance = agent.evaluate(req)

        assert clearance.approved is False
        assert "inactive" in clearance.rejection_reason.lower()
        assert clearance.clearance_token == ""

    def test_disallowed_channel_rejection(self, sample_policy_request):
        req = sample_policy_request.model_copy()
        req.merchant_policy = req.merchant_policy.model_copy(
            update={"allowed_channels": ["PAYMENT_LINK"]}
        )

        agent = PolicyGatewayAgent()
        clearance = agent.evaluate(req)

        assert clearance.approved is False
        assert "not permitted" in clearance.rejection_reason.lower()

    def test_max_retry_count_exceeded(self, sample_policy_request):
        req = sample_policy_request.model_copy(update={"current_retry_count": 2})

        agent = PolicyGatewayAgent()
        clearance = agent.evaluate(req)

        assert clearance.approved is False
        assert "retry limit" in clearance.rejection_reason.lower()

    def test_action_cost_exceeds_limit(self, sample_policy_request):
        req = sample_policy_request.model_copy()
        req.strategy = req.strategy.model_copy(
            update={
                "candidate_actions": [
                    CandidateAction(
                        action=ActionType.HUMAN_ESCALATION,
                        p_success=0.80,
                        expected_value=Decimal("1000.00"),
                        cost=Decimal("60.00"),  # exceeds max_intervention_cost (50.00)
                        confidence=0.80,
                    )
                ],
                "selected_action": ActionType.HUMAN_ESCALATION,
            }
        )

        agent = PolicyGatewayAgent()
        clearance = agent.evaluate(req)

        assert clearance.approved is False
        assert "exceeds policy limit" in clearance.rejection_reason.lower()

    def test_human_approval_threshold_triggered(self, sample_policy_request):
        req = sample_policy_request.model_copy()
        req.opportunity = req.opportunity.model_copy(
            update={"expected_revenue": Decimal("30000.00")}
        )

        agent = PolicyGatewayAgent()
        clearance = agent.evaluate(req)

        assert clearance.approved is False
        assert clearance.requires_human_approval is True
        assert "human review" in clearance.rejection_reason.lower()
        assert clearance.clearance_token == ""


class TestClearanceTokenSecurity:

    def test_valid_token_verification(self):
        opp_id = uuid4()
        token = generate_clearance_token(opp_id, ActionType.PAYMENT_LINK, "v1")
        valid, msg = verify_clearance_token(token, opp_id, ActionType.PAYMENT_LINK)
        assert valid is True

    def test_mismatched_opportunity_id(self):
        opp_id1 = uuid4()
        opp_id2 = uuid4()
        token = generate_clearance_token(opp_id1, ActionType.RETRY, "v1")
        valid, msg = verify_clearance_token(token, opp_id2, ActionType.RETRY)
        assert valid is False
        assert "mismatch" in msg.lower()

    def test_mismatched_action(self):
        opp_id = uuid4()
        token = generate_clearance_token(opp_id, ActionType.RETRY, "v1")
        valid, msg = verify_clearance_token(token, opp_id, ActionType.PAYMENT_LINK)
        assert valid is False
        assert "action mismatch" in msg.lower()


class TestPolicyGatewayServiceIntegration:

    @pytest_asyncio.fixture
    async def seed_opp_pipeline(self, db):
        merchant = Merchant(
            merchant_id=uuid4(),
            name="Policy Test Merchant",
            recovery_policy={
                "max_retry_count": 2,
                "approval_threshold": 25000,
                "allowed_channels": ["RETRY", "PAYMENT_LINK", "REMINDER"],
            },
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
            amount=Decimal("5000.00"),
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
            expected_revenue=Decimal("5000.00"),
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
                "expected_value": "3748.00",
                "cost": "2.00",
                "confidence": 0.85,
            }],
            selected_action="RETRY",
            expected_value=Decimal("3748.00"),
            confidence=Decimal("0.85"),
            reasoning="Selected RETRY",
            model_version="v1.0",
        )
        db.add(decision)
        await db.flush()

        wf = WorkflowState(
            workflow_id=uuid4(),
            opportunity_id=opp.opportunity_id,
            current_state=WorkflowStatus.STRATEGY_SELECTED.value,
            state_entered_at=datetime.now(tz=timezone.utc),
            idempotency_key=f"recovery-{payment_id}",
            audit_log=[],
        )
        db.add(wf)
        await db.commit()

        return merchant, customer, event, opp, decision, wf

    @pytest.mark.asyncio
    async def test_evaluate_opportunity_policy_auto_cleared(self, db, seed_opp_pipeline):
        *_, opp, _, _ = seed_opp_pipeline
        svc = PolicyGatewayService(db)
        clearance, updated_wf = await svc.evaluate_opportunity_policy(opp.opportunity_id)

        assert clearance.approved is True
        assert clearance.clearance_token != ""
        assert updated_wf.current_state == WorkflowStatus.AWAITING_POLICY.value

    @pytest.mark.asyncio
    async def test_evaluate_opportunity_policy_human_queue(self, db, seed_opp_pipeline):
        *_, opp, _, _ = seed_opp_pipeline
        # Update opp revenue to exceed threshold (25000.00)
        opp.expected_revenue = Decimal("30000.00")
        await db.commit()

        svc = PolicyGatewayService(db)
        clearance, updated_wf = await svc.evaluate_opportunity_policy(opp.opportunity_id)

        assert clearance.approved is False
        assert clearance.requires_human_approval is True
        assert updated_wf.current_state == WorkflowStatus.AWAITING_APPROVAL.value

        # Verify listing in human approval queue
        pending = await svc.get_pending_human_approvals()
        assert len(pending) == 1
        assert pending[0]["opportunity_id"] == str(opp.opportunity_id)

    @pytest.mark.asyncio
    async def test_approve_human_request(self, db, seed_opp_pipeline):
        *_, opp, _, wf = seed_opp_pipeline
        wf.current_state = WorkflowStatus.AWAITING_APPROVAL.value
        await db.commit()

        svc = PolicyGatewayService(db)
        clearance, updated_wf = await svc.approve_human_request(opp.opportunity_id, manager_id="mgr_alice@corp.com")

        assert clearance.approved is True
        assert clearance.clearance_token != ""
        assert updated_wf.current_state == WorkflowStatus.AWAITING_POLICY.value

    @pytest.mark.asyncio
    async def test_reject_human_request(self, db, seed_opp_pipeline):
        *_, opp, _, wf = seed_opp_pipeline
        wf.current_state = WorkflowStatus.AWAITING_APPROVAL.value
        await db.commit()

        svc = PolicyGatewayService(db)
        updated_wf = await svc.reject_human_request(opp.opportunity_id, manager_id="mgr_bob@corp.com", reason="Budget limit exceeded")

        assert updated_wf.current_state == WorkflowStatus.POLICY_REJECTED.value
