from uuid import uuid4
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDType, JSONType


class Merchant(Base, TimestampMixin):
    __tablename__ = "merchants"

    merchant_id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    recovery_policy: Mapped[dict] = mapped_column(JSONType, default=dict)

    customers: Mapped[list["Customer"]] = relationship(back_populates="merchant")
    policies: Mapped[list["Policy"]] = relationship(back_populates="merchant")
