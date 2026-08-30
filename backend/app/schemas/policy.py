from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field


class PolicyBase(BaseModel):
    merchant_id: UUID
    max_retry_count: int = Field(2, ge=0, le=10)
    max_discount_pct: Decimal = Field(Decimal("5.00"), ge=0, le=100)
    allowed_channels: list[str] = Field(default_factory=lambda: ["RETRY", "PAYMENT_LINK", "REMINDER"])
    approval_threshold: Decimal = Field(Decimal("25000.00"), ge=0)
    max_intervention_cost: Decimal = Field(Decimal("50.00"), ge=0)
    active: bool = True
    version: int = 1


class PolicyCreate(PolicyBase):
    pass


class PolicyRead(PolicyBase):
    policy_id: UUID

    model_config = {"from_attributes": True}


class PolicyUpdate(BaseModel):
    """Partial update — only include fields that change."""
    max_retry_count: int | None = None
    max_discount_pct: Decimal | None = None
    allowed_channels: list[str] | None = None
    approval_threshold: Decimal | None = None
    max_intervention_cost: Decimal | None = None
