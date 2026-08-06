import json
from pathlib import Path

import pytest

from app.simulator.engine import EfrisEventFactory, RatePacer, format_source_id


class Cursor:
    def __init__(self):
        self.value = 0

    def execute(self, _sql):
        self.value += 1

    def fetchone(self):
        return (self.value,)


def write(path: Path, name: str, payload):
    (path / name).write_text(json.dumps(payload), encoding="utf-8")


def sim_dir(tmp_path: Path):
    write(tmp_path, "generated_taxpayers.json", [{"taxpayer_id": "SIMTIN000001", "traffic_weight": 1}])
    write(tmp_path, "generated_devices.json", [{"device_no": "SIMTIN000001_01", "taxpayer_id": "SIMTIN000001", "traffic_weight": 1}])
    write(tmp_path, "error_codes.json", [{"code": "1600", "message": "Inventory shortage!", "weight": 1}])
    write(tmp_path, "products.json", ["Rice"])
    write(tmp_path, "config.json", {"recent_reference_pool": 10, "gross_amount_min": 100, "gross_amount_max": 100, "currency": "UGX", "create_user_id": "POC_SIMULATOR"})
    return tmp_path


def test_source_id_is_run_scoped():
    assert format_source_id("S260806A1", 841) == "S260806A1-000841"


def test_retry_reuses_business_reference(tmp_path):
    factory = EfrisEventFactory(sim_dir(tmp_path), "S260806A1", seed=1, retry_probability=1.0)
    cursor = Cursor()
    first = factory.next_bindings(cursor, 1)
    second = factory.next_bindings(cursor, 2)
    assert first["seller_reference_no"] == second["seller_reference_no"]
    assert first["tin"] == second["tin"]
    assert first["device_no"] == second["device_no"]
    assert first["source_id"] != second["source_id"]


def test_rate_pacer_first_deadline_is_one_interval_after_start():
    values = iter([100.0, 100.1])
    pacer = RatePacer(10.0, clock=lambda: next(values), sleeper=lambda _: None)
    assert pacer.next_due == 100.1
    pacer.reset()
    assert pacer.next_due == pytest.approx(100.2)
