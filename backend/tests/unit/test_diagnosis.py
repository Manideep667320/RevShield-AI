"""
Unit & Service tests for Phase 3 — Diagnosis Agent.
Includes a benchmark dataset verifying >90% classification accuracy on Razorpay failure codes.
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
from app.schemas.agents import CustomerHistory, DiagnosisInput
from app.schemas.enums import FailureCause, PaymentMethod, WorkflowStatus
from app.schemas.payment_event import PaymentEventRead
from app.services.diagnosis import DiagnosisAgent, DiagnosisService


@pytest.fixture
def sample_diagnosis_input():
    customer_id = uuid4()
    event = PaymentEventRead(
        event_id=uuid4(),
        merchant_id=uuid4(),
        customer_id=customer_id,
        payment_id=f"pay_{uuid4().hex[:16]}",
        amount=Decimal("1999.00"),
        currency="INR",
        payment_method=PaymentMethod.CARD,
        status="failed",
        failure_code="GATEWAY_ERROR",
        failure_category=FailureCause.TEMPORARY_FAILURE.value,
        timestamp=datetime.now(tz=timezone.utc),
        metadata={},
    )

    history = CustomerHistory(
        customer_id=customer_id,
        total_payments=15,
        successful_payments=12,
        recent_failure_codes=["SERVER_ERROR"],
        days_since_last_success=3,
    )

    return DiagnosisInput(
        payment_event=event,
        customer_history=history,
        failure_code="GATEWAY_ERROR",
    )


class TestDiagnosisAgentUnit:

    def test_temporary_failure_diagnosis(self, sample_diagnosis_input):
        agent = DiagnosisAgent()
        out = agent.diagnose(sample_diagnosis_input)
        assert out.cause == FailureCause.TEMPORARY_FAILURE
        assert out.confidence == 0.85
        assert out.retriable is True
        assert len(out.evidence) >= 3

    def test_insufficient_funds_diagnosis(self, sample_diagnosis_input):
        inp = sample_diagnosis_input.model_copy(update={"failure_code": "BAD_REQUEST_ERROR:INSUFFICIENT_BALANCE"})
        agent = DiagnosisAgent()
        out = agent.diagnose(inp)
        assert out.cause == FailureCause.INSUFFICIENT_FUNDS
        assert out.confidence == 0.95
        assert out.suggested_wait_minutes == 1440
        assert out.retriable is True

    def test_card_expired_diagnosis(self, sample_diagnosis_input):
        inp = sample_diagnosis_input.model_copy(update={"failure_code": "BAD_REQUEST_ERROR:CARD_EXPIRED"})
        agent = DiagnosisAgent()
        out = agent.diagnose(inp)
        assert out.cause == FailureCause.PAYMENT_METHOD_FAILURE
        assert out.confidence == 0.95
        assert out.retriable is False

    def test_unknown_code_fallback(self, sample_diagnosis_input):
        inp = sample_diagnosis_input.model_copy(update={"failure_code": "SOMETHING_NEW_AND_UNMAPPED"})
        agent = DiagnosisAgent()
        out = agent.diagnose(inp)
        assert out.cause == FailureCause.UNKNOWN
        assert out.confidence == 0.30
        assert out.fallback_used is True
        assert "Unmapped Razorpay code" in out.evidence[0]


# ── Labeled Benchmark Test Set for Classification Accuracy (>90% target) ────

BENCHMARK_FAILURE_CODES = [
    # (Razorpay Failure Code, Expected FailureCause)
    ("GATEWAY_ERROR", FailureCause.TEMPORARY_FAILURE),
    ("SERVER_ERROR", FailureCause.TEMPORARY_FAILURE),
    ("TIMEOUT", FailureCause.TEMPORARY_FAILURE),
    ("BAD_REQUEST_ERROR:PAYMENT_PROCESSING_FAILED", FailureCause.TEMPORARY_FAILURE),
    ("BAD_REQUEST_ERROR:INSUFFICIENT_BALANCE", FailureCause.INSUFFICIENT_FUNDS),
    ("BAD_REQUEST_ERROR:INSUFFICIENT_FUNDS", FailureCause.INSUFFICIENT_FUNDS),
    ("BAD_REQUEST_ERROR:CREDIT_LIMIT_EXCEEDED", FailureCause.INSUFFICIENT_FUNDS),
    ("BAD_REQUEST_ERROR:CARD_EXPIRED", FailureCause.PAYMENT_METHOD_FAILURE),
    ("BAD_REQUEST_ERROR:INVALID_CARD", FailureCause.PAYMENT_METHOD_FAILURE),
    ("BAD_REQUEST_ERROR:CARD_INVALID_CVV", FailureCause.PAYMENT_METHOD_FAILURE),
    ("BAD_REQUEST_ERROR:INVALID_UPI_ID", FailureCause.PAYMENT_METHOD_FAILURE),
    ("BAD_REQUEST_ERROR:PAYMENT_METHOD_NOT_SUPPORTED", FailureCause.PAYMENT_METHOD_FAILURE),
    ("BAD_REQUEST_ERROR:PAYMENT_LINK_EXPIRED", FailureCause.EXPIRED_PAYMENT),
    ("BAD_REQUEST_ERROR:ORDER_EXPIRED", FailureCause.EXPIRED_PAYMENT),
    ("BAD_REQUEST_ERROR:PAYMENT_TIMEOUT", FailureCause.EXPIRED_PAYMENT),
    ("BAD_REQUEST_ERROR:CARD_STOLEN", FailureCause.RISK_REJECTION),
    ("BAD_REQUEST_ERROR:RISK_THRESHOLD", FailureCause.RISK_REJECTION),
    ("BAD_REQUEST_ERROR:SUSPECTED_FRAUD", FailureCause.RISK_REJECTION),
    ("BAD_REQUEST_ERROR:PAYMENT_BLOCKED", FailureCause.RISK_REJECTION),
    ("BAD_REQUEST_ERROR:PAYMENT_CANCELLED", FailureCause.CUSTOMER_ABANDONMENT),
    ("BAD_REQUEST_ERROR:USER_CANCELLED", FailureCause.CUSTOMER_ABANDONMENT),
    ("BAD_REQUEST_ERROR:BANK_ACCOUNT_FROZEN", FailureCause.TEMPORARY_FAILURE),
    ("BAD_REQUEST_ERROR:ISSUER_NOT_AVAILABLE", FailureCause.TEMPORARY_FAILURE),
    ("BAD_REQUEST_ERROR:BANK_NOT_AVAILABLE", FailureCause.TEMPORARY_FAILURE),
    ("RANDOM_UNMAPPED_CODE_123", FailureCause.UNKNOWN),
]


class TestClassificationAccuracyBenchmark:

    def test_benchmark_accuracy_exceeds_target(self, sample_diagnosis_input):
        agent = DiagnosisAgent()
        correct = 0
        total = len(BENCHMARK_FAILURE_CODES)

        for code, expected_cause in BENCHMARK_FAILURE_CODES:
            inp = sample_diagnosis_input.model_copy(update={"failure_code": code})
            out = agent.diagnose(inp)
            if out.cause == expected_cause:
                correct += 1

        accuracy_pct = (correct / total) * 100.0
        print(f"\n[BENCHMARK RESULT] Correct: {correct}/{total} | Accuracy: {accuracy_pct:.1f}%")

        # Target: >90% classification accuracy
        assert accuracy_pct >= 90.0, f"Classification accuracy {accuracy_pct}% fell below 90% target"


class TestDiagnosisServiceIntegration:

    @pytest.mark.asyncio
    async def test_diagnose_opportunity_pipeline(self, db):
        merchant = Merchant(merchant_id=uuid4(), name="Diagnosis Test Merchant")
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
            amount=Decimal("2500.00"),
            currency="INR",
            payment_method="CARD",
            status="failed",
            failure_code="BAD_REQUEST_ERROR:INSUFFICIENT_BALANCE",
            failure_category=FailureCause.INSUFFICIENT_FUNDS.value,
            timestamp=datetime.now(tz=timezone.utc),
            metadata_={},
        )
        db.add(event)
        await db.flush()

        opp = RecoveryOpportunity(
            opportunity_id=uuid4(),
            payment_id=payment_id,
            recoverability_score=Decimal("0.75"),
            expected_revenue=Decimal("2500.00"),
            priority="HIGH",
            status="OPEN",
        )
        db.add(opp)
        await db.flush()

        wf = WorkflowState(
            workflow_id=uuid4(),
            opportunity_id=opp.opportunity_id,
            current_state=WorkflowStatus.PENDING.value,
            state_entered_at=datetime.now(tz=timezone.utc),
            idempotency_key=f"recovery-{payment_id}",
            audit_log=[],
        )
        db.add(wf)
        await db.commit()

        # Run Diagnosis Service
        svc = DiagnosisService(db)
        diagnosis, updated_wf = await svc.diagnose_opportunity(opp.opportunity_id)

        assert diagnosis.cause == FailureCause.INSUFFICIENT_FUNDS
        assert diagnosis.confidence == 0.95
        assert updated_wf.current_state == WorkflowStatus.DIAGNOSING.value

        # Verify Audit Log created
        from app.repositories.audit import AuditLogRepository
        audits = await AuditLogRepository(db).list_by_entity("RecoveryOpportunity", opp.opportunity_id)
        assert len(audits) == 1
        assert audits[0].action == "DIAGNOSIS_COMPLETED"
