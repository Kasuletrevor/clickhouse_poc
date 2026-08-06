# EFRIS Simulator Control Room Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing command-line EFRIS workload generator into a browser-controlled, refresh-safe Simulator Control Room that starts one server-side Oracle source workload, tracks exact run progress through ClickHouse, supports Pause/Resume/Stop, and preserves truthful Oracle → Debezium → Kafka → ClickHouse lineage.

**Architecture:** FastAPI owns run orchestration only; the actual workload runs in a detached Python worker process on the RHEL host. A small atomic JSON run registry under `runtime/simulator/` survives browser refreshes and FastAPI process restarts. The worker writes only to Oracle; the status API combines worker/run state, exact Oracle source rows, ClickHouse-arrived rows, CDC latency, and independently measured pipeline health. The browser polls this status API and never owns simulation execution.

**Tech Stack:** Python 3, FastAPI, `oracledb`, existing ClickHouse HTTP wrapper, standard-library `subprocess`, `fcntl`, `urllib`, `socket`, JSON persistence, vanilla JavaScript, existing HTML/CSS application shell, pytest/httpx.

## Global Constraints

- Browser refresh, navigation away, tab closure, and reopening the app must not stop an active simulation.
- The browser never generates EFRIS events and never writes to Kafka or ClickHouse.
- The worker writes only to `CDC_APP.T_INVOICE_ERROR_LOG`; downstream delivery remains Oracle redo → Debezium → Kafka → ClickHouse.
- Only one simulator run may be active on the POC host at a time.
- Default workload remains `14.00 events/sec`, `600 seconds`, `12% retry probability`, and `8,400` target source events.
- Pause stops new Oracle writes while downstream CDC continues draining; Resume continues the same run ID and sequence.
- Stop is final for that run and moves the run to `draining`; the run becomes `completed` only when ClickHouse has received all committed source events.
- Progress is source-event-count based. For finite runs, generation stops exactly when `generated == target_events`; paused time does not consume active duration.
- The UI must not invent Debezium/Kafka per-event stage state. Intermediate systems show health; exact per-event lineage is shown only once downstream evidence exists.
- Runtime state must contain no password, connection string, or secret.
- `T_INVOICE_ERROR_LOG.ID` is `VARCHAR2(32)`, so generated source IDs must stay within 32 characters.
- Keep the existing FastAPI + HTML/CSS + vanilla JavaScript architecture; do not add Celery, Redis, React, Node, or another orchestration dependency.
- Generated simulator population files remain local runtime artifacts and must not be committed.
- Current seeded population remains `20 stations`, `200 taxpayers`, `500 devices`, `15 error codes`.

---

## File Structure

### New backend files

- `app/simulator/__init__.py` — package marker.
- `app/simulator/models.py` — run configuration, run record, status constants, identity generation, serialization.
- `app/simulator/engine.py` — reusable weighted EFRIS event factory and monotonic rate pacer used by both CLI and worker.
- `app/simulator/store.py` — atomic JSON run registry, active-run lock, run history, stale-safe file updates.
- `app/simulator/worker.py` — detached server-side worker entry point; owns Oracle connection, pacing, Pause/Resume/Stop loop, heartbeat.
- `app/simulator/manager.py` — starts detached worker, issues commands through run state, detects stale/dead workers.
- `app/repositories/simulator.py` — exact Oracle/ClickHouse reconciliation, run-level analytics, recent event merge, pipeline health checks.
- `app/services/simulator.py` — Simulator use cases and run-state transitions exposed to the API.
- `app/schemas/simulator.py` — Start request validation.
- `app/routes/simulator.py` — Start/status/pause/resume/stop/history/events endpoints.

### New frontend file

- `app/static/js/simulator.js` — complete Simulator page, reconnect-safe polling, controls, live run view, event feed, charts.

### New tests

- `tests/test_simulator_models.py`
- `tests/test_simulator_store.py`
- `tests/test_simulator_engine.py`
- `tests/test_simulator_manager.py`
- `tests/test_simulator_service.py`
- `tests/test_simulator_api.py`

### Modified files

- `scripts/run_efris_simulator.py` — reuse the new engine; retain CLI capability.
- `app/config.py` — add Debezium/Kafka/runtime simulator settings.
- `app/errors.py` — allow structured error details for `simulation_already_running`.
- `app/main.py` — wire simulator service/router and structured API error response.
- `app/static/js/api.js` — preserve backend error code/details on thrown errors.
- `app/static/js/app.js` — route the existing Simulator nav item to `SimulatorPage`.
- `app/static/css/app.css` — Simulator Control Room layouts, states, responsive behavior, accessible status styling.
- `.gitignore` — ignore `runtime/simulator/` and worker logs.
- `.env.example` — document runtime/connector/broker settings without secrets.
- `simulation/README.md` — document browser-controlled and CLI modes.
- `docs/efris-error-monitor.md` — add the browser-controlled simulator milestone and verification flow.

---

### Task 1: Extract Reusable Simulator Engine and Exact Run Identity

**Files:**
- Create: `app/simulator/__init__.py`
- Create: `app/simulator/models.py`
- Create: `app/simulator/engine.py`
- Modify: `scripts/run_efris_simulator.py`
- Test: `tests/test_simulator_models.py`
- Test: `tests/test_simulator_engine.py`

**Interfaces:**
- Produces: `RunConfig`, `RunRecord`, `make_run_identity()`, `EfrisEventFactory`, `RatePacer`.
- `RunConfig(rate: float, duration_seconds: int, retry_probability: float, random_seed: int)` exposes `target_events: int | None`.
- `make_run_identity(now: datetime | None = None, token: str | None = None) -> tuple[str, str]` returns `(run_id, source_prefix)`.
- `EfrisEventFactory.next_bindings(cursor, sequence: int) -> dict` returns Oracle bind values including deterministic run-scoped `source_id`.
- `RatePacer.wait_next()` paces generation using `time.perf_counter()` and supports `reset()` after Resume so paused time never causes a catch-up burst.

