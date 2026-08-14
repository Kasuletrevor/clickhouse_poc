from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from app.simulator.models import ACTIVE_STATUSES, RunRecord


class ActiveRunExists(RuntimeError):
    def __init__(self, active_run: RunRecord):
        self.active_run = active_run
        super().__init__(f"Simulation {active_run.run_id} is already active")


class RunNotFound(KeyError):
    pass


class RunStore:
    def __init__(self, runtime_dir: Path | str):
        self.runtime_dir = Path(runtime_dir)
        self.runs_dir = self.runtime_dir / "runs"
        self.logs_dir = self.runtime_dir / "logs"
        self.active_path = self.runtime_dir / "active.json"
        self.lock_path = self.runtime_dir / "registry.lock"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path.touch(exist_ok=True)

    @contextmanager
    def _locked(self):
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _atomic_write(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _run_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def _get_run_unlocked(self, run_id: str) -> RunRecord:
        payload = self._read_json(self._run_path(run_id))
        if payload is None:
            raise RunNotFound(run_id)
        return RunRecord.from_dict(payload)

    def _active_unlocked(self) -> RunRecord | None:
        pointer = self._read_json(self.active_path)
        if not pointer or not pointer.get("run_id"):
            return None
        try:
            return self._get_run_unlocked(str(pointer["run_id"]))
        except RunNotFound:
            return None

    def create_run(self, record: RunRecord) -> RunRecord:
        with self._locked():
            active = self._active_unlocked()
            if active is not None and active.status in ACTIVE_STATUSES:
                raise ActiveRunExists(active)
            path = self._run_path(record.run_id)
            if path.exists():
                raise FileExistsError(f"Run already exists: {record.run_id}")
            self._atomic_write(path, record.to_dict())
            self._atomic_write(self.active_path, {"run_id": record.run_id})
        return record

    def get_run(self, run_id: str) -> RunRecord:
        with self._locked():
            return self._get_run_unlocked(run_id)

    def get_current_run(self) -> RunRecord | None:
        with self._locked():
            return self._active_unlocked()

    def get_active_run(self) -> RunRecord | None:
        with self._locked():
            active = self._active_unlocked()
            if active is None or active.status not in ACTIVE_STATUSES:
                return None
            return active

    def update_run(self, run_id: str, mutator: Callable[[RunRecord], object | None]) -> RunRecord:
        with self._locked():
            record = self._get_run_unlocked(run_id)
            mutator(record)
            self._atomic_write(self._run_path(run_id), record.to_dict())
            return record

    def set_fields(self, run_id: str, **fields) -> RunRecord:
        def mutate(record: RunRecord):
            for key, value in fields.items():
                if not hasattr(record, key):
                    raise AttributeError(key)
                setattr(record, key, value)
        return self.update_run(run_id, mutate)

    def clear_active(self, run_id: str) -> None:
        with self._locked():
            pointer = self._read_json(self.active_path)
            if pointer and pointer.get("run_id") == run_id:
                try:
                    self.active_path.unlink()
                except FileNotFoundError:
                    pass

    def list_runs(self, limit: int = 20) -> list[RunRecord]:
        limit = max(1, min(int(limit), 100))
        with self._locked():
            records = []
            for path in self.runs_dir.glob("*.json"):
                payload = self._read_json(path)
                if payload:
                    try:
                        records.append(RunRecord.from_dict(payload))
                    except (TypeError, ValueError):
                        continue
        records.sort(key=lambda item: item.run_id, reverse=True)
        return records[:limit]
