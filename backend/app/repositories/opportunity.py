"""
Recovery Opportunity Repository — DB access for RecoveryOpportunity entities.
"""
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.recovery import RecoveryOpportunity
from app.repositories.base import BaseRepository


class RecoveryOpportunityRepository(BaseRepository[RecoveryOpportunity]):
    model = RecoveryOpportunity

    async def get_by_payment_id(self, payment_id: str) -> RecoveryOpportunity | None:
        result = await self.db.execute(
            select(RecoveryOpportunity).where(RecoveryOpportunity.payment_id == payment_id)
        )
        return result.scalar_one_or_none()

    async def list_opportunities(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RecoveryOpportunity]:
        stmt = select(RecoveryOpportunity)
        if status:
            stmt = stmt.where(RecoveryOpportunity.status == status)
        if priority:
            stmt = stmt.where(RecoveryOpportunity.priority == priority)
        stmt = stmt.order_by(RecoveryOpportunity.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_idempotent(
        self, opportunity: RecoveryOpportunity
    ) -> tuple[RecoveryOpportunity, bool]:
        """
        Returns (opportunity, created). If an opportunity for payment_id already exists,
        returns existing record without creating duplicate.
        """
        existing = await self.get_by_payment_id(opportunity.payment_id)
        if existing:
            return existing, False
        try:
            created = await self.create(opportunity)
            return created, True
        except IntegrityError:
            await self.db.rollback()
    async def update_status(self, opportunity_id: UUID, new_status: str) -> RecoveryOpportunity | None:
        opp = await self.get(opportunity_id)
        if opp:
            opp.status = new_status
            await self.db.commit()
            await self.db.refresh(opp)
        return opp
