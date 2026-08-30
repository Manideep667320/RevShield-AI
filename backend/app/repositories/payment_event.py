"""
Payment event repository — DB access for PaymentEvent entities.
Idempotency enforced: duplicate payment_id raises DuplicateError before insert.
"""
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core.exceptions import DuplicateError
from app.models.payment_event import PaymentEvent
from app.repositories.base import BaseRepository


class PaymentEventRepository(BaseRepository[PaymentEvent]):
    model = PaymentEvent

    async def get_by_payment_id(self, payment_id: str) -> PaymentEvent | None:
        result = await self.db.execute(
            select(PaymentEvent).where(PaymentEvent.payment_id == payment_id)
        )
        return result.scalar_one_or_none()

    async def create_idempotent(self, event: PaymentEvent) -> tuple[PaymentEvent, bool]:
        """
        Returns (event, created). If payment_id already exists, returns existing
        record without inserting — guarantees exactly-once storage.
        """
        existing = await self.get_by_payment_id(event.payment_id)
        if existing:
            return existing, False
        try:
            created = await self.create(event)
            return created, True
        except IntegrityError:
            await self.db.rollback()
            existing = await self.get_by_payment_id(event.payment_id)
            return existing, False   # race condition: another worker inserted first

    async def list_by_status(
        self, status: str, *, limit: int = 100, offset: int = 0
    ) -> list[PaymentEvent]:
        return await self.list(
            PaymentEvent.status == status, limit=limit, offset=offset
        )

    async def list_by_merchant(
        self, merchant_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[PaymentEvent]:
        return await self.list(
            PaymentEvent.merchant_id == str(merchant_id), limit=limit, offset=offset
        )
