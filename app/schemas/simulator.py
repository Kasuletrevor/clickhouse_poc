from pydantic import BaseModel, Field


class SimulatorStartRequest(BaseModel):
    rate: float = Field(default=14.0, gt=0, le=1000)
    duration_seconds: int = Field(default=600, ge=0, le=86400)
    retry_probability: float = Field(default=0.12, ge=0, le=1)
