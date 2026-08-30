"""
Audit Log Repository — DB access for AuditLog entities.
"""
from uuid import UUID
from sqlalchemy import select
from app.models.audit import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    model = AuditLog

    async def list_by_entity(
        self, entity_type: str, entity_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[AuditLog]:
        return await self.list(
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == str(entity_id),
            limit=limit,
            offset=offset,
        )
