from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class EfrisErrorCreate(BaseModel):
    tin: str = Field(min_length=1, max_length=20)
    device_no: str = Field(min_length=1, max_length=50)
    seller_reference_no: Optional[str] = Field(default=None, max_length=50)
    return_code: str = Field(min_length=1, max_length=8)
    return_msg: str = Field(min_length=1, max_length=256)
    gross_amount: Decimal = Field(gt=0)
    tax_amount: Decimal = Field(ge=0)
    currency: str = Field(default="UGX", min_length=1, max_length=10)
    item_description: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("tin", "device_no", "seller_reference_no", "return_code", "currency")
    @classmethod
    def normalize_identifiers(cls, value):
        if value is None:
            return value
        return value.strip().upper()

    @field_validator("return_msg", "item_description")
    @classmethod
    def normalize_text(cls, value):
        if value is None:
            return value
        return value.strip()
