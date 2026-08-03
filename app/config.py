import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    app_log_level: str = os.getenv("APP_LOG_LEVEL", "INFO")
    oracle_user: str = os.getenv("CDC_APP_USER", "CDC_APP")
    oracle_password: Optional[str] = os.getenv("CDC_APP_PASSWORD")
    oracle_dsn: str = os.getenv("CDC_APP_DSN", "localhost:1521/FREEPDB1")
    clickhouse_host: str = os.getenv("CLICKHOUSE_HOST", "localhost")
    clickhouse_http_port: int = int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))
    clickhouse_database: str = os.getenv("CLICKHOUSE_DATABASE", "analytics")
    clickhouse_user: str = os.getenv("CLICKHOUSE_USER", "default")
    clickhouse_password: Optional[str] = os.getenv("CLICKHOUSE_PASSWORD")


def get_settings() -> Settings:
    return Settings()
