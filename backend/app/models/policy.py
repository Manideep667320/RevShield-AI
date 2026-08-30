from decimal import Decimal
from uuid import uuid4
from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, UUIDType, ArrayType


class Policy(Base):
    __tablename__ = "policies"

    policy_id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=uuid4)
    merchant_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("merchants.merchant_id"))
    max_retry_count: Mapped[int] = mapped_column(Integer, default=2)
    max_discount_pct: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("5.00"))
    allowed_channels: Mapped[list] = mapped_column(ArrayType, default=list)
    approval_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("25000.00"))
    max_intervention_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("50.00"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    merchant: Mapped["Merchant"] = relationship(back_populates="policies")
