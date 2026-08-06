from app.simulator.manager import SimulatorManager
from app.simulator.models import RunConfig, RunRecord
from app.simulator.store import RunStore


class FakeProcess:
    pid = 4321


def test_start_persists_worker_pid(tmp_path):
    calls = []

    def launcher(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    manager = SimulatorManager(RunStore(tmp_path), launcher=launcher, project_root=tmp_path)
    run = manager.start(RunConfig(14, 60, 0.12, 1))
    assert run.pid == 4321
    assert run.status == "starting"
    assert calls


def test_pause_resume_stop_use_commands(tmp_path):
    store = RunStore(tmp_path)
    run = RunRecord("EFR-1", "S1", "running", "run", 14, 60, 840, 0.12, 1, pid=1)
    store.create_run(run)
    manager = SimulatorManager(store, pid_probe=lambda _: True)
    assert manager.pause("EFR-1").command == "pause"
    store.set_fields("EFR-1", status="paused")
    assert manager.resume("EFR-1").command == "run"
    store.set_fields("EFR-1", status="running")
    assert manager.stop("EFR-1").command == "stop"


def test_stop_is_allowed_while_worker_is_still_starting(tmp_path):
    store = RunStore(tmp_path)
    run = RunRecord("EFR-START", "SSTART", "starting", "run", 14, 60, 840, 0.12, 1, pid=123)
    store.create_run(run)
    manager = SimulatorManager(store, pid_probe=lambda _: True)
    stopped = manager.stop("EFR-START")
    assert stopped.status == "starting"
    assert stopped.command == "stop"
