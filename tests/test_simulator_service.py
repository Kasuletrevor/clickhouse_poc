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