- [ ] **Step 1: Write failing model tests for finite target count and 32-character-safe identities**

```python
# tests/test_simulator_models.py
from datetime import datetime, timezone

from app.simulator.models import RunConfig, make_run_identity


def test_finite_config_has_exact_target_event_count():
    config = RunConfig(rate=14.0, duration_seconds=60, retry_probability=0.12, random_seed=1)
    assert config.target_events == 840


def test_continuous_config_has_no_target_event_count():
    config = RunConfig(rate=14.0, duration_seconds=0, retry_probability=0.12, random_seed=1)
    assert config.target_events is None


def test_run_identity_is_traceable_and_source_ids_fit_oracle_column():
    now = datetime(2026, 8, 6, 8, 47, 1, tzinfo=timezone.utc)
    run_id, prefix = make_run_identity(now=now, token="A1")
    assert run_id == "EFR-20260806-084701-A1"
    assert prefix == "S260806A1"
    assert len(f"{prefix}-999999") <= 32
```

- [ ] **Step 2: Run the model tests and confirm they fail because the simulator package does not yet exist**

Run:

```bash
pytest tests/test_simulator_models.py -q
```

Expected: import failure for `app.simulator.models`.

- [ ] **Step 3: Implement run configuration, statuses, serialization and identity generation**

```python
# app/simulator/models.py
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from secrets import choice
from string import ascii_uppercase, digits

ACTIVE_STATUSES = {"starting", "running", "paused", "draining"}
FINAL_STATUSES = {"completed", "failed", "stale"}


@dataclass(frozen=True)
class RunConfig:
    rate: float
    duration_seconds: int
    retry_probability: float
    random_seed: int

    @property
    def target_events(self) -> int | None:
        if self.duration_seconds == 0:
            return None
        return round(self.rate * self.duration_seconds)


@dataclass
class RunRecord:
    run_id: str
    source_prefix: str
    status: str
    command: str
    rate: float
    duration_seconds: int
    target_events: int | None
    retry_probability: float
    random_seed: int
    pid: int | None = None
    generated: int = 0
    failures: int = 0
    last_sequence: int = 0
    active_elapsed_seconds: float = 0.0
    paused_seconds: float = 0.0
    started_at: str | None = None
    finished_at: str | None = None
    last_heartbeat: str | None = None
    source_rate_samples: list[dict] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "RunRecord":
        return cls(**payload)


def make_run_identity(now: datetime | None = None, token: str | None = None) -> tuple[str, str]:
    now = now or datetime.now(timezone.utc)
    token = token or "".join(choice(ascii_uppercase + digits) for _ in range(2))
    run_id = f"EFR-{now:%Y%m%d-%H%M%S}-{token}"
    source_prefix = f"S{now:%y%m%d}{token}"
    return run_id, source_prefix
```

- [ ] **Step 4: Write failing engine tests for deterministic source IDs, exact retry reuse and pacer reset**

```python
# tests/test_simulator_engine.py
from app.simulator.engine import format_source_id, RatePacer


def test_source_id_uses_run_prefix_and_monotonic_sequence():
    assert format_source_id("S260806A1", 1) == "S260806A1-000001"
    assert format_source_id("S260806A1", 841) == "S260806A1-000841"


def test_rate_pacer_reset_discards_old_deadline():
    clock_values = iter([100.0, 100.0, 105.0])
    pacer = RatePacer(rate=14.0, clock=lambda: next(clock_values), sleeper=lambda _: None)
    pacer.reset()
    assert pacer.next_due >= 100.0
```

- [ ] **Step 5: Implement the reusable event factory and pacer by extracting existing CLI behavior without changing workload semantics**

The engine must preserve weighted taxpayers/devices/error codes, 12% retry behavior, VAT calculation, product selection, seller-reference sequence generation and Oracle bind shape. The run-specific source ID changes from UUID-based `SIMERR...` to deterministic sequence IDs.

```python
# app/simulator/engine.py
from __future__ import annotations

import json
import random
import time
from collections import defaultdict, deque
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def format_source_id(source_prefix: str, sequence: int) -> str:
    value = f"{source_prefix}-{sequence:06d}"
    if len(value) > 32:
        raise ValueError("Simulator source ID exceeds T_INVOICE_ERROR_LOG.ID length")
    return value


class RatePacer:
    def __init__(self, rate: float, clock=time.perf_counter, sleeper=time.sleep):
        self.rate = rate
        self.interval = 1.0 / rate
        self.clock = clock
        self.sleeper = sleeper
        self.next_due = clock()

    def reset(self) -> None:
        self.next_due = self.clock()

    def wait_next(self) -> float:
        now = self.clock()
        delay = self.next_due - now
        if delay > 0:
            self.sleeper(delay)
        self.next_due += self.interval
        return max(0.0, self.clock() - self.next_due)
```

Implement `EfrisEventFactory` with constructor arguments `sim_dir`, `source_prefix`, `seed`, `retry_probability`, and method `next_bindings(cursor, sequence)` returning exactly the bind keys expected by `T_INVOICE_ERROR_LOG`.

- [ ] **Step 6: Refactor the CLI to call the shared engine and stop finite runs by exact target count**

Change the CLI finite loop condition from elapsed-time boundary checking to:

```python
target_events = config.target_events
while target_events is None or generated < target_events:
    pacer.wait_next()
    bindings = factory.next_bindings(cursor, generated + 1)
    cursor.execute(INSERT_SQL, bindings)
    conn.commit()
    generated += 1
```

Expected result for `--rate 14 --duration 60`: exactly `840` successful source commits rather than the current boundary-dependent `841`.

- [ ] **Step 7: Run focused tests and the existing Python compilation check**

```bash
pytest tests/test_simulator_models.py tests/test_simulator_engine.py -q
python -m compileall -q app scripts
```

Expected: all tests pass; compile command exits 0.

