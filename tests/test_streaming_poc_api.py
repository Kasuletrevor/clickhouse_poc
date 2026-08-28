from fastapi.testclient import TestClient

from app.main import create_app
from app.services.payments import PaymentService


class EmptyPaymentRepo:
    def list_payments(self, **kwargs): return [], 0
    def payment_summary(self): return {"payments_today": 0, "successful": 0, "pending": 0, "reversed": 0, "amount_today": 0}
    def get_payment(self, payment_id): return None
    def taxpayer_context(self, taxpayer_id): return None
    def payment_exists(self, payment_id): return False
    def create_payment(self, *args): raise AssertionError("not used")
    def update_status(self, *args): return False


class FakeStreamingPocService:
    def status(self):
        return {
            "state": "idle",
            "active": None,
            "health": {
                "oracle": {"status": "healthy", "detail": "Source reachable"},
                "debezium": {"status": "healthy", "detail": "Connector RUNNING"},
                "kafka": {"status": "healthy", "detail": "Broker reachable"},
                "clickhouse": {"status": "healthy", "detail": "Analytics reachable"},
            },
            "recent_events": [],
        }

    def start(self, payload):
        return {
            "state": "running",
            "active": {
                "rate": payload.rate,
                "duration_seconds": payload.duration_seconds,
            },
        }

    def stop(self):
        return {"state": "stopped", "active": None}


def client():
    app = create_app(payment_service=PaymentService(EmptyPaymentRepo()))
    app.state.streaming_poc_service = FakeStreamingPocService()
    return TestClient(app)


def test_streaming_poc_status_endpoint_returns_pipeline_state():
    response = client().get("/api/streaming-poc/status")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "idle"
    assert body["health"]["kafka"]["status"] == "healthy"


def test_streaming_poc_start_accepts_rate_and_duration():
    response = client().post(
        "/api/streaming-poc/start",
        json={"rate": 10, "duration_seconds": 600},
    )

    assert response.status_code == 201
    assert response.json()["active"] == {"rate": 10.0, "duration_seconds": 600}


def test_streaming_poc_stop_endpoint_stops_the_source_workload():
    response = client().post("/api/streaming-poc/stop")

    assert response.status_code == 200
    assert response.json() == {"state": "stopped", "active": None}
