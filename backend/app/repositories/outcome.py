"""
Recovery Outcome Repository — DB access for RecoveryOutcome entities.
"""
from uuid import UUID
from sqlalchemy import select, func
from app.models.recovery import RecoveryOutcome
from app.repositories.base import BaseRepository


class RecoveryOutcomeRepository(BaseRepository[RecoveryOutcome]):
    model = RecoveryOutcome

    async def get_by_intervention_id(self, intervention_id: UUID) -> list[RecoveryOutcome]:
        result = await self.db.execute(
            select(RecoveryOutcome).where(RecoveryOutcome.intervention_id == str(intervention_id))
        )
        return list(result.scalars().all())

    async def get_total_recovered_amount(self) -> float:
        result = await self.db.execute(
            select(func.coalesce(func.sum(RecoveryOutcome.recovered_amount), 0.0))
        )
        return float(result.scalar_one())

    async def get_total_incremental_recovery(self) -> float:
        result = await self.db.execute(
            select(func.coalesce(func.sum(RecoveryOutcome.incremental_recovery), 0.0))
        )
        return float(result.scalar_one())
