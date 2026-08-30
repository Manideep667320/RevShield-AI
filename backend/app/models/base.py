"""
Shared ORM base and mixins.
All models inherit from Base. Timestamps are automatic.
"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import uuid
from sqlalchemy.types import JSON, Text, CHAR, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, UUID as PG_UUID

JSONType = JSON().with_variant(JSONB(), "postgresql")
ArrayType = JSON().with_variant(ARRAY(Text()), "postgresql")


class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses PostgreSQL's UUID type on Postgres, CHAR(36) on SQLite.
    Accepts both str and uuid.UUID inputs seamlessly.
    """
    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value if dialect.name == "postgresql" else str(value)
        try:
            val_uuid = uuid.UUID(str(value))
            return val_uuid if dialect.name == "postgresql" else str(val_uuid)
        except (ValueError, AttributeError):
            return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError):
            return value


UUIDType = GUID


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    """Provides a UUID primary key generated server-side."""
    id: Mapped[str]  # overridden in each model with actual column name


class TimestampMixin:
    """Auto-managed created_at / updated_at timestamps."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
