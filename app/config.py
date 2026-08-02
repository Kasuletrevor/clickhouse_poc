from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    app_log_level: str = os.getenv("APP_LOG_LEVEL", "INFO")
    oracle_user: str = os.getenv("CDC_APP_USER", "CDC_APP")
    oracle_password: str | None = os.getenv("CDC_APP_PASSWORD")
    oracle_dsn: str = os.getenv("CDC_APP_DSN", "localhost:1521/FREEPDB1")


def get_settings() -> Settings:
    return Settings()
