from app.errors import APIError
from app.services.simulator import SimulatorService
from app.simulator.models import RunRecord
from app.simulator.store import RunStore


class Manager:
    def reconcile_worker_state(self, run):
        return run


class Repo:
    def pipeline_health(self):
        return {k: {"status": "healthy", "detail": "ok"} for k in ["oracle", "debezium", "kafka", "clickhouse"]}

    def oracle_run_summary(self, prefix):
        return {"oracle_committed": 840, "affected_invoices": 750, "taxpayers": 188, "devices": 335, "error_codes": 15}

    def clickhouse_run_summary(self, prefix):
        return {"clickhouse_received": 812, "affected_invoices": 730, "retry_events": 82, "taxpayers": 180, "devices": 320, "error_codes": 15, "avg_ms": 6200, "p50_ms": 6300, "p95_ms": 9900, "p99_ms": 10900, "max_ms": 11000}

    def arrival_throughput(self, prefix):
        return []

    def recent_events(self, prefix, limit):
        return []


def test_status_reconciliation_math(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(RunRecord("EFR-1", "S1", "running", "run", 14, 60, 840, 0.12, 1, pid=1, generated=840, active_elapsed_seconds=60))
    view = SimulatorService(store, Manager(), Repo()).status()["active"]
    assert view["oracle_committed"] == 840
    assert view["clickhouse_received"] == 812
    assert view["in_flight"] == 28
    assert view["actual_source_rate"] == 14.0
    assert view["metrics"]["retry_events"] == 82


def test_draining_becomes_completed_when_counts_match(tmp_path):
    class CompleteRepo(Repo):
        def clickhouse_run_summary(self, prefix):
            row = super().clickhouse_run_summary(prefix)
            row["clickhouse_received"] = 840
            return row

    store = RunStore(tmp_path)
    store.create_run(RunRecord("EFR-1", "S1", "draining", "stop", 14, 60, 840, 0.12, 1, generated=840, active_elapsed_seconds=60))
    payload = SimulatorService(store, Manager(), CompleteRepo()).status()
    assert payload["active"]["status"] == "completed"


def test_stalled_draining_shortfall_can_be_closed_as_cdc_gap(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(
        RunRecord(
            "EFR-GAP",
            "S260813LF",
            "draining",
            "stop",
            14,
            300,
            4200,
            0.12,
            1,
            generated=4200,
            active_elapsed_seconds=300,
            last_heartbeat="2026-08-13T11:38:43+00:00",
        )
    )

    class GapRepo(Repo):
        def oracle_run_summary(self, prefix):
            return {"oracle_committed": 4200, "affected_invoices": 0, "taxpayers": 0, "devices": 0, "error_codes": 0}

        def clickhouse_run_summary(self, prefix):
            row = super().clickhouse_run_summary(prefix)
            row["clickhouse_received"] = 3964
            return row

    view = SimulatorService(store, Manager(), GapRepo()).status()["active"]
    assert view["can_close_cdc_gap"] is True
    assert view["draining_for_seconds"] >= 30


def test_close_cdc_gap_records_exact_shortfall_and_releases_active_run(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(
        RunRecord(
            "EFR-GAP",
            "S260813LF",
            "draining",
            "stop",
            14,
            300,
            4200,
            0.12,
            1,
            generated=4200,
            active_elapsed_seconds=300,
            last_heartbeat="2026-08-13T11:38:43+00:00",
        )
    )

    class GapRepo(Repo):
        def oracle_run_summary(self, prefix):
            return {"oracle_committed": 4200, "affected_invoices": 0, "taxpayers": 0, "devices": 0, "error_codes": 0}

        def clickhouse_run_summary(self, prefix):
            row = super().clickhouse_run_summary(prefix)
            row["clickhouse_received"] = 3964
            return row

    service = SimulatorService(store, Manager(), GapRepo())
    closed = service.close_gap("EFR-GAP")

    assert closed["status"] == "cdc_gap"
    assert closed["gap_events"] == 236
    assert closed["gap_oracle_committed"] == 4200
    assert closed["gap_clickhouse_received"] == 3964
    assert closed["gap_reason"] == "cdc_continuity_lost"
    assert closed["finished_at"] is not None
    assert store.get_active_run() is None

    view = service.status()["active"]
    assert view["status"] == "cdc_gap"
    assert view["in_flight"] == 0
    assert view["gap_events"] == 236


def test_close_cdc_gap_rejects_a_run_that_is_not_draining(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(RunRecord("EFR-1", "S1", "running", "run", 14, 60, 840, 0.12, 1, generated=100))
    service = SimulatorService(store, Manager(), Repo())

    try:
        service.close_gap("EFR-1")
    except APIError as exc:
        assert exc.status_code == 409
        assert exc.code == "simulation_cdc_gap_requires_draining"
    else:
        raise AssertionError("Expected close_gap to reject a non-draining run")
