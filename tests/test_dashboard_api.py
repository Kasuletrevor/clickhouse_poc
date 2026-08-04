from fastapi.testclient import TestClient

from app.clickhouse import AnalyticsUnavailableError
from app.main import create_app


class FakeDashboardService:
    def summary(self):
        return {
            "total_taxpayers": 3,
            "total_stations": 3,
            "payments_today": 47,
            "amount_collected_today": 41250000,
            "refreshed_at": "2026-08-02T16:00:00+00:00",
        }

    def payments_by_station(self):
        return [{"station_name": "Jinja", "payment_count": 20, "successful_amount": 16000000}]

    def status_summary(self):
        return [
            {"status": "SUCCESSFUL", "payment_count": 44, "amount": 40000000},
            {"status": "PENDING", "payment_count": 3, "amount": 1250000},
            {"status": "REVERSED", "payment_count": 0, "amount": 0},
        ]

    def recent_activity(self):
        return {
            "recent_payments": [{"payment_id": "PAY103", "status": "SUCCESSFUL"}],
            "recent_taxpayer_activity": [{"taxpayer_id": "TIN003", "action": "Station changed"}],
        }


class FailingDashboardService(FakeDashboardService):
    def summary(self):
        raise AnalyticsUnavailableError("secret host detail")


def client(service=None):
    return TestClient(create_app(dashboard_service=service or FakeDashboardService()))


def test_dashboard_endpoints_return_analytical_payloads():
    c = client()

    summary = c.get("/api/dashboard/summary")
    stations = c.get("/api/dashboard/payments-by-station")
    statuses = c.get("/api/dashboard/status-summary")
    activity = c.get("/api/dashboard/recent-activity")

    assert summary.status_code == 200
    assert summary.json()["amount_collected_today"] == 41250000
    assert stations.json()[0]["station_name"] == "Jinja"
    assert statuses.json()[0]["status"] == "SUCCESSFUL"
    assert activity.json()["recent_taxpayer_activity"][0]["action"] == "Station changed"


def test_clickhouse_unavailable_returns_safe_dashboard_error():
    response = client(FailingDashboardService()).get("/api/dashboard/summary")

    assert response.status_code == 503
    assert response.json() == {
        "error": "analytics_unavailable",
        "message": "Dashboard analytics are temporarily unavailable.",
    }
    assert "secret" not in response.text
