from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field
from app.schemas.enums import PaymentMethod


class CustomerBase(BaseModel):
    merchant_id: UUID
    historical_payment_count: int = 0
    successful_payment_count: int = 0
    average_transaction_value: Decimal = Decimal("0.00")
    preferred_payment_methods: list[PaymentMethod] = Field(default_factory=list)
    last_successful_payment: datetime | None = None
    risk_score: float = Field(0.5, ge=0.0, le=1.0)


class CustomerCreate(CustomerBase):
    pass


class CustomerRead(CustomerBase):
    customer_id: UUID

    model_config = {"from_attributes": True}


class CustomerContext(BaseModel):
    """Lightweight customer context passed to agents — avoids full customer object."""
    customer_id: UUID
    historical_payment_count: int
    successful_payment_count: int
    average_transaction_value: Decimal
    risk_score: float
    last_successful_payment: datetime | None = None

    @property
    def success_rate(self) -> float:
        if self.historical_payment_count == 0:
            return 0.0
        return self.successful_payment_count / self.historical_payment_count
