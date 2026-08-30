"""
Merchant repository — DB access for Merchant entities.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.merchant import Merchant
from app.repositories.base import BaseRepository


class MerchantRepository(BaseRepository[Merchant]):
    model = Merchant

    async def get_by_name(self, name: str) -> Merchant | None:
        result = await self.db.execute(select(Merchant).where(Merchant.name == name))
        return result.scalar_one_or_none()
