from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import AliasChoices, BaseModel, Field
from app.schemas.enums import FailureCause, PaymentMethod


class PaymentEventBase(BaseModel):
    merchant_id: UUID
    customer_id: UUID
    payment_id: str = Field(..., description="Razorpay payment ID — used as idempotency key")
    amount: Decimal
    currency: str = "INR"
    payment_method: PaymentMethod
    status: str
    failure_code: str | None = None          # raw Razorpay code
    failure_category: FailureCause | None = None  # mapped internal taxonomy
    metadata: dict = Field(default_factory=dict, validation_alias=AliasChoices("metadata_", "metadata"))


class PaymentEventCreate(PaymentEventBase):
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaymentEventRead(PaymentEventBase):
    event_id: UUID
    timestamp: datetime

    model_config = {"from_attributes": True}


class RazorpayWebhookPayload(BaseModel):
    """Inbound Razorpay webhook payload — only relevant fields extracted."""
    entity: str
    account_id: str
    event: str
    payload: dict
    created_at: int  # Unix timestamp from Razorpay


class SimulatePaymentRequest(BaseModel):
    """Used by /api/v1/payments/simulate for synthetic event injection."""
    merchant_id: UUID
    customer_id: UUID
    amount: Decimal = Field(..., gt=0)
    currency: str = "INR"
    payment_method: PaymentMethod = PaymentMethod.CARD
    failure_code: str = "GATEWAY_ERROR"
    metadata: dict = Field(default_factory=dict)
