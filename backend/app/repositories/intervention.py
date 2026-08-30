"""
Intervention Repository — DB access for Intervention entities.
"""
from uuid import UUID
from sqlalchemy import select
from app.models.recovery import Intervention
from app.repositories.base import BaseRepository


class InterventionRepository(BaseRepository[Intervention]):
    model = Intervention

    async def get_by_decision_id(self, decision_id: UUID) -> list[Intervention]:
        result = await self.db.execute(
            select(Intervention).where(Intervention.decision_id == str(decision_id))
        )
        return list(result.scalars().all())
