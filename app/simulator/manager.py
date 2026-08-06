from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.simulator.models import RunConfig, RunRecord, SOURCE_ACTIVE_STATUSES, make_run_identity, utc_now_iso
from app.simulator.store import RunStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SimulatorStateError(RuntimeError):
    def __init__(self, code: str, message: str, run: RunRecord | None = None):
        self.code = code
        self.run = run
        super().__init__(message)


def pid_exists(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class SimulatorManager:
    def __init__(
        self,
        store: RunStore,
        launcher: Callable = subprocess.Popen,
        stale_seconds: int = 10,
        project_root: Path = PROJECT_ROOT,
        pid_probe: Callable[[int | None], bool] = pid_exists,
    ):
        self.store = store
        self.launcher = launcher
        self.stale_seconds = int(stale_seconds)
        self.project_root = Path(project_root)
        self.pid_probe = pid_probe

    def start(self, config: RunConfig) -> RunRecord:
        last_error = None
        for _ in range(8):
            run_id, source_prefix = make_run_identity()
            record = RunRecord(
                run_id=run_id,
                source_prefix=source_prefix,
                status="starting",
                command="run",
                rate=config.rate,
                duration_seconds=config.duration_seconds,
                target_events=config.target_events,
                retry_probability=config.retry_probability,
                random_seed=config.random_seed,
                started_at=utc_now_iso(),
                last_heartbeat=utc_now_iso(),
            )
            try:
                self.store.create_run(record)
                break
            except FileExistsError as exc:
                last_error = exc
                continue
        else:
            raise RuntimeError("Could not allocate a unique simulation run identity") from last_error

        log_path = self.store.logs_dir / f"{record.run_id}.log"
        try:
            log_handle = log_path.open("ab", buffering=0)
            try:
                process = self.launcher(
                    [sys.executable, "-m", "app.simulator.worker", "--run-id", record.run_id],
                    cwd=str(self.project_root),
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
            finally:
                log_handle.close()
        except Exception as exc:
            self.store.set_fields(record.run_id, status="failed", error="Worker process could not be started.", finished_at=utc_now_iso())
            raise RuntimeError("Simulator worker could not be started") from exc

        return self.store.set_fields(record.run_id, pid=int(process.pid), last_heartbeat=utc_now_iso())

    def _active_for(self, run_id: str) -> RunRecord:
        run = self.store.get_run(run_id)
        if run.status not in {"starting", "running", "paused", "draining"}:
            raise SimulatorStateError("simulation_not_active", f"Simulation {run_id} is {run.status}.", run)
        return run

    def pause(self, run_id: str) -> RunRecord:
        run = self._active_for(run_id)
        if run.status == "paused" or run.command == "pause":
            return run
        if run.status != "running":
            raise SimulatorStateError("simulation_cannot_pause", f"Simulation cannot be paused while {run.status}.", run)
        return self.store.set_fields(run_id, command="pause")

    def resume(self, run_id: str) -> RunRecord:
        run = self._active_for(run_id)
        if run.status == "running" and run.command == "run":
            return run
        if run.status != "paused":
            raise SimulatorStateError("simulation_cannot_resume", f"Simulation cannot be resumed while {run.status}.", run)
        return self.store.set_fields(run_id, command="run")

    def stop(self, run_id: str) -> RunRecord:
        run = self._active_for(run_id)
        if run.status == "draining" or run.command == "stop":
            return run
        if run.status not in {"starting", "running", "paused"}:
            raise SimulatorStateError("simulation_cannot_stop", f"Simulation cannot be stopped while {run.status}.", run)
        return self.store.set_fields(run_id, command="stop")

    def reconcile_worker_state(self, run: RunRecord) -> RunRecord:
        if run.status not in SOURCE_ACTIVE_STATUSES:
            return run
        alive = self.pid_probe(run.pid)
        heartbeat_stale = False
        if run.last_heartbeat:
            try:
                heartbeat = datetime.fromisoformat(run.last_heartbeat)
                if heartbeat.tzinfo is None:
                    heartbeat = heartbeat.replace(tzinfo=timezone.utc)
                heartbeat_stale = (datetime.now(timezone.utc) - heartbeat).total_seconds() > self.stale_seconds
            except ValueError:
                heartbeat_stale = True
        if not alive or heartbeat_stale:
            reason = "Worker process is no longer running." if not alive else "Worker heartbeat expired."
            run = self.store.set_fields(run.run_id, status="stale", error=reason, finished_at=utc_now_iso())
        return run
