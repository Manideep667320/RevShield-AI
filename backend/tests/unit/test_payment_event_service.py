"""
Unit tests for PaymentEventService ingestion logic.
Uses in-memory SQLite + mocked Redis publisher.
"""
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from app.models.customer import Customer
from app.models.merchant import Merchant
from app.schemas.enums import FailureCause, PaymentMethod
from app.schemas.payment_event import SimulatePaymentRequest
from app.services.payment_event import PaymentEventService


@pytest_asyncio.fixture
async def merchant(db):
    m = Merchant(merchant_id=uuid4(), name="Test Merchant", currency="INR")
    db.add(m)
    await db.flush()
    return m


@pytest_asyncio.fixture
async def customer(db, merchant):
    c = Customer(
        customer_id=uuid4(),
        merchant_id=merchant.merchant_id,
        historical_payment_count=10,
        successful_payment_count=9,
        average_transaction_value=Decimal("1500.00"),
        risk_score=0.1,
    )
    db.add(c)
    await db.flush()
    return c


@pytest.fixture
def mock_publisher():
    """Replace Redis publisher with a no-op mock."""
    publisher = AsyncMock()
    publisher.publish_payment_event = AsyncMock(return_value="1234567890-0")
    with patch("app.services.payment_event.get_publisher", return_value=publisher):
        yield publisher


class TestPaymentEventServiceSimulated:

    @pytest.mark.asyncio
    async def test_ingest_simulated_returns_accepted(self, db, merchant, customer, mock_publisher):
        svc = PaymentEventService(db)
        req = SimulatePaymentRequest(
            merchant_id=merchant.merchant_id,
            customer_id=customer.customer_id,
            amount=Decimal("999.00"),
            failure_code="GATEWAY_ERROR",
            payment_method=PaymentMethod.CARD,
        )
        result = await svc.ingest_simulated(req)
        assert result["status"] == "accepted"
        assert result["failure_category"] == FailureCause.TEMPORARY_FAILURE

    @pytest.mark.asyncio
    async def test_failed_event_is_queued(self, db, merchant, customer, mock_publisher):
        svc = PaymentEventService(db)
        req = SimulatePaymentRequest(
            merchant_id=merchant.merchant_id,
            customer_id=customer.customer_id,
            amount=Decimal("500.00"),
            failure_code="GATEWAY_ERROR",
            payment_method=PaymentMethod.UPI,
        )
        result = await svc.ingest_simulated(req)
        assert result["queued"] is True
        mock_publisher.publish_payment_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_payment_id_returns_duplicate_status(self, db, merchant, customer, mock_publisher):
        svc = PaymentEventService(db)
        req = SimulatePaymentRequest(
            merchant_id=merchant.merchant_id,
            customer_id=customer.customer_id,
            amount=Decimal("200.00"),
            failure_code="SERVER_ERROR",
            payment_method=PaymentMethod.CARD,
        )
        r1 = await svc.ingest_simulated(req)
        # Manually inject duplicate with same payment_id
        from app.repositories.payment_event import PaymentEventRepository
        from app.models.payment_event import PaymentEvent
        from datetime import datetime, timezone

        repo = PaymentEventRepository(db)
        dup_event = PaymentEvent(
            event_id=uuid4(),
            merchant_id=str(merchant.merchant_id),
            customer_id=str(customer.customer_id),
            payment_id=r1["payment_id"],   # same ID!
            amount=Decimal("200.00"),
            currency="INR",
            payment_method="CARD",
            status="failed",
            failure_code="SERVER_ERROR",
            failure_category="TEMPORARY_FAILURE",
            timestamp=datetime.now(tz=timezone.utc),
            metadata_={},
        )
        stored, created = await repo.create_idempotent(dup_event)
        assert created is False
        assert stored.payment_id == r1["payment_id"]

    @pytest.mark.asyncio
    async def test_failure_category_classified_correctly(self, db, merchant, customer, mock_publisher):
        svc = PaymentEventService(db)
        for failure_code, expected_cause in [
            ("BAD_REQUEST_ERROR:INSUFFICIENT_BALANCE", FailureCause.INSUFFICIENT_FUNDS),
            ("BAD_REQUEST_ERROR:CARD_EXPIRED", FailureCause.PAYMENT_METHOD_FAILURE),
            ("BAD_REQUEST_ERROR:PAYMENT_CANCELLED", FailureCause.CUSTOMER_ABANDONMENT),
        ]:
            req = SimulatePaymentRequest(
                merchant_id=merchant.merchant_id,
                customer_id=customer.customer_id,
                amount=Decimal("100.00"),
                failure_code=failure_code,
                payment_method=PaymentMethod.CARD,
            )
            result = await svc.ingest_simulated(req)
            assert result["failure_category"] == expected_cause, (
                f"Expected {expected_cause} for code {failure_code}, got {result['failure_category']}"
            )


class TestPaymentEventServiceRazorpayWebhook:

    def _make_payload(self, payment_id: str, failure_code: str = "GATEWAY_ERROR") -> dict:
        return {
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "amount": 99900,    # paise
                        "currency": "INR",
                        "method": "card",
                        "status": "failed",
                        "error_code": failure_code,
                        "merchant_id": str(uuid4()),
                        "customer_id": str(uuid4()),
                    }
                }
            }
        }

    @pytest.mark.asyncio
    async def test_razorpay_webhook_ingest(self, db, mock_publisher):
        svc = PaymentEventService(db)
        payload = self._make_payload(f"pay_{uuid4().hex[:16]}")
        result = await svc.ingest_from_razorpay(payload)
        assert result["status"] == "accepted"
        assert result["failure_category"] == FailureCause.TEMPORARY_FAILURE

    @pytest.mark.asyncio
    async def test_empty_payload_returns_skipped(self, db, mock_publisher):
        svc = PaymentEventService(db)
        result = await svc.ingest_from_razorpay({"event": "order.paid", "payload": {}})
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_amount_converted_from_paise(self, db, mock_publisher):
        """Razorpay sends amounts in paise (1/100 rupee); must be divided by 100."""
        svc = PaymentEventService(db)
        payload = self._make_payload(f"pay_{uuid4().hex[:16]}")
        payload["payload"]["payment"]["entity"]["amount"] = 100000  # 1000 INR in paise
        result = await svc.ingest_from_razorpay(payload)
        # Verify stored amount — query the DB
        from app.repositories.payment_event import PaymentEventRepository
        repo = PaymentEventRepository(db)
        event = await repo.get_by_payment_id(result["payment_id"])
        assert event.amount == Decimal("1000.00")