- [ ] **Step 8: Commit the engine extraction**

```bash
git add app/simulator scripts/run_efris_simulator.py tests/test_simulator_models.py tests/test_simulator_engine.py
git commit -m "refactor: extract reusable EFRIS simulation engine"
```

---

### Task 2: Durable Run Registry and State Machine

**Files:**
- Create: `app/simulator/store.py`
- Test: `tests/test_simulator_store.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `RunRecord`, `ACTIVE_STATUSES` from Task 1.
- Produces: `RunStore(runtime_dir: Path)`, `create_run(record)`, `get_run(run_id)`, `get_active_run()`, `update_run(run_id, mutator)`, `clear_active(run_id)`, `list_runs(limit)`.
- All state writes are atomic (`tempfile` + `os.replace`) and protected by `fcntl.flock` on `runtime/simulator/registry.lock`.

- [ ] **Step 1: Write failing tests for active-run exclusivity, atomic update and history**

```python
# tests/test_simulator_store.py
from pathlib import Path

import pytest

from app.simulator.models import RunRecord
from app.simulator.store import ActiveRunExists, RunStore


def record(run_id="EFR-1", prefix="S1"):
    return RunRecord(
        run_id=run_id,
        source_prefix=prefix,
        status="starting",
        command="run",
        rate=14.0,
        duration_seconds=60,
        target_events=840,
        retry_probability=0.12,
        random_seed=1,
    )


def test_only_one_active_run_can_be_created(tmp_path: Path):
    store = RunStore(tmp_path)
    store.create_run(record())
    with pytest.raises(ActiveRunExists):
        store.create_run(record("EFR-2", "S2"))


def test_update_round_trips_without_losing_fields(tmp_path: Path):
    store = RunStore(tmp_path)
    store.create_run(record())
    updated = store.update_run("EFR-1", lambda run: setattr(run, "generated", 14))
    assert updated.generated == 14
    assert store.get_run("EFR-1").generated == 14
```

- [ ] **Step 2: Run the store tests and confirm import failure**

```bash
pytest tests/test_simulator_store.py -q
```

Expected: import failure for `app.simulator.store`.

- [ ] **Step 3: Implement the locked atomic registry**

Core behavior:

```python
# app/simulator/store.py
class ActiveRunExists(RuntimeError):
    def __init__(self, active_run):
        self.active_run = active_run
        super().__init__(f"Simulation {active_run.run_id} is already active")


class RunStore:
    def __init__(self, runtime_dir: Path):
        self.runtime_dir = Path(runtime_dir)
        self.runs_dir = self.runtime_dir / "runs"
        self.active_path = self.runtime_dir / "active.json"
        self.lock_path = self.runtime_dir / "registry.lock"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
```

Implement a private `_locked()` context manager with `fcntl.flock(..., LOCK_EX)`, `_atomic_write(path, payload)` using a file in the same directory followed by `os.replace`, and ensure `create_run()` checks the active pointer while holding the same lock used to create the new active record.

- [ ] **Step 4: Add runtime artifacts to gitignore**

Append:

```gitignore
# EFRIS simulator server-side runtime state
runtime/simulator/
```

- [ ] **Step 5: Run store tests, including a second test process if practical**

```bash
pytest tests/test_simulator_store.py -q
```

Expected: all store tests pass.

- [ ] **Step 6: Commit the run registry**

```bash
git add app/simulator/store.py tests/test_simulator_store.py .gitignore
git commit -m "feat: add durable simulator run registry"
```

---

### Task 3: Detached Worker and Run Manager

**Files:**
- Create: `app/simulator/worker.py`
- Create: `app/simulator/manager.py`
- Test: `tests/test_simulator_manager.py`

**Interfaces:**
- Consumes: `RunStore`, `RunRecord`, `EfrisEventFactory`, `RatePacer`, existing `OracleDatabase/get_settings()`.
- Produces: `SimulatorManager.start(config)`, `pause(run_id)`, `resume(run_id)`, `stop(run_id)`, `reconcile_worker_state(run)`.
- Worker entry point: `python -m app.simulator.worker --run-id <run_id>`.
- Command field meanings: `run`, `pause`, `stop`; status field meanings remain `starting`, `running`, `paused`, `draining`, `completed`, `failed`, `stale`.

- [ ] **Step 1: Write failing manager tests using a fake process launcher and fake PID probe**

```python
# tests/test_simulator_manager.py
from app.simulator.models import RunConfig
from app.simulator.manager import SimulatorManager
from app.simulator.store import RunStore


def test_start_persists_pid_and_starting_run(tmp_path):
    launched = []

    class FakeProcess:
        pid = 4321

    def launcher(*args, **kwargs):
        launched.append((args, kwargs))
        return FakeProcess()

    manager = SimulatorManager(RunStore(tmp_path), launcher=launcher)
    run = manager.start(RunConfig(14.0, 60, 0.12, 1))
    assert run.pid == 4321
    assert run.status == "starting"
    assert launched


def test_pause_resume_stop_write_commands_without_killing_worker(tmp_path):
    # create active running record in store, then assert command changes:
    # running -> pause, paused -> run, running -> stop
    ...
