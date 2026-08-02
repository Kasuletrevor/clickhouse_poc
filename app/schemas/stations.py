from pydantic import BaseModel, Field, field_validator


class StationCreate(BaseModel):
    station_id: str = Field(min_length=1, max_length=20)
    station_name: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=50)
    district: str = Field(min_length=1, max_length=50)

    @field_validator("station_id")
    @classmethod
    def normalize_station_id(cls, value):
        return value.strip().upper()

    @field_validator("station_name", "region", "district")
    @classmethod
    def normalize_text(cls, value):
        return value.strip()


class StationUpdate(BaseModel):
    station_name: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=50)
    district: str = Field(min_length=1, max_length=50)

    @field_validator("station_name", "region", "district")
    @classmethod
    def normalize_text(cls, value):
        return value.strip()
