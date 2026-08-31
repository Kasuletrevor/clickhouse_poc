from pydantic import BaseModel, Field


class StreamingPocStartRequest(BaseModel):
    rate: float = Field(gt=0, le=1000)
    duration_seconds: int = Field(ge=0, le=86400)