```

Replace the ellipsis in the actual test with a complete seeded `RunRecord` fixture and explicit assertions; do not leave placeholders in committed tests.

- [ ] **Step 2: Run the manager test and verify failure**

```bash
pytest tests/test_simulator_manager.py -q
```

Expected: import failure for `app.simulator.manager`.

- [ ] **Step 3: Implement detached worker launch in the manager**

The manager must launch with the same Python interpreter and inherited environment, but runtime JSON must not store the environment:

```python
process = subprocess.Popen(
    [sys.executable, "-m", "app.simulator.worker", "--run-id", run.run_id],
    cwd=str(PROJECT_ROOT),
    stdin=subprocess.DEVNULL,
    stdout=log_handle,
    stderr=subprocess.STDOUT,
    start_new_session=True,
    close_fds=True,
)
```

The manager must persist `pid` after successful launch and mark the run `failed` plus clear the active pointer if process creation raises.

- [ ] **Step 4: Implement Pause/Resume/Stop as durable commands rather than Unix signal semantics**

`pause()` only accepts an actual `running` run and writes `command="pause"`.

`resume()` only accepts `paused` and writes `command="run"`.

`stop()` accepts `running` or `paused` and writes `command="stop"`; the worker transitions the actual status to `draining` after it stops source generation.

Return idempotently if the requested state is already reached where that is safe; otherwise raise a domain error with the current state.

- [ ] **Step 5: Implement the worker loop**

Worker behavior:

```python
while run.target_events is None or run.generated < run.target_events:
    current = store.get_run(run_id)

    if current.command == "stop":
        set_status("draining")
        break

    if current.command == "pause":
        enter_paused_state_once()
        time.sleep(0.2)
        continue

    if returning_from_pause:
        pacer.reset()

    pacer.wait_next()
    bindings = factory.next_bindings(cursor, current.last_sequence + 1)
    cursor.execute(INSERT_SQL, bindings)
    conn.commit()
    record_successful_commit()
```

Requirements inside the worker:

- mark `running` after Oracle connection and factory setup succeed;
- update `last_heartbeat` at least once per second;
- update `generated`, `last_sequence`, `active_elapsed_seconds`, and a bounded source-rate sample list;
- exclude paused time from `active_elapsed_seconds`;
- after natural target completion, set `draining`;
- on `KeyboardInterrupt`/explicit stop, do not delete source rows;
- on fatal source exception, rollback, increment `failures`, set `failed`, store a sanitized error summary, and clear active pointer only when final-state rules allow;
- never write a password or raw connection string to state/log output.

- [ ] **Step 6: Add stale/dead-worker reconciliation**

`SimulatorManager.reconcile_worker_state(run)` must use both PID existence and heartbeat age. For statuses `starting`, `running`, or `paused`, if the process does not exist or heartbeat is older than a configured threshold, mark `stale` rather than continuing to display RUNNING.

Use `os.kill(pid, 0)` only as a liveness probe; do not send a terminating signal during ordinary state reconciliation.

- [ ] **Step 7: Run manager tests and compilation**

```bash
pytest tests/test_simulator_manager.py -q
python -m compileall -q app/simulator
```

Expected: all pass.

- [ ] **Step 8: Commit detached worker orchestration**

```bash
git add app/simulator/worker.py app/simulator/manager.py tests/test_simulator_manager.py
git commit -m "feat: run EFRIS simulation in detached worker"
```

---

### Task 4: Exact Reconciliation, CDC Analytics and Pipeline Health

**Files:**
- Create: `app/repositories/simulator.py`
- Modify: `app/config.py`
- Modify: `.env.example`
- Test: `tests/test_simulator_service.py` (repository fakes are used here rather than integration DBs)

**Interfaces:**
- Produces repository methods:
  - `oracle_run_summary(source_prefix) -> dict`
  - `clickhouse_run_summary(source_prefix) -> dict`
  - `clickhouse_latency(source_prefix) -> dict`
  - `recent_events(source_prefix, limit=40) -> list[dict]`
  - `arrival_throughput(source_prefix) -> list[dict]`
  - `pipeline_health() -> dict`
- `pipeline_health()` returns exact stage states `healthy`, `degraded`, `unavailable`, or `unknown` plus short detail text.

- [ ] **Step 1: Extend application settings with non-secret observability/runtime configuration**

Add to `Settings` in `app/config.py`:

```python
debezium_url: str = os.getenv("DEBEZIUM_URL", "http://localhost:8083")
debezium_flat_connector: str = os.getenv("DEBEZIUM_FLAT_CONNECTOR", "oracle-cdc-flat")
kafka_bootstrap: str = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
simulator_runtime_dir: str = os.getenv("SIMULATOR_RUNTIME_DIR", "runtime/simulator")
simulator_stale_seconds: int = int(os.getenv("SIMULATOR_STALE_SECONDS", "10"))
```

Document the same keys in `.env.example`; do not place real credentials there.

- [ ] **Step 2: Implement exact Oracle run summary by source prefix**

Use a bound prefix, not string interpolation:

```sql
SELECT
    COUNT(*) AS ERROR_EVENTS,
    COUNT(DISTINCT TIN || CHR(31) || SELLER_REFERENCE_NO) AS AFFECTED_INVOICES,
    COUNT(DISTINCT TIN) AS TAXPAYERS,
    COUNT(DISTINCT DEVICE_NO) AS DEVICES,
    COUNT(DISTINCT RETURN_CODE) AS ERROR_CODES,
    MIN(CREATE_DATE) AS FIRST_EVENT_TIME,
    MAX(CREATE_DATE) AS LAST_EVENT_TIME
FROM T_INVOICE_ERROR_LOG
WHERE ID LIKE :prefix
```

Bind `prefix=f"{source_prefix}-%"`.

`oracle_committed` is this exact row count when Oracle is available; worker `generated` remains the fallback counter when Oracle is temporarily unavailable.

- [ ] **Step 3: Implement ClickHouse run summary and latency metrics**

Use `startsWith(ifNull(id, ''), '<escaped-prefix>-')` and return:

```sql
SELECT
    count() AS clickhouse_received,
    uniqExact(tuple(tin, seller_reference_no)) AS affected_invoices,
    count() - uniqExact(tuple(tin, seller_reference_no)) AS retry_events,
    uniqExact(tin) AS taxpayers,
    uniqExact(device_no) AS devices,
    uniqExact(return_code) AS error_codes,
    avg(dateDiff('millisecond', source_commit_ts, ingested_at)) AS avg_ms,
    quantileExact(0.50)(dateDiff('millisecond', source_commit_ts, ingested_at)) AS p50_ms,
    quantileExact(0.95)(dateDiff('millisecond', source_commit_ts, ingested_at)) AS p95_ms,
    quantileExact(0.99)(dateDiff('millisecond', source_commit_ts, ingested_at)) AS p99_ms,
    max(dateDiff('millisecond', source_commit_ts, ingested_at)) AS max_ms
