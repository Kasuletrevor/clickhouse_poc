from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from secrets import choice
from string import ascii_uppercase, digits

ACTIVE_STATUSES = {"starting", "running", "paused", "draining"}
SOURCE_ACTIVE_STATUSES = {"starting", "running", "paused"}
FINAL_STATUSES = {"completed", "failed", "stale"}
VALID_STATUSES = ACTIVE_STATUSES | FINAL_STATUSES
VALID_COMMANDS = {"run", "pause", "stop"}


@dataclass(frozen=True)
class RunConfig:
    rate: float
    duration_seconds: int
    retry_probability: float
    random_seed: int

    def __post_init__(self):
        if self.rate <= 0:
            raise ValueError("rate must be greater than zero")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")
        if not 0 <= self.retry_probability <= 1:
            raise ValueError("retry_probability must be between 0 and 1")

    @property
    def target_events(self) -> int | None:
        if self.duration_seconds == 0:
            return None
        return round(self.rate * self.duration_seconds)


@dataclass
class RunRecord:
    run_id: str
    source_prefix: str
    status: str
    command: str
    rate: float
    duration_seconds: int
    target_events: int | None
    retry_probability: float
    random_seed: int
    pid: int | None = None
    generated: int = 0
    failures: int = 0
    last_sequence: int = 0
    active_elapsed_seconds: float = 0.0
    paused_seconds: float = 0.0
    started_at: str | None = None
    finished_at: str | None = None
    last_heartbeat: str | None = None
    source_rate_samples: list[dict] = field(default_factory=list)
    error: str | None = None

    def __post_init__(self):
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid simulator status: {self.status}")
        if self.command not in VALID_COMMANDS:
            raise ValueError(f"Invalid simulator command: {self.command}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "RunRecord":
        current_fields = {item.name for item in fields(cls)}
        compatible_payload = {
            key: value
            for key, value in payload.items()
            if key in current_fields
        }
        return cls(**compatible_payload)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_run_identity(now: datetime | None = None, token: str | None = None) -> tuple[str, str]:
    now = now or datetime.now(timezone.utc)
    token = (token or "".join(choice(ascii_uppercase + digits) for _ in range(2))).upper()
    if len(token) != 2 or any(ch not in ascii_uppercase + digits for ch in token):
        raise ValueError("token must contain exactly two A-Z/0-9 characters")
    run_id = f"EFR-{now:%Y%m%d-%H%M%S}-{token}"
    source_prefix = f"S{now:%y%m%d}{token}"
    return run_id, source_prefix
