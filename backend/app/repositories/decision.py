"""
Recovery Decision Repository — DB access for RecoveryDecision entities.
"""
from uuid import UUID
from sqlalchemy import select
from app.models.recovery import RecoveryDecision
from app.repositories.base import BaseRepository


class RecoveryDecisionRepository(BaseRepository[RecoveryDecision]):
    model = RecoveryDecision

    async def get_by_opportunity_id(self, opportunity_id: UUID | str) -> RecoveryDecision | None:
        opp_str = str(opportunity_id)
        result = await self.db.execute(
            select(RecoveryDecision).where(
                (RecoveryDecision.opportunity_id == opp_str) | (RecoveryDecision.opportunity_id == UUID(opp_str))
            )
        )
        return result.scalars().first()