FROM analytics.raw_efris_error_log
WHERE startsWith(ifNull(id, ''), '<prefix>-')
```

Use the existing `ClickHouseDatabase` query path and centralize string escaping for the prefix even though server-generated prefixes are constrained.

- [ ] **Step 4: Implement truthful recent-event merge**

Query the latest Oracle source events for the run by `ERROR_EVENT_ID DESC`, query ClickHouse rows for the same run IDs, and merge in Python keyed by `ID`.

Pending row shape:

```python
{
    "source_id": "S260806A1-000123",
    "sequence": 123,
    "tin": "SIMTIN000042",
    "device_no": "SIMTIN000042_02",
    "return_code": "1600",
    "return_msg": "Inventory shortage!",
    "seller_reference_no": "...",
    "oracle_committed": True,
    "clickhouse_received": False,
    "cdc_latency_ms": None,
    "kafka_partition": None,
    "kafka_offset": None,
}
```

After arrival, populate `source_commit_ts`, `ingested_at`, `source_scn`, `source_commit_scn`, `kafka_partition`, `kafka_offset`, and calculated latency from the real ClickHouse row.

- [ ] **Step 5: Implement stage health without Docker CLI dependencies**

- Oracle: `SELECT 1 FROM DUAL` through `OracleDatabase`.
- Debezium: standard-library HTTP GET to `${DEBEZIUM_URL}/connectors/${DEBEZIUM_FLAT_CONNECTOR}/status`; healthy only when connector and task 0 are `RUNNING`.
- Kafka: parse `KAFKA_BOOTSTRAP` host/port and use `socket.create_connection(..., timeout=1.0)` as broker reachability for this POC; label it as broker reachability, not topic delivery proof.
- ClickHouse: lightweight `SELECT 1` through the existing ClickHouse wrapper.

Return data such as:

```python
{
    "oracle": {"status": "healthy", "detail": "Source reachable"},
    "debezium": {"status": "healthy", "detail": "Connector and task RUNNING"},
    "kafka": {"status": "healthy", "detail": "Broker reachable"},
    "clickhouse": {"status": "healthy", "detail": "Analytics reachable"},
}
```

- [ ] **Step 6: Add repository/service-level tests with fakes for reconciliation math**

Tests must explicitly cover:

```python
assert in_flight == max(oracle_committed - clickhouse_received, 0)
assert delivery_percent == 100.0 when oracle_committed == clickhouse_received == 840
assert retry_events == error_events - affected_invoices
```

Also test partial delivery (`840` source, `812` destination -> `28` in flight) and analytics unavailable while source state remains readable.

- [ ] **Step 7: Run focused tests**

```bash
pytest tests/test_simulator_service.py -q
python -m compileall -q app
```

- [ ] **Step 8: Commit observability and configuration**

```bash
git add app/repositories/simulator.py app/config.py .env.example tests/test_simulator_service.py
git commit -m "feat: add simulator CDC reconciliation metrics"
```

---

### Task 5: Simulator Service, API Contracts and App Wiring

**Files:**
- Create: `app/schemas/simulator.py`
- Create: `app/services/simulator.py`
- Create: `app/routes/simulator.py`
- Modify: `app/errors.py`
- Modify: `app/main.py`
- Test: `tests/test_simulator_api.py`

**Interfaces:**
- `POST /api/simulator/runs`
- `GET /api/simulator/status`
- `POST /api/simulator/runs/{run_id}/pause`
- `POST /api/simulator/runs/{run_id}/resume`
- `POST /api/simulator/runs/{run_id}/stop`
- `GET /api/simulator/runs/{run_id}/events?limit=40`
- `GET /api/simulator/runs?limit=20`

- [ ] **Step 1: Write failing API tests with a fake simulator service**

```python
# tests/test_simulator_api.py
from fastapi.testclient import TestClient

from app.main import create_app


class FakeSimulatorService:
    def __init__(self):
        self.started = []

    def start(self, payload):
        self.started.append(payload)
        return {"run_id": "EFR-TEST", "status": "starting"}

    def status(self):
        return {"active": None, "history": []}


def test_start_simulation_returns_created_run(base_services):
    service = FakeSimulatorService()
    app = create_app(simulator_service=service, **base_services)
    client = TestClient(app)
    response = client.post("/api/simulator/runs", json={
        "rate": 14,
        "duration_seconds": 600,
        "retry_probability": 0.12,
    })
    assert response.status_code == 201
    assert response.json()["run_id"] == "EFR-TEST"
```

Use the repository's existing test helper/fake-service conventions when implementing `base_services`; if no shared fixture exists, define complete no-op fakes in this test file so `create_app()` never touches real Oracle/ClickHouse.

- [ ] **Step 2: Run the API test and confirm failure**

```bash
pytest tests/test_simulator_api.py -q
```

Expected: missing simulator route/service injection.

- [ ] **Step 3: Add strict Start request validation**

```python
# app/schemas/simulator.py
from pydantic import BaseModel, Field


class SimulatorStartRequest(BaseModel):
    rate: float = Field(default=14.0, gt=0, le=1000)
    duration_seconds: int = Field(default=600, ge=0, le=86400)
    retry_probability: float = Field(default=0.12, ge=0, le=1)
