from typing import Callable

import httpx

from app.config import Settings


class AnalyticsUnavailableError(RuntimeError):
    pass


class AnalyticsOperationError(RuntimeError):
    pass


class ClickHouseDatabase:
    def __init__(self, settings: Settings, client_factory: Callable = httpx.Client):
        self.settings = settings
        self.client_factory = client_factory

    def query(self, sql: str):
        statement = sql.strip().rstrip(";") + "\nFORMAT JSON"
        url = "http://{}:{}/".format(
            self.settings.clickhouse_host,
            self.settings.clickhouse_http_port,
        )
        auth = None
        if self.settings.clickhouse_user:
            auth = (
                self.settings.clickhouse_user,
                self.settings.clickhouse_password or "",
            )

        try:
            with self.client_factory(timeout=5.0) as client:
                response = client.post(
                    url,
                    params={"database": self.settings.clickhouse_database},
                    content=statement,
                    auth=auth,
                )
            response.raise_for_status()
        except httpx.RequestError as exc:
            raise AnalyticsUnavailableError("ClickHouse analytics is unavailable.") from exc
        except httpx.HTTPStatusError as exc:
            raise AnalyticsOperationError("ClickHouse analytics query failed.") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise AnalyticsOperationError("ClickHouse returned an invalid response.") from exc

        data = payload.get("data")
        if not isinstance(data, list):
            raise AnalyticsOperationError("ClickHouse response did not contain data rows.")
        return data
