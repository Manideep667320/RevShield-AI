"""
Customer History Feature Extractor Service — Phase 3
Extracts historical behavior signals and recent failure codes for a customer.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.customer import Customer
from app.models.payment_event import PaymentEvent
from app.repositories.customer import CustomerRepository
from app.schemas.agents import CustomerHistory

logger = get_logger(__name__)


class CustomerHistoryService:
    """Extracts CustomerHistory feature vector from DB for Diagnosis Agent."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.customer_repo = CustomerRepository(db)

    async def get_customer_history(self, customer_id: UUID) -> CustomerHistory:
        """Fetches customer record + recent payment events to build CustomerHistory."""
        customer = await self.customer_repo.get(customer_id)

        if not customer:
            logger.info(f"message=Customer not found for history extraction | customer_id={customer_id}")
            return CustomerHistory(
                customer_id=customer_id,
                total_payments=0,
                successful_payments=0,
                recent_failure_codes=[],
                days_since_last_success=None,
            )

        # Query last 5 payment events for customer
        stmt = (
            select(PaymentEvent.failure_code)
            .where(
                PaymentEvent.customer_id == str(customer_id),
                PaymentEvent.failure_code.isnot(None),
            )
            .order_by(PaymentEvent.timestamp.desc())
            .limit(5)
        )
        result = await self.db.execute(stmt)
        recent_codes = [code for code in result.scalars().all() if code]

        days_since_last: int | None = None
        if customer.last_successful_payment:
            last_dt = customer.last_successful_payment
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            days_since_last = max(0, (datetime.now(tz=timezone.utc) - last_dt).days)

        return CustomerHistory(
            customer_id=customer_id,
            total_payments=customer.historical_payment_count,
            successful_payments=customer.successful_payment_count,
            recent_failure_codes=recent_codes,
            days_since_last_success=days_since_last,
        )