```

The upper bounds are safety limits for the POC UI; they do not claim infrastructure capacity.

- [ ] **Step 4: Extend APIError with optional structured details and preserve existing callers**

```python
class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
```

Update the handler in `app/main.py` to include `details` only when present. This enables `409 simulation_already_running` to return the active run metadata without breaking current error responses.

- [ ] **Step 5: Implement SimulatorService orchestration and derived status**

`SimulatorService.status()` must:

1. load the active run;
2. reconcile dead/stale worker state;
3. query exact Oracle/ClickHouse run metrics when a run exists;
4. compute `in_flight`, `delivery_percent`, source progress and latency;
5. if run status is `draining` and `clickhouse_received >= oracle_committed`, set `completed`, set `finished_at`, clear active pointer;
6. include stage health and recent run history.

A completed run must stay queryable from history after its active pointer is cleared.

- [ ] **Step 6: Implement API routes with correct status codes and state errors**

Example:

```python
@router.post("/runs", status_code=status.HTTP_201_CREATED)
def start_simulator(payload: SimulatorStartRequest, request: Request):
    return service(request).start(payload)


@router.get("/status")
def simulator_status(request: Request):
    return service(request).status()
```

Map duplicate active-run creation to:

```json
{
  "error": "simulation_already_running",
  "message": "A simulation is already running.",
  "details": {"active_run": {"run_id": "...", "status": "running"}}
}
```

- [ ] **Step 7: Wire default simulator dependencies in `app/main.py`**

Add `default_simulator_service()` that builds `RunStore`, `SimulatorManager`, `SimulatorRepository`, Oracle/ClickHouse dependencies and settings. Extend `create_app(..., simulator_service=None)` and include `simulator_router`.

Bump application version from `0.6.0` to `0.7.0`.

- [ ] **Step 8: Run all API-focused tests**

```bash
pytest tests/test_simulator_api.py tests/test_simulator_service.py tests/test_simulator_manager.py -q
```

Expected: all pass.

- [ ] **Step 9: Commit API and service layer**

```bash
git add app/schemas/simulator.py app/services/simulator.py app/routes/simulator.py app/errors.py app/main.py tests/test_simulator_api.py
git commit -m "feat: expose simulator run control API"
```

---

### Task 6: Build the Simulator Control Room Frontend

**Files:**
- Create: `app/static/js/simulator.js`
- Modify: `app/static/js/app.js`
- Modify: `app/static/js/api.js`
- Modify: `app/static/css/app.css`

**Interfaces:**
- Consumes the Task 5 API contracts.
- Produces `SimulatorPage` with `render()`, `destroy()`, visibility-aware polling, idle/running/paused/draining/completed/failed/stale renders, and Start/Pause/Resume/Stop actions.

- [ ] **Step 1: Preserve backend error code/details in the shared API helper**

Update `app/static/js/api.js`:

```javascript
if (!response.ok) {
  const error = new Error(data.message || "The request could not be completed.");
  error.code = data.error || "request_failed";
  error.details = data.details || {};
  error.status = response.status;
  throw error;
}
```

This lets duplicate Start render the active-run recovery card rather than only a generic toast.

- [ ] **Step 2: Wire SimulatorPage into SPA navigation**

In `app/static/js/app.js`:

```javascript
import { SimulatorPage } from "./simulator.js";
```

and:

```javascript
if(page === "simulator") {
  activePage = new SimulatorPage(shell);
  await activePage.render();
  return;
}
```

The sidebar button already exists in `index.html`; do not add another navigation item.

- [ ] **Step 3: Implement refresh-safe page lifecycle and visibility-aware polling**

`SimulatorPage.render()` must immediately draw a skeleton, call `/api/simulator/status`, and then choose idle or active-run rendering.

Polling rules:

```javascript
pollDelay() {
  return document.hidden ? 5000 : 1000;
}

