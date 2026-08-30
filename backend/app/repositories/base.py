"""
Generic async repository base — provides standard CRUD that all entity repos inherit.
Eliminates repeated DB boilerplate across all repository classes.
"""
from typing import Generic, TypeVar
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, pk: UUID) -> ModelT | None:
        return await self.db.get(self.model, pk)

    async def get_or_raise(self, pk: UUID) -> ModelT:
        from app.core.exceptions import NotFoundError
        obj = await self.get(pk)
        if not obj:
            raise NotFoundError(f"{self.model.__tablename__} {pk} not found")
        return obj

    async def create(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        await self.db.flush()   # get PK without committing
        await self.db.refresh(obj)
        return obj

    async def list(self, *filters, limit: int = 50, offset: int = 0) -> list[ModelT]:
        stmt = select(self.model).where(*filters).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
