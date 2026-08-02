from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from secrets import token_hex
from typing import Protocol

from app.errors import APIError

ALLOWED_STATUSES = {"PENDING", "SUCCESSFUL", "REVERSED"}
ALLOWED_TRANSITIONS = {
    "PENDING": {"SUCCESSFUL", "REVERSED"},
    "SUCCESSFUL": {"REVERSED"},
    "REVERSED": set(),
}


class PaymentRepository(Protocol):
    def list_payments(self, **kwargs): ...
    def payment_summary(self): ...
    def get_payment(self, payment_id: str): ...
    def taxpayer_context(self, taxpayer_id: str): ...
    def payment_exists(self, payment_id: str) -> bool: ...
    def create_payment(self, payment_id: str, taxpayer_id: str, amount: Decimal, status: str): ...
    def update_status(self, payment_id: str, expected_status: str, new_status: str) -> bool: ...


def generate_payment_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")
    return f"WEB{stamp}{token_hex(2).upper()}"


class PaymentService:
    def __init__(self, repo: PaymentRepository):
        self.repo = repo

    def list_payments(self, **filters):
        items, total = self.repo.list_payments(**filters)
        return {"items": items, "total": total, "summary": self.repo.payment_summary()}

    def get_payment(self, payment_id: str):
        payment = self.repo.get_payment(payment_id)
        if payment is None:
            raise APIError(404, "payment_not_found", f"Payment {payment_id} does not exist.")
        return payment

    def create_payment(self, payment_id: str | None, taxpayer_id: str, amount: Decimal, status: str):
        if amount <= 0:
            raise APIError(422, "invalid_amount", "Payment amount must be greater than zero.")
        if status not in ALLOWED_STATUSES:
            raise APIError(422, "invalid_payment_status", "Unsupported payment status.")

        payment_id = payment_id or generate_payment_id()
        if self.repo.payment_exists(payment_id):
            raise APIError(409, "duplicate_payment", f"Payment {payment_id} already exists.")

        taxpayer = self.repo.taxpayer_context(taxpayer_id)
        if taxpayer is None:
            raise APIError(404, "taxpayer_not_found", f"Taxpayer {taxpayer_id} does not exist.")
        if not taxpayer.get("station_id") or not taxpayer.get("station_name"):
            raise APIError(409, "station_not_found", f"Taxpayer {taxpayer_id} does not reference a valid station.")

        return self.repo.create_payment(payment_id, taxpayer_id, amount, status)

    def change_status(self, payment_id: str, new_status: str):
        payment = self.get_payment(payment_id)
        if new_status not in ALLOWED_STATUSES:
            raise APIError(422, "invalid_payment_status", "Unsupported payment status.")

        current_status = payment["status"]
        if new_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
            raise APIError(
                409,
                "invalid_status_transition",
                f"Payment status cannot change from {current_status} to {new_status}.",
            )

        if not self.repo.update_status(payment_id, current_status, new_status):
            raise APIError(409, "payment_changed", "Payment changed before the update could be applied. Refresh and retry.")
        return self.get_payment(payment_id)
