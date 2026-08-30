from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, Numeric, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, UUIDType, JSONType


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        Index("ix_payment_events_payment_id", "payment_id", unique=True),
        Index("ix_payment_events_merchant_id", "merchant_id"),
        Index("ix_payment_events_customer_id", "customer_id"),
        Index("ix_payment_events_timestamp", "timestamp"),
    )

    event_id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=uuid4)
    merchant_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("merchants.merchant_id"))
    customer_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("customers.customer_id"))
    payment_id: Mapped[str] = mapped_column(Text, nullable=False)       # Razorpay ID — idempotency key
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, default="INR")
    payment_method: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)      # raw Razorpay code
    failure_category: Mapped[str | None] = mapped_column(Text, nullable=True)  # mapped taxonomy
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)

    customer: Mapped["Customer"] = relationship(back_populates="payment_events")
