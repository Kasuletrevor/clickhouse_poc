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
                "payment_create_pct": payload.payment_create_pct,
                "status_update_pct": payload.status_update_pct,
                "taxpayer_move_pct": payload.taxpayer_move_pct,
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


def test_streaming_poc_start_accepts_events_per_second_and_editable_mix():
    response = client().post(
        "/api/streaming-poc/start",
        json={
            "rate": 10,
            "duration_seconds": 600,
            "payment_create_pct": 70,
            "status_update_pct": 20,
            "taxpayer_move_pct": 10,
        },
    )

    assert response.status_code == 201
    assert response.json()["active"] == {
        "rate": 10.0,
        "duration_seconds": 600,
        "payment_create_pct": 70.0,
        "status_update_pct": 20.0,
        "taxpayer_move_pct": 10.0,
    }


def test_streaming_poc_start_defaults_to_80_15_5_mix():
    response = client().post(
        "/api/streaming-poc/start",
        json={"rate": 10, "duration_seconds": 600},
    )

    assert response.status_code == 201
    active = response.json()["active"]
    assert active["payment_create_pct"] == 80.0
    assert active["status_update_pct"] == 15.0
    assert active["taxpayer_move_pct"] == 5.0


def test_streaming_poc_rejects_mix_that_does_not_total_100():
    response = client().post(
        "/api/streaming-poc/start",
        json={
            "rate": 10,
            "duration_seconds": 600,
            "payment_create_pct": 70,
            "status_update_pct": 20,
            "taxpayer_move_pct": 5,
        },
    )

    assert response.status_code == 422


def test_streaming_poc_stop_endpoint_stops_the_source_workload():
    response = client().post("/api/streaming-poc/stop")

    assert response.status_code == 200
    assert response.json() == {"state": "stopped", "active": None}
