from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.clickhouse import AnalyticsOperationError, AnalyticsUnavailableError
from app.errors import APIError


class StreamingPocService:
    def __init__(
        self,
        repository,
        health_repository,
        settings,
        project_root: Path,
        launcher=subprocess.Popen,
    ):
        self.repository = repository
        self.health_repository = health_repository
        self.settings = settings
        self.project_root = Path(project_root)
        self.launcher = launcher
        self.runtime_dir = self.project_root / "runtime" / "streaming_poc"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.runtime_dir / "payments_cdc.log"
        self._process = None
        self._timer = None
        self._run = None
        self._state = "idle"
        self._lock = threading.RLock()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _source_generated(self) -> int:
        try:
            with self.log_path.open("r", encoding="utf-8", errors="replace") as handle:
                return sum(
                    1
                    for line in handle
                    if line.startswith("[PAYMENT]")
                    or line.startswith("[UPDATE ]")
                    or line.startswith("[MOVE   ]")
                )
        except FileNotFoundError:
            return 0

    def _run_view(self, running: bool, arrivals: dict) -> dict | None:
        if not self._run:
            return None
        generated = self._source_generated()
        received = int(arrivals.get("received") or 0)
        return {
            **self._run,
            "status": "running" if running else self._state,
            "source_generated": generated,
            "clickhouse_received": received,
            "in_flight": max(generated - received, 0),
            "payments_received": int(arrivals.get("payments") or 0),
            "taxpayer_changes_received": int(arrivals.get("taxpayer_changes") or 0),
        }

    def _launch_environment(self) -> dict:
        if not self.settings.oracle_password:
            raise APIError(
                503,
                "streaming_poc_not_configured",
                "CDC_APP_PASSWORD is not configured for the source workload.",
            )
        env = os.environ.copy()
        env["CDC_APP_USER"] = self.settings.oracle_user
        env["CDC_APP_PASSWORD"] = self.settings.oracle_password
        env["CDC_APP_DSN"] = self.settings.oracle_dsn
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def start(self, payload) -> dict:
        with self._lock:
            if self._is_running():
                raise APIError(
                    409,
                    "streaming_poc_already_running",
                    "The payments CDC source workload is already running.",
                    {"active": self._run},
                )

            if self._timer:
                self._timer.cancel()
                self._timer = None

            env = self._launch_environment()
            self.log_path.write_text("", encoding="utf-8")
            command = [
                sys.executable,
                str(self.project_root / "simulator" / "run_load.py"),
                "--transactions-per-minute",
                str(float(payload.rate)),
            ]
            try:
                log_handle = self.log_path.open("ab", buffering=0)
                try:
                    self._process = self.launcher(
                        command,
                        cwd=str(self.project_root),
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=log_handle,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                        close_fds=True,
                    )
                finally:
                    log_handle.close()
            except Exception as exc:
                self._process = None
                self._state = "failed"
                raise APIError(
                    500,
                    "streaming_poc_start_failed",
                    "The payments CDC source workload could not be started.",
                ) from exc

            self._state = "running"
            self._run = {
                "rate": float(payload.rate),
                "duration_seconds": int(payload.duration_seconds),
                "started_at": self._now_iso(),
                "pid": int(self._process.pid),
            }

            if int(payload.duration_seconds) > 0:
                self._timer = threading.Timer(int(payload.duration_seconds), self.stop)
                self._timer.daemon = True
                self._timer.start()

        return self.status()

    def stop(self) -> dict:
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None

            process = self._process
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)

            self._process = None
            self._state = "stopped" if self._run else "idle"

        return {"state": self._state, "active": None}

    def status(self) -> dict:
        with self._lock:
            running = self._is_running()
            if self._process is not None and not running and self._state == "running":
                return_code = self._process.poll()
                self._state = "stopped" if return_code == 0 else "failed"
                self._process = None
            run = dict(self._run) if self._run else None
            state = "running" if running else self._state

        try:
            health = self.health_repository.pipeline_health()
        except Exception:
            health = {
                "oracle": {"status": "unknown", "detail": "Health check unavailable"},
                "debezium": {"status": "unknown", "detail": "Health check unavailable"},
                "kafka": {"status": "unknown", "detail": "Health check unavailable"},
                "clickhouse": {"status": "unknown", "detail": "Health check unavailable"},
            }

        arrivals = {"received": 0, "payments": 0, "taxpayer_changes": 0}
        events = []
        if run:
            try:
                arrivals = self.repository.arrival_summary(run["started_at"])
                events = self.repository.recent_events(run["started_at"], 40)
            except (AnalyticsUnavailableError, AnalyticsOperationError, ValueError):
                pass

        return {
            "state": state,
            "active": self._run_view(running, arrivals) if running else None,
            "run": self._run_view(running, arrivals),
            "health": health,
            "recent_events": events,
        }