schedulePoll() {
  window.clearTimeout(this.timer);
  this.timer = window.setTimeout(async () => {
    await this.refresh();
    if (!this.destroyed) this.schedulePoll();
  }, this.pollDelay());
}
```

On `visibilitychange`, refresh immediately when visible. `destroy()` clears timer and removes the visibility listener. Do not add `beforeunload`; refreshing is intentionally safe.

- [ ] **Step 4: Implement the idle configuration experience**

Idle view must show:

- `14.00` events/sec default;
- `10 minutes` default duration;
- `12%` retry default;
- live expected-event calculation;
- population summary `200 taxpayers / 500 devices / 20 stations / 15 error codes`;
- architecture strip `Oracle → Debezium → Kafka → ClickHouse`;
- one clear **Start Simulation** primary action.

Start button submits:

```javascript
await api("/api/simulator/runs", {
  method: "POST",
  body: JSON.stringify({rate, duration_seconds, retry_probability}),
});
```

Disable controls while the request is in flight.

If `error.code === "simulation_already_running"`, render the returned active-run card with **View Active Simulation** rather than an alarming error state.

- [ ] **Step 5: Implement running/paused/draining/completed header and controls**

The top region must prioritize:

```text
Run ID | status | elapsed | remaining | target rate | actual rate | progress
```

Controls:

- `running`: Pause + Stop Run.
- `paused`: Resume + Stop Run; helper text `Source generation is paused. CDC is still draining committed events.`
- `draining`: no Resume/Start; helper text `Source generation has stopped. Waiting for committed events to arrive in ClickHouse.`
- `completed`: Start New Run.
- `failed/stale`: show diagnosis and Start New Run only after there is no active run.

Stop requires an application confirmation modal/drawer, not a browser `confirm()` dialog. Copy must explicitly say committed Oracle rows are retained and the run cannot resume after Stop.

- [ ] **Step 6: Implement the primary reconciliation strip**

Render three visually dominant values:

```text
ORACLE                 IN FLIGHT                 CLICKHOUSE
3,463 committed   →        61        →           3,402 received
14.02 / sec                                     98.2% delivered
```

If Oracle exact count is temporarily unavailable, display worker-generated count with a clear `worker count` note rather than showing a fabricated exact source count.

- [ ] **Step 7: Implement health strip with text + icon + color**

Each stage card shows stage name, status icon/text, and detail. Color is supplementary, never the only state cue.

Examples:

```text
✓ Oracle       HEALTHY      Source reachable
✓ Debezium     RUNNING      Connector and task RUNNING
✓ Kafka        HEALTHY      Broker reachable
✓ ClickHouse   HEALTHY      Analytics reachable
```

- [ ] **Step 8: Implement live event feed without 14 DOM inserts/sec**

Refresh the latest 25–40 events as one batch on each status/event poll. Each compact row shows sequence, TIN, device, error code, seller reference, Oracle ✓, then either `Waiting for CDC…` or `ClickHouse ✓ 6.18s`.

An expandable detail area may show `source_commit_ts`, SCN, commit SCN, Kafka partition/offset and `ingested_at` only when those fields are actually present.

- [ ] **Step 9: Implement operational charts and run KPIs**

Run KPIs:

```text
Error Events | Affected Invoices | Retry Events | Taxpayers | Devices | Error Codes
```

Charts remain lightweight SVG/HTML consistent with the existing codebase:

- source/arrival throughput over recent intervals;
- latency summary emphasizing P50/P95 with P99/max secondary.

Do not turn this page into a duplicate of `EFRIS Errors`; business analysis stays there.

- [ ] **Step 10: Add responsive Control Room CSS using existing design tokens**

Add `.sim-*` classes to `app/static/css/app.css` using existing variables such as `--ura-blue`, `--ura-yellow`, `--success`, `--warning`, `--danger`, `--border`, `--surface`.

Desktop: reconciliation strip and health cards remain one-row where practical.

Tablet/mobile: collapse to single-column cards, keep controls reachable, allow the event table to horizontally scroll only if required.

Respect existing focus styles and add `:focus-visible` behavior for new custom buttons if any.

Avoid continuous animations; only the running status dot may use a subtle pulse, and it must not be required to understand status.

- [ ] **Step 11: Run JavaScript syntax and application compile checks**

```bash
node --check app/static/js/api.js
node --check app/static/js/app.js
node --check app/static/js/simulator.js
python -m compileall -q app
```

Expected: all exit 0.

- [ ] **Step 12: Commit the Control Room UI**

```bash
git add app/static/js/api.js app/static/js/app.js app/static/js/simulator.js app/static/css/app.css
git commit -m "feat: add EFRIS simulator control room UI"
```

---

### Task 7: Runtime Documentation, History UX and CLI Compatibility

**Files:**
- Modify: `simulation/README.md`
- Modify: `docs/efris-error-monitor.md`
- Modify: `.env.example`
- Modify: `scripts/run_efris_simulator.py` if any final compatibility gaps remain

**Interfaces:**
- Keeps CLI commands working for engineering diagnostics while browser-controlled mode becomes the demo default.

- [ ] **Step 1: Document browser mode and lifecycle**

Add this explicit behavior to `simulation/README.md`:

```text
Browser Start → detached worker → Oracle source writes
Browser refresh/navigation/tab closure → no effect on worker
Pause → no new Oracle commits, downstream keeps draining
Resume → same run ID/source prefix and next event sequence
Stop → generation ends permanently, state becomes Draining until ClickHouse reconciles
```

Include API endpoints and runtime state location. State files contain no secrets.

- [ ] **Step 2: Document new `.env` requirements for a new terminal/app process**

Keep the source connection keys:

```text
CDC_APP_USER=CDC_APP
CDC_APP_PASSWORD=<local secret only>
CDC_APP_DSN=localhost:1521/FREEPDB1
```

and non-secret control-room settings:

```text
DEBEZIUM_URL=http://localhost:8083
DEBEZIUM_FLAT_CONNECTOR=oracle-cdc-flat
KAFKA_BOOTSTRAP=localhost:9092
SIMULATOR_RUNTIME_DIR=runtime/simulator
SIMULATOR_STALE_SECONDS=10
```

Do not add real passwords.

- [ ] **Step 3: Update EFRIS monitor documentation with the proven baseline and new control flow**

Record the already-observed baseline separately from future tests:

```text
One-minute source test:
841 source commits produced by the pre-control-room CLI boundary behavior
14.02 events/sec
0 source failures
841 ClickHouse rows received
90 retry events
188 taxpayers represented
335 devices represented
P50 CDC latency 6362 ms
P95 CDC latency 9914 ms
P99 CDC latency 10938 ms
```

Explain that the refactored finite-run engine intentionally uses exact target-event count, so future `14 × 60` finite runs should produce exactly `840` events.

- [ ] **Step 4: Confirm CLI compatibility**

```bash
python scripts/run_efris_simulator.py --help
python -m compileall -q scripts app
```

Do not run another 14/sec source workload as part of this documentation step.

- [ ] **Step 5: Commit docs and compatibility updates**

```bash
git add simulation/README.md docs/efris-error-monitor.md .env.example scripts/run_efris_simulator.py
git commit -m "docs: document browser-controlled EFRIS simulation"
```

---

### Task 8: Full Test Pass and RHEL End-to-End Verification

**Files:**
- Modify only files proven necessary by failures discovered during this verification task.
- Test: all simulator tests plus existing project tests.

**Interfaces:**
- Produces a runtime-verified Simulator Control Room ready for the 10-minute demo workload.

- [ ] **Step 1: Run the full automated test and syntax suite**

```bash
pytest -q
python -m compileall -q app scripts
node --check app/static/js/api.js
node --check app/static/js/app.js
node --check app/static/js/simulator.js
node --check app/static/js/efris_errors.js
```

Expected: all tests/syntax checks pass.

- [ ] **Step 2: Pull the implementation on the RHEL POC host and load environment safely**

```bash
cd /home/jkasule/cdc-clickhouse-poc
source venv/bin/activate
set -a
source .env
set +a
```

Verify without printing the password:

```bash
python3 - <<'PY'
import os
print("USER:", os.getenv("CDC_APP_USER"))
print("DSN :", os.getenv("CDC_APP_DSN"))
print("PASS:", "SET" if os.getenv("CDC_APP_PASSWORD") else "MISSING")
PY
```

- [ ] **Step 3: Start/restart FastAPI and open Simulator**

Use the existing application launch method for this POC. If running manually:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open **Simulator** from the existing SYSTEM sidebar.

- [ ] **Step 4: Run a 60-second browser test at 14/sec and refresh mid-run**

Configure:

```text
Rate: 14 events/sec
Duration: 60 seconds
Retry: 12%
Expected source events: 840
```

During the run:

1. verify status becomes RUNNING;
2. refresh the browser around 15–20 seconds;
3. verify the page says it reconnected to the same run ID;
4. verify the source counter continues through the refresh;
5. navigate to EFRIS Errors and back to Simulator;
6. verify same run remains active.

Expected final source count: exactly `840` successful Oracle commits.

- [ ] **Step 5: Verify Pause/Resume semantics in a second short run**

Start another finite run, Pause after approximately 10 seconds, and verify:

```text
Oracle committed count: stops increasing
ClickHouse received: continues increasing until in-flight approaches 0
Active elapsed time: stops advancing while paused
```

Resume and verify:

```text
same run_id
same source_prefix
next source sequence continues without reset
no catch-up burst above the requested rate caused by paused time
```

- [ ] **Step 6: Verify Stop → Draining → Completed**

Stop before the run reaches its target. Confirm:

1. no new Oracle run-prefix rows are generated after Stop;
2. UI status becomes DRAINING;
3. ClickHouse count continues catching up;
4. once `clickhouse_received == oracle_committed`, UI becomes COMPLETED;
5. completed run remains visible in history;
6. a new run can now be started.

- [ ] **Step 7: Verify second-browser duplicate Start protection**

While a run is active, open another browser/session and press Start. Expected:

```text
HTTP 409 simulation_already_running
UI shows active run metadata
View Active Simulation action reconnects to the existing run
no second worker process is launched
```

- [ ] **Step 8: Verify truthful run analytics and lineage against ClickHouse**

For the browser-generated run prefix, compare UI counts to ClickHouse:

```sql
SELECT
    count() AS error_events,
    uniqExact(tuple(tin, seller_reference_no)) AS affected_invoices,
    count() - uniqExact(tuple(tin, seller_reference_no)) AS retry_events,
    uniqExact(tin) AS taxpayers,
    uniqExact(device_no) AS devices,
    uniqExact(return_code) AS error_codes
