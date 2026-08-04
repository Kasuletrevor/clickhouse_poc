from decimal import Decimal

import pytest

from app.errors import APIError
from app.services.payments import PaymentService


class FakeRepo:
    def __init__(self):
        self.payments = {
            "PAY1": {
                "payment_id": "PAY1",
                "taxpayer_id": "TIN001",
                "taxpayer_name": "KJT Traders",
                "amount": Decimal("1000.00"),
                "status": "PENDING",
                "payment_time": None,
                "updated_at": None,
                "station_id": "ST001",
                "station_name": "Kampala Central",
            }
        }
        self.taxpayers = {
            "TIN001": {
                "taxpayer_id": "TIN001",
                "taxpayer_name": "KJT Traders",
                "station_id": "ST001",
                "station_name": "Kampala Central",
            }
        }

    def get_payment(self, payment_id):
        return self.payments.get(payment_id)

    def taxpayer_context(self, taxpayer_id):
        return self.taxpayers.get(taxpayer_id)

    def payment_exists(self, payment_id):
        return payment_id in self.payments

    def create_payment(self, payment_id, taxpayer_id, amount, status):
        self.payments[payment_id] = {
            "payment_id": payment_id,
            "taxpayer_id": taxpayer_id,
            "taxpayer_name": self.taxpayers[taxpayer_id]["taxpayer_name"],
            "amount": amount,
            "status": status,
            "payment_time": None,
            "updated_at": None,
            "station_id": self.taxpayers[taxpayer_id]["station_id"],
            "station_name": self.taxpayers[taxpayer_id]["station_name"],
        }
        return self.payments[payment_id]

    def update_status(self, payment_id, expected_status, new_status):
        payment = self.payments[payment_id]
        if payment["status"] != expected_status:
            return False
        payment["status"] = new_status
        return True


def test_pending_payment_can_be_marked_successful():
    service = PaymentService(FakeRepo())
    payment = service.change_status("PAY1", "SUCCESSFUL")
    assert payment["status"] == "SUCCESSFUL"


def test_reversed_payment_cannot_be_changed_back_to_successful():
    repo = FakeRepo()
    repo.payments["PAY1"]["status"] = "REVERSED"
    service = PaymentService(repo)

    with pytest.raises(APIError) as exc:
        service.change_status("PAY1", "SUCCESSFUL")

    assert exc.value.status_code == 409
    assert exc.value.code == "invalid_status_transition"


def test_create_payment_requires_existing_taxpayer_station_reference():
    repo = FakeRepo()
    repo.taxpayers["TIN001"]["station_id"] = None
    repo.taxpayers["TIN001"]["station_name"] = None
    service = PaymentService(repo)

    with pytest.raises(APIError) as exc:
        service.create_payment("PAY2", "TIN001", Decimal("5000.00"), "PENDING")

    assert exc.value.code == "station_not_found"
