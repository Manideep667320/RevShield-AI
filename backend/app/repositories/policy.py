"""
Policy Repository — DB access for Policy entities.
"""
from uuid import UUID
from sqlalchemy import select
from app.models.policy import Policy
from app.repositories.base import BaseRepository


class PolicyRepository(BaseRepository[Policy]):
    model = Policy

    async def get_by_merchant_id(self, merchant_id: UUID) -> Policy | None:
        result = await self.db.execute(
            select(Policy).where(Policy.merchant_id == str(merchant_id), Policy.active.is_(True))
        )
        return result.scalar_one_or_none()
