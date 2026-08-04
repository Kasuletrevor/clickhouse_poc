from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.payments import PaymentService


class FakeRepo:
    def __init__(self):
        self.payments = {}
        self.taxpayers = {
            "TIN001": {
                "taxpayer_id": "TIN001",
                "taxpayer_name": "KJT Traders",
                "station_id": "ST001",
                "station_name": "Kampala Central",
            }
        }

    def list_payments(self, **kwargs):
        items = list(self.payments.values())
        return items, len(items)

    def payment_summary(self):
        values = list(self.payments.values())
        return {
            "payments_today": len(values),
            "successful": sum(p["status"] == "SUCCESSFUL" for p in values),
            "pending": sum(p["status"] == "PENDING" for p in values),
            "reversed": sum(p["status"] == "REVERSED" for p in values),
            "amount_today": sum((p["amount"] for p in values), Decimal("0")),
        }

    def get_payment(self, payment_id):
        return self.payments.get(payment_id)

    def taxpayer_context(self, taxpayer_id):
        return self.taxpayers.get(taxpayer_id)

    def payment_exists(self, payment_id):
        return payment_id in self.payments

    def create_payment(self, payment_id, taxpayer_id, amount, status):
        taxpayer = self.taxpayers[taxpayer_id]
        self.payments[payment_id] = {
            "payment_id": payment_id,
            "taxpayer_id": taxpayer_id,
            "taxpayer_name": taxpayer["taxpayer_name"],
            "amount": amount,
            "status": status,
            "payment_time": None,
            "updated_at": None,
            "station_id": taxpayer["station_id"],
            "station_name": taxpayer["station_name"],
        }
        return self.payments[payment_id]

    def update_status(self, payment_id, expected_status, new_status):
        payment = self.payments[payment_id]
        if payment["status"] != expected_status:
            return False
        payment["status"] = new_status
        return True


def client():
    app = create_app(payment_service=PaymentService(FakeRepo()))
    return TestClient(app)


def test_create_payment_returns_committed_source_record():
    c = client()
    response = c.post(
        "/api/payments",
        json={
            "payment_id": "PAY200",
            "taxpayer_id": "TIN001",
            "amount": "810000.00",
            "status": "PENDING",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["payment_id"] == "PAY200"
    assert body["status"] == "PENDING"
    assert body["station_name"] == "Kampala Central"


def test_invalid_status_transition_has_stable_error_shape():
    c = client()
    c.post(
        "/api/payments",
        json={
            "payment_id": "PAY201",
            "taxpayer_id": "TIN001",
            "amount": "1000.00",
            "status": "REVERSED",
        },
    )

    response = c.post("/api/payments/PAY201/status", json={"status": "SUCCESSFUL"})

    assert response.status_code == 409
    assert response.json() == {
        "error": "invalid_status_transition",
        "message": "Payment status cannot change from REVERSED to SUCCESSFUL.",
    }


def test_list_payments_returns_items_summary_and_total():
    c = client()
    c.post(
        "/api/payments",
        json={
            "payment_id": "PAY202",
            "taxpayer_id": "TIN001",
            "amount": "1500.00",
            "status": "SUCCESSFUL",
        },
    )

    response = c.get("/api/payments")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["summary"]["successful"] == 1
    assert body["items"][0]["payment_id"] == "PAY202"
