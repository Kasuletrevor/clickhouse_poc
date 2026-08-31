from pydantic import BaseModel, Field, model_validator


class StreamingPocStartRequest(BaseModel):
    rate: float = Field(gt=0, le=1000)
    duration_seconds: int = Field(ge=0, le=86400)
    payment_create_pct: float = Field(default=80.0, ge=0, le=100)
    status_update_pct: float = Field(default=15.0, ge=0, le=100)
    taxpayer_move_pct: float = Field(default=5.0, ge=0, le=100)

    @model_validator(mode="after")
    def validate_mix_total(self):
        total = self.payment_create_pct + self.status_update_pct + self.taxpayer_move_pct
        if abs(total - 100.0) > 1e-6:
            raise ValueError("Traffic mix percentages must total 100")
        return self
