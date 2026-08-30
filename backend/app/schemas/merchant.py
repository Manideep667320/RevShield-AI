from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class MerchantBase(BaseModel):
    name: str
    currency: str = "INR"
    recovery_policy: dict = Field(default_factory=dict)


class MerchantCreate(MerchantBase):
    pass


class MerchantRead(MerchantBase):
    merchant_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
