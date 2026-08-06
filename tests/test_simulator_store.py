from pathlib import Path

import pytest

from app.simulator.models import RunRecord
from app.simulator.store import ActiveRunExists, RunStore


def record(run_id="EFR-1", prefix="S1", status="starting"):
    return RunRecord(run_id, prefix, status, "run", 14.0, 60, 840, 0.12, 1)


def test_only_one_active_run_can_be_created(tmp_path: Path):
    store = RunStore(tmp_path)
    store.create_run(record())
    with pytest.raises(ActiveRunExists):
        store.create_run(record("EFR-2", "S2"))


def test_final_run_does_not_block_next_run(tmp_path: Path):
    store = RunStore(tmp_path)
    store.create_run(record())
    store.set_fields("EFR-1", status="completed")
    created = store.create_run(record("EFR-2", "S2"))
    assert created.run_id == "EFR-2"


def test_update_round_trip(tmp_path: Path):
    store = RunStore(tmp_path)
    store.create_run(record())
    store.set_fields("EFR-1", generated=14)
    assert store.get_run("EFR-1").generated == 14
