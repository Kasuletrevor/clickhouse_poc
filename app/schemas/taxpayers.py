from pydantic import BaseModel, Field, field_validator


class TaxpayerCreate(BaseModel):
    taxpayer_id: str = Field(min_length=1, max_length=30)
    taxpayer_name: str = Field(min_length=1, max_length=200)
    taxpayer_type: str = Field(min_length=1, max_length=50)
    station_id: str = Field(min_length=1, max_length=30)

    @field_validator("taxpayer_id", "taxpayer_type", "station_id")
    @classmethod
    def normalize_codes(cls, value):
        return value.strip().upper()

    @field_validator("taxpayer_name")
    @classmethod
    def normalize_name(cls, value):
        return value.strip()


class TaxpayerUpdate(BaseModel):
    taxpayer_name: str = Field(min_length=1, max_length=200)
    taxpayer_type: str = Field(min_length=1, max_length=50)
    station_id: str = Field(min_length=1, max_length=30)

    @field_validator("taxpayer_type", "station_id")
    @classmethod
    def normalize_codes(cls, value):
        return value.strip().upper()

    @field_validator("taxpayer_name")
    @classmethod
    def normalize_name(cls, value):
        return value.strip()
