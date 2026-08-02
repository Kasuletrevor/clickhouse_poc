from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

PaymentStatus = Literal["PENDING", "SUCCESSFUL", "REVERSED"]


class PaymentCreate(BaseModel):
    payment_id: Optional[str] = Field(default=None, max_length=20)
    taxpayer_id: str = Field(min_length=1, max_length=20)
    amount: Decimal = Field(gt=0)
    status: PaymentStatus = "PENDING"

    @field_validator("payment_id", "taxpayer_id")
    @classmethod
    def normalize_identifiers(cls, value):
        if value is None:
            return value
        return value.strip().upper()


class PaymentStatusUpdate(BaseModel):
    status: PaymentStatus
