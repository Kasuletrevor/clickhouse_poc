from fastapi.testclient import TestClient

from app.main import create_app
from app.services.payments import PaymentService


class EmptyRepo:
    def list_payments(self, **kwargs): return [], 0
    def payment_summary(self): return {"payments_today": 0, "successful": 0, "pending": 0, "reversed": 0, "amount_today": 0}
    def get_payment(self, payment_id): return None
    def taxpayer_context(self, taxpayer_id): return None
    def payment_exists(self, payment_id): return False
    def create_payment(self, *args): raise AssertionError("not used")
    def update_status(self, *args): return False


def test_root_renders_the_internal_application_shell():
    app = create_app(payment_service=PaymentService(EmptyRepo()))
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Tax Operations Portal" in response.text
    assert "Payments" in response.text
    assert "Pipeline Health" in response.text
    assert "<img" not in response.text
