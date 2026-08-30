"""
Payment Event Service — orchestrates the full ingestion pipeline:
  parse → classify → store (idempotent) → enqueue

This is the ONLY entry point for creating payment events. All callers
(webhook handler, simulate endpoint, seed scripts) go through this service.
"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import get_logger
from app.models.payment_event import PaymentEvent
from app.repositories.payment_event import PaymentEventRepository
from app.models.merchant import Merchant
from app.models.customer import Customer
from app.repositories.customer import CustomerRepository
from app.repositories.merchant import MerchantRepository
from app.schemas.payment_event import PaymentEventRead, SimulatePaymentRequest
from app.services.taxonomy import classify_failure_code, TaxonomyEntry
from app.services.event_queue import get_publisher

logger = get_logger(__name__)

# Failed statuses that trigger recovery pipeline
FAILED_STATUSES = {"failed", "payment.failed", "payment_failed"}


class PaymentEventService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PaymentEventRepository(db)
        self.customer_repo = CustomerRepository(db)
        self.merchant_repo = MerchantRepository(db)
        self.publisher = get_publisher()

    async def _ensure_merchant_and_customer(self, merchant_id_str: str, customer_id_str: str) -> tuple[str, str]:
        """Ensures merchant and customer records exist in DB for FK constraints."""
        from uuid import UUID
        m_id = UUID(merchant_id_str) if isinstance(merchant_id_str, str) else merchant_id_str
        c_id = UUID(customer_id_str) if isinstance(customer_id_str, str) else customer_id_str

        m = await self.merchant_repo.get(m_id)
        if not m:
            m = Merchant(
                merchant_id=str(m_id),
                name="TechFlow SaaS",
                currency="INR",
                recovery_policy={"max_retry_count": 2, "approval_threshold": 25000, "allowed_channels": ["RETRY", "PAYMENT_LINK", "REMINDER", "HUMAN_ESCALATION"]},
            )
            self.db.add(m)
            await self.db.flush()

        c = await self.customer_repo.get(c_id)
        if not c:
            from decimal import Decimal
            c = Customer(
                customer_id=str(c_id),
                merchant_id=str(m_id),
                historical_payment_count=5,
                successful_payment_count=4,
                average_transaction_value=Decimal("15000.00"),
                risk_score=0.2,
            )
            self.db.add(c)
            await self.db.flush()

        return str(m_id), str(c_id)

    async def ingest_from_razorpay(self, payload: dict) -> dict:
        """
        Entry point for Razorpay webhooks.
        Extracts, normalises, classifies, stores, enqueues.
        Returns pipeline result summary.
        """
        event_type: str = payload.get("event", "")
        payment_data: dict = payload.get("payload", {}).get("payment", {}).get("entity", {})

        if not payment_data:
            logger.info(f"message=Webhook skipped | event={event_type} | reason=no_payment_entity")
            return {"status": "skipped", "reason": "no payment entity in payload"}

        payment_id = payment_data.get("id", f"rzp_{uuid4().hex[:16]}")
        failure_code = payment_data.get("error_code") or payment_data.get("error_reason")
        taxonomy: TaxonomyEntry = classify_failure_code(failure_code)

        event = PaymentEvent(
            event_id=uuid4(),
            merchant_id=payment_data.get("merchant_id"),
            customer_id=payment_data.get("customer_id") or payment_data.get("contact"),
            payment_id=payment_id,
            amount=payment_data.get("amount", 0) / 100,   # Razorpay uses paise
            currency=payment_data.get("currency", "INR"),
            payment_method=_normalise_method(payment_data.get("method", "other")),
            status=payment_data.get("status", "failed"),
            failure_code=failure_code,
            failure_category=taxonomy.internal_cause.value,
            timestamp=datetime.now(tz=timezone.utc),
            metadata_={"raw_event": event_type, "taxonomy": taxonomy.notes},
        )

        return await self._persist_and_enqueue(event)

    async def ingest_simulated(self, req: SimulatePaymentRequest) -> dict:
        """Entry point for synthetic test events injected via /simulate endpoint."""
        m_id, c_id = await self._ensure_merchant_and_customer(str(req.merchant_id), str(req.customer_id))
        taxonomy: TaxonomyEntry = classify_failure_code(req.failure_code)
        event = PaymentEvent(
            event_id=uuid4(),
            merchant_id=m_id,
            customer_id=c_id,
            payment_id=f"sim_{uuid4().hex[:16]}",
            amount=req.amount,
            currency=req.currency,
            payment_method=req.payment_method.value,
            status="failed",
            failure_code=req.failure_code,
            failure_category=taxonomy.internal_cause.value,
            timestamp=datetime.now(tz=timezone.utc),
            metadata_={"simulated": True, **req.metadata},
        )
        return await self._persist_and_enqueue(event)

    async def _persist_and_enqueue(self, event: PaymentEvent) -> dict:
        """
        Idempotent store + conditional enqueue.
        Only failed events are enqueued for recovery processing.
        """
        stored_event, created = await self.repo.create_idempotent(event)

        if not created:
            logger.info(f"message=Duplicate event skipped | payment_id={event.payment_id}")
            return {"status": "duplicate", "payment_id": event.payment_id}

        # Update customer payment stats atomically
        if stored_event.customer_id:
            await self.customer_repo.increment_payment_stats(
                stored_event.customer_id,
                success=(stored_event.status == "captured"),
            )

        # Only enqueue failed payments for recovery processing
        stream_id = None
        if stored_event.status.lower() in FAILED_STATUSES:
            stream_id = await self.publisher.publish_payment_event(
                event_id=stored_event.event_id,
                payment_id=stored_event.payment_id,
                payload={
                    "merchant_id": str(stored_event.merchant_id),
                    "customer_id": str(stored_event.customer_id),
                    "amount": str(stored_event.amount),
                    "currency": stored_event.currency,
                    "failure_category": stored_event.failure_category,
                },
            )

        logger.info(
            f"message=Payment event ingested | payment_id={stored_event.payment_id} "
            f"| category={stored_event.failure_category} | queued={stream_id is not None}"
        )
        return {
            "status": "accepted",
            "event_id": str(stored_event.event_id),
            "payment_id": stored_event.payment_id,
            "failure_category": stored_event.failure_category,
            "queued": stream_id is not None,
            "stream_id": stream_id,
        }


def _normalise_method(raw: str) -> str:
    """Maps Razorpay payment method strings to internal PaymentMethod enum values."""
    _map = {"card": "CARD", "upi": "UPI", "netbanking": "NETBANKING",
            "wallet": "WALLET", "emi": "EMI"}
    return _map.get(raw.lower(), "OTHER")
