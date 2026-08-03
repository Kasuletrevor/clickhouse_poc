import httpx
import pytest

from app.clickhouse import AnalyticsOperationError, AnalyticsUnavailableError, ClickHouseDatabase
from app.config import Settings


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"data": []}
        self.request = httpx.Request("POST", "http://localhost:8123/")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "clickhouse failed",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, response=None, error=None, calls=None, **_kwargs):
        self.response = response or FakeResponse(payload={"data": [{"value": 1}]})
        self.error = error
        self.calls = calls if calls is not None else []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, params=None, content=None, auth=None):
        self.calls.append({"url": url, "params": params, "content": content, "auth": auth})
        if self.error:
            raise self.error
        return self.response


def settings():
    return Settings(
        oracle_user="CDC_APP",
        oracle_password="unused",
        oracle_dsn="unused",
        clickhouse_host="localhost",
        clickhouse_http_port=8123,
        clickhouse_database="analytics",
        clickhouse_user="kjt",
        clickhouse_password="secret",
    )


def test_query_returns_clickhouse_json_data():
    calls = []
    db = ClickHouseDatabase(settings(), client_factory=lambda **kw: FakeClient(calls=calls, **kw))

    rows = db.query("SELECT 1 AS value")

    assert rows == [{"value": 1}]
    assert calls[0]["params"] == {"database": "analytics"}
    assert calls[0]["auth"] == ("kjt", "secret")
    assert calls[0]["content"].endswith("FORMAT JSON")


def test_network_failure_becomes_analytics_unavailable():
    error = httpx.ConnectError("connection refused", request=httpx.Request("POST", "http://localhost:8123/"))
    db = ClickHouseDatabase(settings(), client_factory=lambda **kw: FakeClient(error=error, **kw))

    with pytest.raises(AnalyticsUnavailableError):
        db.query("SELECT 1")


def test_bad_clickhouse_response_becomes_safe_operation_error():
    db = ClickHouseDatabase(
        settings(),
        client_factory=lambda **kw: FakeClient(response=FakeResponse(status_code=500), **kw),
    )

    with pytest.raises(AnalyticsOperationError):
        db.query("SELECT broken")
