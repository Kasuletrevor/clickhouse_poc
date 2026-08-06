from __future__ import annotations

import time

from app.clickhouse import AnalyticsOperationError, AnalyticsUnavailableError
from app.errors import APIError
from app.oracle import SourceOperationError, SourceUnavailableError
from app.simulator.manager import SimulatorManager, SimulatorStateError
from app.simulator.models import RunConfig, RunRecord, utc_now_iso
from app.simulator.store import ActiveRunExists, RunNotFound, RunStore


class SimulatorService:
    def __init__(self, store: RunStore, manager: SimulatorManager, repository, seed_factory=None):
        self.store = store
        self.manager = manager
        self.repository = repository
        self.seed_factory = seed_factory or (lambda: int(time.time_ns() % 2_147_483_647))
        self._health_cache = None
        self._health_cached_at = 0.0

    @staticmethod
    def _record_view(run: RunRecord) -> dict:
        return run.to_dict()

    def start(self, payload) -> dict:
        config = RunConfig(
            rate=float(payload.rate),
            duration_seconds=int(payload.duration_seconds),
            retry_probability=float(payload.retry_probability),
            random_seed=int(self.seed_factory()),
        )
        try:
            run = self.manager.start(config)
        except ActiveRunExists as exc:
            raise APIError(
                409,
                "simulation_already_running",
                "A simulation is already running.",
                {"active_run": self._record_view(exc.active_run)},
            ) from exc
        return self._record_view(run)

    def _control(self, run_id: str, operation: str) -> dict:
        try:
            method = getattr(self.manager, operation)
            return self._record_view(method(run_id))
        except RunNotFound as exc:
            raise APIError(404, "simulation_not_found", f"Simulation {run_id} does not exist.") from exc
        except SimulatorStateError as exc:
            raise APIError(409, exc.code, str(exc), {"run": self._record_view(exc.run) if exc.run else None}) from exc

    def pause(self, run_id: str) -> dict:
        return self._control(run_id, "pause")

    def resume(self, run_id: str) -> dict:
        return self._control(run_id, "resume")

    def stop(self, run_id: str) -> dict:
        return self._control(run_id, "stop")

    def events(self, run_id: str, limit: int = 40) -> list[dict]:
        try:
            run = self.store.get_run(run_id)
        except RunNotFound as exc:
            raise APIError(404, "simulation_not_found", f"Simulation {run_id} does not exist.") from exc
        try:
            return self.repository.recent_events(run.source_prefix, limit)
        except (SourceUnavailableError, SourceOperationError, AnalyticsUnavailableError, AnalyticsOperationError):
            return []

    def history(self, limit: int = 20) -> list[dict]:
        return [self._record_view(run) for run in self.store.list_runs(limit)]

    def _health(self) -> dict:
        now = time.monotonic()
        if self._health_cache is None or now - self._health_cached_at >= 5.0:
            self._health_cache = self.repository.pipeline_health()
            self._health_cached_at = now
        return self._health_cache

    def status(self) -> dict:
        health = self._health()
        active = self.store.get_active_run()
        current = active or self.store.get_current_run()
        if current is None:
            return {
                "state": "idle",
                "active": None,
                "defaults": {"rate": 14.0, "duration_seconds": 600, "retry_probability": 0.12},
                "population": {"stations": 20, "taxpayers": 200, "devices": 500, "error_codes": 15},
                "health": health,
                "history": self.history(10),
            }

        active = self.manager.reconcile_worker_state(current) if current.status in {"starting", "running", "paused"} else current
        oracle_summary = None
        clickhouse_summary = None
        throughput = []
        source_exact = True
        destination_available = True
        try:
            oracle_summary = self.repository.oracle_run_summary(active.source_prefix)
        except (SourceUnavailableError, SourceOperationError):
            source_exact = False
        try:
            clickhouse_summary = self.repository.clickhouse_run_summary(active.source_prefix)
            throughput = self.repository.arrival_throughput(active.source_prefix)
        except (AnalyticsUnavailableError, AnalyticsOperationError):
            destination_available = False

        view = self._compose_run_status(active, oracle_summary, clickhouse_summary, health)
        view["source_count_exact"] = source_exact
        view["destination_available"] = destination_available
        view["throughput"] = throughput

        if active.status == "draining" and source_exact and destination_available and view["clickhouse_received"] >= view["oracle_committed"]:
            active = self.store.set_fields(active.run_id, status="completed", finished_at=utc_now_iso())
            view = self._compose_run_status(active, oracle_summary, clickhouse_summary, health)
            view["source_count_exact"] = True
            view["destination_available"] = True
            view["throughput"] = throughput

        try:
            recent = self.repository.recent_events(active.source_prefix, 40)
        except (SourceUnavailableError, SourceOperationError, AnalyticsUnavailableError, AnalyticsOperationError):
            recent = []
        view["recent_events"] = recent
        return {"state": view["status"], "active": view, "health": health, "history": self.history(10)}

    @staticmethod
    def _compose_run_status(run: RunRecord, oracle_summary: dict | None, ch_summary: dict | None, health: dict) -> dict:
        oracle_committed = int(oracle_summary["oracle_committed"]) if oracle_summary else int(run.generated)
        ch = ch_summary or {
            "clickhouse_received": 0,
            "affected_invoices": 0,
            "retry_events": 0,
            "taxpayers": 0,
            "devices": 0,
            "error_codes": 0,
            "avg_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
            "max_ms": None,
        }
        clickhouse_received = int(ch.get("clickhouse_received") or 0)
        in_flight = max(oracle_committed - clickhouse_received, 0)
        delivery_percent = round(clickhouse_received / oracle_committed * 100, 2) if oracle_committed else 0.0
        target = run.target_events
        progress_percent = round(min(run.generated / target * 100, 100), 2) if target else None
        actual_rate = round(run.generated / run.active_elapsed_seconds, 2) if run.active_elapsed_seconds > 0 else 0.0
        remaining_events = max(target - run.generated, 0) if target is not None else None
        remaining_seconds = round(remaining_events / run.rate, 1) if remaining_events is not None and run.rate else None
        return {
            **run.to_dict(),
            "oracle_committed": oracle_committed,
            "clickhouse_received": clickhouse_received,
            "in_flight": in_flight,
            "delivery_percent": delivery_percent,
            "progress_percent": progress_percent,
            "actual_source_rate": actual_rate,
            "remaining_events": remaining_events,
            "remaining_seconds": remaining_seconds,
            "metrics": {
                "error_events": clickhouse_received,
                "affected_invoices": int(ch.get("affected_invoices") or 0),
                "retry_events": int(ch.get("retry_events") or 0),
                "taxpayers": int(ch.get("taxpayers") or 0),
                "devices": int(ch.get("devices") or 0),
                "error_codes": int(ch.get("error_codes") or 0),
            },
            "latency": {
                "avg_ms": ch.get("avg_ms"),
                "p50_ms": ch.get("p50_ms"),
                "p95_ms": ch.get("p95_ms"),
                "p99_ms": ch.get("p99_ms"),
                "max_ms": ch.get("max_ms"),
            },
            "health": health,
            "source_summary": oracle_summary,
        }
