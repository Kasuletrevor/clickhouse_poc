from __future__ import annotations

from datetime import datetime, timezone
from secrets import token_hex

from app.errors import APIError


def generate_source_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")
    return f"WEBERR{stamp}{token_hex(3).upper()}"


class EfrisEventService:
    def __init__(self, repository):
        self.repository = repository

    def devices(self, tin: str):
        tin = tin.strip().upper()
        if not self.repository.taxpayer_exists(tin):
            raise APIError(404, "taxpayer_not_found", f"Taxpayer {tin} does not exist.")
        return self.repository.list_devices(tin)

    def create_event(self, payload):
        devices = self.devices(payload.tin)
        allowed_devices = {row["device_no"] for row in devices}
        if payload.device_no not in allowed_devices:
            raise APIError(
                422,
                "invalid_efris_device",
                f"Device {payload.device_no} is not registered to taxpayer {payload.tin}.",
            )

        event = self.repository.create_event(
            source_id=generate_source_id(),
            tin=payload.tin,
            device_no=payload.device_no,
            seller_reference_no=payload.seller_reference_no,
            return_code=payload.return_code,
            return_msg=payload.return_msg,
            gross_amount=payload.gross_amount,
            tax_amount=payload.tax_amount,
            currency=payload.currency,
            item_description=payload.item_description,
        )
        if event is None:
            raise APIError(500, "efris_event_not_found", "EFRIS error event was committed but could not be read back.")

        event["cdc_status"] = "committed_to_oracle"
        event["message"] = "Event committed to Oracle. Debezium, Kafka and ClickHouse will receive it asynchronously."
        return event
