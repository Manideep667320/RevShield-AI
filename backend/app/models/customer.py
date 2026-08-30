from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, UUIDType, ArrayType


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=uuid4)
    merchant_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("merchants.merchant_id"), nullable=False)
    historical_payment_count: Mapped[int] = mapped_column(Integer, default=0)
    successful_payment_count: Mapped[int] = mapped_column(Integer, default=0)
    average_transaction_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    preferred_payment_methods: Mapped[list] = mapped_column(ArrayType, default=list)
    last_successful_payment: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.5)

    merchant: Mapped["Merchant"] = relationship(back_populates="customers")
    payment_events: Mapped[list["PaymentEvent"]] = relationship(back_populates="customer")
