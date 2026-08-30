"""
Unit & Service tests for Phase 2 — Detection Agent.
Tests eligibility rules, recoverability scoring, priority assignment,
and DB persistence (RecoveryOpportunity + WorkflowState + AuditLog).
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from app.models.customer import Customer
from app.models.merchant import Merchant
from app.schemas.agents import DetectionInput
from app.schemas.customer import CustomerContext
from app.schemas.enums import FailureCause, PaymentMethod, Priority, WorkflowStatus
from app.schemas.payment_event import PaymentEventRead
from app.schemas.policy import PolicyRead
from app.services.detection import DetectionAgent, DetectionService


@pytest.fixture
def sample_data():
    merchant_id = uuid4()
    customer_id = uuid4()

    event = PaymentEventRead(
        event_id=uuid4(),
        merchant_id=merchant_id,
        customer_id=customer_id,
        payment_id=f"pay_{uuid4().hex[:16]}",
        amount=Decimal("1500.00"),
        currency="INR",
        payment_method=PaymentMethod.CARD,
        status="failed",
        failure_code="GATEWAY_ERROR",
        failure_category=FailureCause.TEMPORARY_FAILURE.value,
        timestamp=datetime.now(tz=timezone.utc),
        metadata={},
    )

    customer = CustomerContext(
        customer_id=customer_id,
        historical_payment_count=10,
        successful_payment_count=9,
        average_transaction_value=Decimal("1200.00"),
        risk_score=0.15,
        last_successful_payment=datetime.now(tz=timezone.utc),
    )

    policy = PolicyRead(
        policy_id=uuid4(),
        merchant_id=merchant_id,
        max_retry_count=2,
        max_discount_pct=Decimal("5.00"),
        allowed_channels=["RETRY", "PAYMENT_LINK"],
        approval_threshold=Decimal("25000.00"),
        max_intervention_cost=Decimal("50.00"),
        active=True,
        version=1,
    )

    return event, customer, policy


class TestDetectionAgentEligibility:

    def test_eligible_payment_event(self, sample_data):
        event, customer, policy = sample_data
        eligible, reason = DetectionAgent.evaluate_eligibility(event, customer, policy)
        assert eligible is True
        assert "passed" in reason.lower()

    def test_ineligible_if_status_not_failed(self, sample_data):
        event, customer, policy = sample_data
        event_succ = event.model_copy(update={"status": "captured"})
        eligible, reason = DetectionAgent.evaluate_eligibility(event_succ, customer, policy)
        assert eligible is False
        assert "not failed" in reason.lower()

    def test_ineligible_if_policy_inactive(self, sample_data):
        event, customer, policy = sample_data
        policy_inactive = policy.model_copy(update={"active": False})
        eligible, reason = DetectionAgent.evaluate_eligibility(event, customer, policy_inactive)
        assert eligible is False
        assert "disabled" in reason.lower()

    def test_ineligible_if_zero_amount(self, sample_data):
        event, customer, policy = sample_data
        event_zero = event.model_copy(update={"amount": Decimal("0.00")})
        eligible, reason = DetectionAgent.evaluate_eligibility(event_zero, customer, policy)
        assert eligible is False
        assert "greater than zero" in reason.lower()

    def test_ineligible_if_high_risk_score(self, sample_data):
        event, customer, policy = sample_data
        customer_high_risk = customer.model_copy(update={"risk_score": 0.95})
        eligible, reason = DetectionAgent.evaluate_eligibility(event, customer_high_risk, policy)
        assert eligible is False
        assert "risk score" in reason.lower()

    def test_ineligible_if_risk_rejection_failure(self, sample_data):
        event, customer, policy = sample_data
        event_risk = event.model_copy(update={"failure_category": FailureCause.RISK_REJECTION.value})
        eligible, reason = DetectionAgent.evaluate_eligibility(event_risk, customer, policy)
        assert eligible is False
        assert "risk/fraud" in reason.lower()


class TestDetectionAgentScoringAndPriority:

    def test_high_recoverability_scoring(self, sample_data):
        event, customer, policy = sample_data
        score = DetectionAgent.calculate_recoverability_score(event, customer)
        # 0.225 (90% success) + 0.10 (3+ payments) + 0.35 (temp failure) + 0.15 (low risk) + 0.05 (recent) + 0.10 (value) = 0.990
        assert 0.85 <= score <= 0.99

    def test_low_recoverability_scoring(self, sample_data):
        event, customer, policy = sample_data
        cust_low = customer.model_copy(update={
            "historical_payment_count": 0,
            "successful_payment_count": 0,
            "risk_score": 0.80,
            "last_successful_payment": None,
        })
        event_bad = event.model_copy(update={"failure_category": FailureCause.RISK_REJECTION.value})
        score = DetectionAgent.calculate_recoverability_score(event_bad, cust_low)
        assert score <= 0.30

    def test_priority_assignment(self):
        assert DetectionAgent.assign_priority(0.80, Decimal("1000.00")) == Priority.HIGH
        assert DetectionAgent.assign_priority(0.55, Decimal("15000.00")) == Priority.HIGH
        assert DetectionAgent.assign_priority(0.45, Decimal("1000.00")) == Priority.MEDIUM
        assert DetectionAgent.assign_priority(0.30, Decimal("500.00")) == Priority.LOW


class TestDetectionServicePersistence:

    @pytest.mark.asyncio
    async def test_detect_and_create_opportunity_pipeline(self, db, sample_data):
        event, customer, policy = sample_data
        input_data = DetectionInput(
            payment_event=event,
            customer_context=customer,
            merchant_policy=policy,
        )

        svc = DetectionService(db)
        output, opp, wf = await svc.detect_and_create_opportunity(input_data)

        assert output.eligible is True
        assert output.recoverability_score > 0.50
        assert opp is not None
        assert wf is not None

        # Verify DB records
        from app.repositories.opportunity import RecoveryOpportunityRepository
        from app.repositories.workflow_state import WorkflowStateRepository
        from app.repositories.audit import AuditLogRepository

        opp_db = await RecoveryOpportunityRepository(db).get_by_payment_id(event.payment_id)
        assert opp_db is not None
        assert opp_db.priority == output.priority.value
        assert opp_db.status == "OPEN"

        wf_db = await WorkflowStateRepository(db).get_by_idempotency_key(f"recovery-{event.payment_id}")
        assert wf_db is not None
        assert wf_db.current_state == WorkflowStatus.PENDING.value
        assert len(wf_db.audit_log) == 1

        audits = await AuditLogRepository(db).list_by_entity("RecoveryOpportunity", opp.opportunity_id)
        assert len(audits) == 1
        assert audits[0].actor.startswith("detection_agent")

    @pytest.mark.asyncio
    async def test_detect_ineligible_does_not_create_records(self, db, sample_data):
        event, customer, policy = sample_data
        event_succ = event.model_copy(update={"status": "captured"})
        input_data = DetectionInput(
            payment_event=event_succ,
            customer_context=customer,
            merchant_policy=policy,
        )

        svc = DetectionService(db)
        output, opp, wf = await svc.detect_and_create_opportunity(input_data)

        assert output.eligible is False
        assert opp is None
        assert wf is None

    @pytest.mark.asyncio
    async def test_detect_idempotent_duplicate_prevention(self, db, sample_data):
        event, customer, policy = sample_data
        input_data = DetectionInput(
            payment_event=event,
            customer_context=customer,
            merchant_policy=policy,
        )

        svc = DetectionService(db)
        output1, opp1, wf1 = await svc.detect_and_create_opportunity(input_data)
        output2, opp2, wf2 = await svc.detect_and_create_opportunity(input_data)

        assert opp1.opportunity_id == opp2.opportunity_id
        assert wf1.workflow_id == wf2.workflow_id
