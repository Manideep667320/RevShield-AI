"""
Customer repository — DB access for Customer entities.
"""
from uuid import UUID
from sqlalchemy import select
from app.models.customer import Customer
from app.repositories.base import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    model = Customer

    async def get_by_merchant(self, merchant_id: UUID) -> list[Customer]:
        return await self.list(Customer.merchant_id == str(merchant_id))

    async def increment_payment_stats(
        self, customer_id: UUID, *, success: bool
    ) -> None:
        """Atomically increment historical + optional success counters."""
        from sqlalchemy import update
        from app.models.customer import Customer as C
        cols = {C.historical_payment_count: C.historical_payment_count + 1}
        if success:
            cols[C.successful_payment_count] = C.successful_payment_count + 1
        await self.db.execute(
            update(C).where(C.customer_id == str(customer_id)).values(cols)
        )