FROM analytics.raw_efris_error_log
WHERE startsWith(ifNull(id, ''), '<RUN_SOURCE_PREFIX>-');
```

Latency:

```sql
SELECT
    round(avg(dateDiff('millisecond', source_commit_ts, ingested_at)), 2) AS avg_ms,
    quantileExact(0.50)(dateDiff('millisecond', source_commit_ts, ingested_at)) AS p50_ms,
    quantileExact(0.95)(dateDiff('millisecond', source_commit_ts, ingested_at)) AS p95_ms,
    quantileExact(0.99)(dateDiff('millisecond', source_commit_ts, ingested_at)) AS p99_ms,
    max(dateDiff('millisecond', source_commit_ts, ingested_at)) AS max_ms
FROM analytics.raw_efris_error_log
WHERE startsWith(ifNull(id, ''), '<RUN_SOURCE_PREFIX>-');
```

Replace `<RUN_SOURCE_PREFIX>` with the source prefix displayed by the UI for the run under test.

- [ ] **Step 9: Run the final 10-minute demonstration workload from the UI**

Only after Steps 1–8 pass:

```text
Rate: 14 events/sec
Duration: 600 seconds
Retry: 12%
Target: 8,400 exact Oracle commits
```

Success criteria:

```text
Oracle committed       8,400
Source failures        0
ClickHouse received    8,400 after drain
Missing after drain    0
No steadily increasing latency/backlog trend
Browser refresh        safe
Pause/Resume           proven in prior test
Duplicate Start        prevented
```

- [ ] **Step 10: Commit any verification-only fixes, then record final evidence in PR #2**

If verification required fixes, commit only the tested corrections:

```bash
git add <exact-fixed-files>
git commit -m "fix: harden simulator control room runtime behavior"
```

Then add a PR comment summarizing automated tests, 60-second browser run, refresh reconnect, Pause/Resume, Stop/Drain, duplicate-Start protection, and final 10-minute reconciliation. Do not claim a check passed unless its output was actually observed.

---

## Plan Self-Review

### Spec coverage

- Refresh/navigation safety: Tasks 3, 5, 6, 8.
- One active run only: Tasks 2, 3, 5, 6, 8.
- Pause/Resume/Stop semantics: Tasks 3, 5, 6, 8.
- Durable run identity and sequence: Tasks 1, 2, 3, 8.
- Oracle-only source writes: Tasks 1, 3, 8.
- Exact Oracle vs ClickHouse reconciliation: Tasks 4, 5, 6, 8.
- Truthful intermediate-stage presentation: Tasks 4 and 6.
- Live events and lineage: Tasks 4 and 6.
- Run analytics and CDC latency: Tasks 4, 5, 6, 8.
- Pipeline health: Tasks 4 and 6.
- Completed-run history: Tasks 2, 5, 6, 8.
- Stale worker detection: Tasks 3 and 5.
- UI/UX quality and responsive behavior: Task 6.
- CLI reuse rather than duplicated generation logic: Tasks 1 and 7.
- No extra infrastructure dependencies: maintained throughout.
- 14/sec exact 60-second and 10-minute runtime verification: Task 8.

### Placeholder scan

The implementation tasks contain no intended `TBD`/`TODO` work. One illustrative test step explicitly instructs the implementer to replace an ellipsis before committing; the committed test must contain the complete fixture and assertions described in that step.

### Type/interface consistency

`RunConfig`, `RunRecord`, `RunStore`, `SimulatorManager`, `SimulatorRepository`, and `SimulatorService` names are used consistently across tasks. Run commands are `run|pause|stop`; actual run statuses are `starting|running|paused|draining|completed|failed|stale`. The source prefix is stable for the entire run and is the join/filter key used by Oracle, ClickHouse, the API and the UI.
