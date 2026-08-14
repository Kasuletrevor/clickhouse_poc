# EFRIS Simulator Control Room Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a refresh-safe browser Simulator Control Room that starts one detached server-side EFRIS workload, writes only to Oracle, supports Pause/Resume/Stop, and continuously reconciles Oracle source commits with ClickHouse delivery and CDC latency.

**Architecture:** FastAPI controls a detached Python worker process. The worker owns the Oracle connection and event-generation loop; the browser only calls control/status APIs. A small atomic JSON registry under `runtime/simulator/` survives page refreshes and FastAPI restarts. Status combines worker state, exact Oracle rows, ClickHouse rows, real CDC lineage, and independent Oracle/Debezium/Kafka/ClickHouse health checks.

**Tech Stack:** Python 3, FastAPI, `oracledb`, existing ClickHouse HTTP wrapper, standard-library `subprocess`, `fcntl`, `urllib`, `socket`, JSON, vanilla JavaScript, existing HTML/CSS shell, pytest/httpx.

## Global Constraints

- Browser refresh, navigation, tab closure, and reopening the app must not stop an active run.
- The worker writes only to `CDC_APP.T_INVOICE_ERROR_LOG`; neither browser nor FastAPI publishes directly to Kafka or writes to ClickHouse.
- Only one simulator run may be active on the POC host.
- Default run: `14.00 events/sec`, `600 seconds`, `12% retry probability`, `8,400` exact target events.
- Pause stops new Oracle writes and freezes active-generation time; downstream CDC continues draining.
- Resume continues the same `run_id`, `source_prefix`, seller-reference retry pool, and event sequence without a catch-up burst.
- Stop is final for that run: source generation ends, state becomes `draining`, then `completed` when ClickHouse receives all committed source events.
- Finite runs stop by exact target count, not a wall-clock boundary, so `14 × 60 = 840` and `14 × 600 = 8,400` exactly when there are no source failures.
- Intermediate systems show health only. The UI must not claim an individual event reached Debezium or Kafka before downstream evidence exists.
- Runtime state must contain no passwords, tokens, connection strings, or other secrets.
- `T_INVOICE_ERROR_LOG.ID` is `VARCHAR2(32)`; run-scoped source IDs must fit that column.
- Keep FastAPI + HTML/CSS + vanilla JavaScript. Do not add Celery, Redis, React, Node, or another job system.
- Existing synthetic population remains `20 stations`, `200 taxpayers`, `500 devices`, `15 error codes`.

## File Map

**Create**

- `app/simulator/__init__.py` — package marker.
- `app/simulator/models.py` — `RunConfig`, `RunRecord`, statuses, run identity.
- `app/simulator/engine.py` — reusable weighted EFRIS event factory and rate pacer.
- `app/simulator/store.py` — atomic JSON registry and active-run lock.
- `app/simulator/worker.py` — detached Oracle workload process.
- `app/simulator/manager.py` — process launch, Pause/Resume/Stop, stale detection.
- `app/repositories/simulator.py` — exact Oracle/ClickHouse reconciliation, lineage, latency, health.
- `app/services/simulator.py` — run use cases and status composition.
- `app/schemas/simulator.py` — Start request validation.
- `app/routes/simulator.py` — Simulator REST API.
- `app/static/js/simulator.js` — Simulator Control Room page.
- `tests/test_simulator_models.py`
- `tests/test_simulator_engine.py`
- `tests/test_simulator_store.py`
- `tests/test_simulator_manager.py`
- `tests/test_simulator_service.py`
- `tests/test_simulator_api.py`

**Modify**

- `scripts/run_efris_simulator.py`
- `app/config.py`
- `app/errors.py`
- `app/main.py`
- `app/static/js/api.js`
- `app/static/js/app.js`
- `app/static/css/app.css`
- `.gitignore`
- `.env.example`
- `simulation/README.md`
- `docs/efris-error-monitor.md`

---

### Task 1: Extract the Reusable Workload Engine

**Files:**
- Create: `app/simulator/__init__.py`
- Create: `app/simulator/models.py`
- Create: `app/simulator/engine.py`
- Modify: `scripts/run_efris_simulator.py`
- Test: `tests/test_simulator_models.py`
- Test: `tests/test_simulator_engine.py`

**Interfaces:**
- Produces `RunConfig`, `RunRecord`, `make_run_identity()`, `format_source_id()`, `EfrisEventFactory`, `RatePacer`.
- `RunConfig.target_events` returns `None` only for continuous duration `0`; otherwise `round(rate * duration_seconds)`.
- `make_run_identity(now, token)` returns `(run_id, source_prefix)`.
- `EfrisEventFactory.next_bindings(cursor, sequence)` returns the bind dictionary for one Oracle insert.

- [ ] **Step 1: Write failing model tests**

```python
# tests/test_simulator_models.py
from datetime import datetime, timezone

from app.simulator.models import RunConfig, make_run_identity


def test_finite_target_is_exact():
    config = RunConfig(rate=14.0, duration_seconds=60, retry_probability=0.12, random_seed=1)
    assert config.target_events == 840


def test_continuous_run_has_no_target():
    config = RunConfig(rate=14.0, duration_seconds=0, retry_probability=0.12, random_seed=1)
    assert config.target_events is None


def test_identity_is_traceable_and_compact():
    now = datetime(2026, 8, 6, 8, 47, 1, tzinfo=timezone.utc)
    run_id, prefix = make_run_identity(now=now, token="A1")
    assert run_id == "EFR-20260806-084701-A1"
    assert prefix == "S260806A1"
    assert len(f"{prefix}-999999") <= 32
```

- [ ] **Step 2: Run the tests and verify the expected import failure**

```bash
pytest tests/test_simulator_models.py -q
```

Expected: failure because `app.simulator.models` does not yet exist.

- [ ] **Step 3: Implement run models and identity generation**

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
        return None if self.duration_seconds == 0 else round(self.rate * self.duration_seconds)


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
    return f"EFR-{now:%Y%m%d-%H%M%S}-{token}", f"S{now:%y%m%d}{token}"
```

- [ ] **Step 4: Write failing engine tests**

```python
# tests/test_simulator_engine.py
from app.simulator.engine import RatePacer, format_source_id


def test_source_id_uses_monotonic_run_sequence():
    assert format_source_id("S260806A1", 1) == "S260806A1-000001"
    assert format_source_id("S260806A1", 840) == "S260806A1-000840"


def test_pacer_reset_uses_current_clock():
    values = iter([100.0, 105.0])
    pacer = RatePacer(rate=14.0, clock=lambda: next(values), sleeper=lambda seconds: None)
    pacer.reset()
    assert pacer.next_due == 105.0
```

- [ ] **Step 5: Implement source ID and monotonic pacer**

```python
# app/simulator/engine.py
import time


def format_source_id(source_prefix: str, sequence: int) -> str:
    value = f"{source_prefix}-{sequence:06d}"
    if len(value) > 32:
        raise ValueError("Simulator source ID exceeds T_INVOICE_ERROR_LOG.ID length")
    return value


class RatePacer:
    def __init__(self, rate: float, clock=time.perf_counter, sleeper=time.sleep):
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

In the same file, extract the current JSON loading, weighted taxpayer selection, taxpayer-owned device selection, 15-code weighted selection, products, retry pool, seller-reference sequence, gross/tax generation, and bind creation into `EfrisEventFactory`. Preserve current business behavior exactly except for deterministic run-scoped `source_id`.

- [ ] **Step 6: Refactor the CLI to use the shared engine and exact finite target count**

Finite loop:

```python
target = config.target_events
while target is None or generated < target:
    pacer.wait_next()
    bindings = factory.next_bindings(cursor, generated + 1)
    cursor.execute(INSERT_SQL, bindings)
    conn.commit()
    generated += 1
```

Expected future one-minute run at 14/sec: exactly `840` successful commits.

- [ ] **Step 7: Verify and commit**

```bash
pytest tests/test_simulator_models.py tests/test_simulator_engine.py -q
python -m compileall -q app scripts
git add app/simulator scripts/run_efris_simulator.py tests/test_simulator_models.py tests/test_simulator_engine.py
git commit -m "refactor: extract reusable EFRIS simulation engine"
```

---

### Task 2: Add Durable Run State and Detached Worker Control

**Files:**
- Create: `app/simulator/store.py`
- Create: `app/simulator/worker.py`
- Create: `app/simulator/manager.py`
- Modify: `.gitignore`
- Test: `tests/test_simulator_store.py`
- Test: `tests/test_simulator_manager.py`

**Interfaces:**
- `RunStore.create_run(record)`, `get_run(run_id)`, `get_active_run()`, `update_run(run_id, mutator)`, `clear_active(run_id)`, `list_runs(limit)`.
- `SimulatorManager.start(config)`, `pause(run_id)`, `resume(run_id)`, `stop(run_id)`, `reconcile_worker_state(run)`.
- Worker entry point: `python -m app.simulator.worker --run-id RUN_ID`.
- Durable commands: `run`, `pause`, `stop`; actual statuses: `starting`, `running`, `paused`, `draining`, `completed`, `failed`, `stale`.

- [ ] **Step 1: Write failing store tests**

```python
# tests/test_simulator_store.py
import pytest

from app.simulator.models import RunRecord
from app.simulator.store import ActiveRunExists, RunStore


def make_record(run_id="EFR-1", prefix="S1"):
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


def test_only_one_active_run_is_allowed(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(make_record())
    with pytest.raises(ActiveRunExists):
        store.create_run(make_record("EFR-2", "S2"))


def test_atomic_update_round_trips(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(make_record())
    store.update_run("EFR-1", lambda run: setattr(run, "generated", 14))
    assert store.get_run("EFR-1").generated == 14
```

- [ ] **Step 2: Implement locked atomic registry**

`RunStore` must create `runtime/simulator/runs/`, lock `runtime/simulator/registry.lock` with `fcntl.flock(LOCK_EX)`, write JSON to a temporary file in the same directory, then call `os.replace()` for atomic replacement. `create_run()` checks and writes the active pointer while holding the same lock.

Add to `.gitignore`:

```gitignore
runtime/simulator/
```

- [ ] **Step 3: Write failing manager state-transition tests**

```python
# tests/test_simulator_manager.py
from app.simulator.manager import SimulatorManager
from app.simulator.models import RunConfig, RunRecord
from app.simulator.store import RunStore


def running_record():
    return RunRecord(
        run_id="EFR-TEST",
        source_prefix="S260806A1",
        status="running",
        command="run",
        rate=14.0,
        duration_seconds=60,
        target_events=840,
        retry_probability=0.12,
        random_seed=1,
        pid=4321,
    )


def test_pause_resume_stop_change_durable_command(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(running_record())
    manager = SimulatorManager(store=store, launcher=lambda *args, **kwargs: None, pid_alive=lambda pid: True)

    paused = manager.pause("EFR-TEST")
    assert paused.command == "pause"

    store.update_run("EFR-TEST", lambda run: setattr(run, "status", "paused"))
    resumed = manager.resume("EFR-TEST")
    assert resumed.command == "run"

    store.update_run("EFR-TEST", lambda run: setattr(run, "status", "running"))
    stopped = manager.stop("EFR-TEST")
    assert stopped.command == "stop"
```

- [ ] **Step 4: Implement detached worker launch**

Use the same interpreter and inherited environment; store only PID and sanitized state:

```python
process = subprocess.Popen(
    [sys.executable, "-m", "app.simulator.worker", "--run-id", run.run_id],
    cwd=str(project_root),
    stdin=subprocess.DEVNULL,
    stdout=log_handle,
    stderr=subprocess.STDOUT,
    start_new_session=True,
    close_fds=True,
)
```

If launch fails, mark the run `failed` and clear its active pointer.

- [ ] **Step 5: Implement worker Pause/Resume/Stop loop**

Core loop:

```python
while run.target_events is None or run.generated < run.target_events:
    current = store.get_run(run_id)

    if current.command == "stop":
        set_status("draining")
        break

    if current.command == "pause":
        enter_paused_state()
        time.sleep(0.2)
        continue

    if resumed_from_pause:
        pacer.reset()

    pacer.wait_next()
    bindings = factory.next_bindings(cursor, current.last_sequence + 1)
    cursor.execute(INSERT_SQL, bindings)
    conn.commit()
    record_successful_commit()
```

The worker must update heartbeat at least once per second, preserve event sequence, exclude pause duration from active elapsed time, bound source-rate history, set `draining` on natural finite completion, and set `failed` with a sanitized message on fatal source failure.

- [ ] **Step 6: Implement stale-worker detection**

For `starting`, `running`, or `paused`, mark the run `stale` when the PID is absent or heartbeat age exceeds the configured threshold. Use `os.kill(pid, 0)` only as a liveness probe.

- [ ] **Step 7: Verify and commit**

```bash
pytest tests/test_simulator_store.py tests/test_simulator_manager.py -q
python -m compileall -q app/simulator
git add app/simulator/store.py app/simulator/worker.py app/simulator/manager.py tests/test_simulator_store.py tests/test_simulator_manager.py .gitignore
git commit -m "feat: add detached simulator worker control"
```

---

### Task 3: Add Exact Reconciliation, Lineage, Latency and Health

**Files:**
- Create: `app/repositories/simulator.py`
- Modify: `app/config.py`
- Modify: `.env.example`
- Test: `tests/test_simulator_service.py`

**Interfaces:**
- `oracle_run_summary(source_prefix)`
- `clickhouse_run_summary(source_prefix)`
- `recent_events(source_prefix, limit=40)`
- `arrival_throughput(source_prefix)`
- `pipeline_health()`

- [ ] **Step 1: Add settings**

Add to `Settings`:

```python
debezium_url: str = os.getenv("DEBEZIUM_URL", "http://localhost:8083")
debezium_flat_connector: str = os.getenv("DEBEZIUM_FLAT_CONNECTOR", "oracle-cdc-flat")
kafka_bootstrap: str = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
simulator_runtime_dir: str = os.getenv("SIMULATOR_RUNTIME_DIR", "runtime/simulator")
simulator_stale_seconds: int = int(os.getenv("SIMULATOR_STALE_SECONDS", "10"))
```

Document the same keys with blank/non-secret defaults in `.env.example`.

- [ ] **Step 2: Implement exact Oracle run summary with a bound prefix**

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

- [ ] **Step 3: Implement ClickHouse delivery and latency summary**

Use the existing ClickHouse query wrapper and a safely escaped server-generated prefix:

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
WHERE startsWith(ifNull(id, ''), 'S260806A1-')
```

The literal prefix above is the test fixture example; production code substitutes only the run's validated server-generated prefix.

- [ ] **Step 4: Implement truthful recent-event merge**

Read the latest Oracle rows for the run and matching ClickHouse rows, merge by `ID`, and return rows with:

```python
{
    "source_id": "S260806A1-000123",
    "sequence": 123,
    "tin": "SIMTIN000042",
    "device_no": "SIMTIN000042_02",
    "return_code": "1600",
    "seller_reference_no": "SIMTIN000042-INV-00001001",
    "oracle_committed": True,
    "clickhouse_received": False,
    "cdc_latency_ms": None,
    "source_scn": None,
    "source_commit_scn": None,
    "kafka_partition": None,
    "kafka_offset": None,
}
```

When ClickHouse has the event, populate the real commit timestamp, SCNs, Kafka partition/offset, ingestion timestamp, and latency. Never synthesize those fields.

- [ ] **Step 5: Implement independent stage health**

- Oracle: `SELECT 1 FROM DUAL`.
- Debezium: HTTP GET `${DEBEZIUM_URL}/connectors/${DEBEZIUM_FLAT_CONNECTOR}/status`; healthy only when connector and task 0 are `RUNNING`.
- Kafka: `socket.create_connection()` to configured broker host/port with 1-second timeout; label result as broker reachability, not delivery proof.
- ClickHouse: lightweight `SELECT 1` using the existing wrapper.

Return each stage as `{status, detail}` where status is `healthy`, `degraded`, `unavailable`, or `unknown`.

- [ ] **Step 6: Write reconciliation tests**

```python
# tests/test_simulator_service.py
def test_reconciliation_math():
    oracle_committed = 840
    clickhouse_received = 812
    in_flight = max(oracle_committed - clickhouse_received, 0)
    delivery_percent = clickhouse_received / oracle_committed * 100
    assert in_flight == 28
    assert round(delivery_percent, 2) == 96.67


def test_retry_math():
    error_events = 840
    affected_invoices = 751
    assert error_events - affected_invoices == 89
```

Add fakes that also verify analytics-unavailable behavior leaves worker/source state visible.

- [ ] **Step 7: Verify and commit**

```bash
pytest tests/test_simulator_service.py -q
python -m compileall -q app
git add app/repositories/simulator.py app/config.py .env.example tests/test_simulator_service.py
git commit -m "feat: add simulator CDC reconciliation metrics"
```

---

### Task 4: Expose Simulator API and Run Lifecycle Service

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

- [ ] **Step 1: Add strict Start schema**

```python
# app/schemas/simulator.py
from pydantic import BaseModel, Field


class SimulatorStartRequest(BaseModel):
    rate: float = Field(default=14.0, gt=0, le=1000)
    duration_seconds: int = Field(default=600, ge=0, le=86400)
    retry_probability: float = Field(default=0.12, ge=0, le=1)
```

These are POC safety bounds, not infrastructure-capacity claims.

- [ ] **Step 2: Extend APIError with optional details**

```python
class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
```

Update `app/main.py` error handler to include `details` only when non-empty.

- [ ] **Step 3: Implement SimulatorService status composition**

`status()` must load active run, reconcile worker liveness, query Oracle/ClickHouse summaries, compute `in_flight` and `delivery_percent`, include health and recent events, and finalize `draining -> completed` when `clickhouse_received >= oracle_committed`.

Completed runs remain in history after the active pointer is cleared.

- [ ] **Step 4: Implement API routes and duplicate-run error**

```python
@router.post("/runs", status_code=201)
def start_run(payload: SimulatorStartRequest, request: Request):
    return simulator_service(request).start(payload)


@router.get("/status")
def status(request: Request):
    return simulator_service(request).status()
```

Duplicate Start returns HTTP `409`:

```json
{
  "error": "simulation_already_running",
  "message": "A simulation is already running.",
  "details": {
    "active_run": {
      "run_id": "EFR-20260806-084701-A1",
      "status": "running"
    }
  }
}
```

- [ ] **Step 5: Wire the service into `create_app()`**

Add `default_simulator_service()`, `simulator_service=None` injection, router include, and bump application version to `0.7.0`.

- [ ] **Step 6: Write and run API tests**

```python
# tests/test_simulator_api.py
from fastapi.testclient import TestClient

from app.main import create_app


class FakeSimulatorService:
    def start(self, payload):
        return {"run_id": "EFR-TEST", "status": "starting"}

    def status(self):
        return {"active": None, "history": []}


def test_start_returns_created_run(noop_services):
    app = create_app(simulator_service=FakeSimulatorService(), **noop_services)
    client = TestClient(app)
    response = client.post("/api/simulator/runs", json={
        "rate": 14,
        "duration_seconds": 600,
        "retry_probability": 0.12,
    })
    assert response.status_code == 201
    assert response.json()["run_id"] == "EFR-TEST"
```

Define `noop_services` in the same test module or existing `conftest.py` as complete fake services for every other `create_app()` dependency so tests never touch real Oracle or ClickHouse.

Run:

```bash
pytest tests/test_simulator_api.py tests/test_simulator_service.py tests/test_simulator_manager.py -q
```

- [ ] **Step 7: Commit API work**

```bash
git add app/schemas/simulator.py app/services/simulator.py app/routes/simulator.py app/errors.py app/main.py tests/test_simulator_api.py
git commit -m "feat: expose simulator run control API"
```

---

### Task 5: Build the High-Quality Simulator Control Room UI

**Files:**
- Create: `app/static/js/simulator.js`
- Modify: `app/static/js/api.js`
- Modify: `app/static/js/app.js`
- Modify: `app/static/css/app.css`

**Interfaces:**
- Produces `SimulatorPage.render()`, `refresh()`, `destroy()`, idle/active/completed renderers, visibility-aware polling, and Start/Pause/Resume/Stop actions.

- [ ] **Step 1: Preserve backend error metadata in `api.js`**

```javascript
if (!response.ok) {
  const error = new Error(data.message || "The request could not be completed.");
  error.code = data.error || "request_failed";
  error.details = data.details || {};
  error.status = response.status;
  throw error;
}
```

- [ ] **Step 2: Wire Simulator navigation**

```javascript
import { SimulatorPage } from "./simulator.js";
```

and inside `navigate(page)`:

```javascript
if (page === "simulator") {
  activePage = new SimulatorPage(shell);
  await activePage.render();
  return;
}
```

The sidebar Simulator item already exists; do not duplicate it.

- [ ] **Step 3: Implement refresh-safe polling lifecycle**

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

On `visibilitychange`, immediately refresh when visible. `destroy()` removes the listener and timer. Do not add a `beforeunload` warning because browser refresh is intentionally safe.

- [ ] **Step 4: Implement idle configuration**

Show `14.00 events/sec`, `10 minutes`, `12% retries`, calculated expected events, `200 taxpayers`, `500 devices`, `20 stations`, `15 error codes`, architecture strip, and one primary **Start Simulation** action.

Start submits:

```javascript
await api("/api/simulator/runs", {
  method: "POST",
  body: JSON.stringify({rate, duration_seconds, retry_probability}),
});
```

If `error.code === "simulation_already_running"`, show the returned active-run card and **View Active Simulation** instead of a generic error.

- [ ] **Step 5: Implement active-run hierarchy and controls**

Header priority:

```text
Run ID | RUNNING/PAUSED/DRAINING | progress | elapsed | remaining | target rate | actual rate
```

Controls:

- running: **Pause**, **Stop Run**;
- paused: **Resume**, **Stop Run**;
- draining: no Resume/Start;
- completed: **Start New Run**;
- failed/stale: clear diagnostic copy and recovery action only after no active worker remains.

Stop uses an application drawer/modal, not browser `confirm()`. Copy states that committed Oracle rows remain and the run cannot resume after Stop.

- [ ] **Step 6: Implement dominant source-to-destination reconciliation**

```text
ORACLE                 IN FLIGHT                 CLICKHOUSE
3,463 committed   ->       61       ->           3,402 received
14.02 / sec                                     98.2% delivered
```

If Oracle exact count is temporarily unavailable, label the worker counter explicitly as a fallback rather than presenting it as an exact database count.

- [ ] **Step 7: Implement health strip and live event feed**

Health cards always combine icon, text and color:

```text
✓ Oracle       HEALTHY      Source reachable
✓ Debezium     RUNNING      Connector and task RUNNING
✓ Kafka        HEALTHY      Broker reachable
✓ ClickHouse   HEALTHY      Analytics reachable
```

Refresh recent events as a 25–40 row batch, not 14 DOM inserts per second. Pending events show `Oracle ✓ / Waiting for CDC`; arrived events show `ClickHouse ✓` and real latency. Expanded lineage shows SCNs and Kafka partition/offset only when present in ClickHouse.

- [ ] **Step 8: Implement operational KPIs and charts**

KPIs: Error Events, Affected Invoices, Retry Events, Taxpayers, Devices, Error Codes.

Visuals: recent source/arrival throughput and CDC latency summary emphasizing P50/P95, with P99/max secondary. Keep business-analysis charts on the existing EFRIS Errors page.

- [ ] **Step 9: Add responsive `.sim-*` CSS using existing design tokens**

Use existing `--ura-blue`, `--ura-yellow`, `--success`, `--warning`, `--danger`, `--border`, `--surface`. Desktop favors a horizontal operations-console flow; tablet/mobile collapses cleanly. Status meaning must never depend on color alone. Avoid distracting continuous animation.

- [ ] **Step 10: Verify and commit frontend**

```bash
node --check app/static/js/api.js
node --check app/static/js/app.js
node --check app/static/js/simulator.js
python -m compileall -q app
git add app/static/js/api.js app/static/js/app.js app/static/js/simulator.js app/static/css/app.css
git commit -m "feat: add EFRIS simulator control room UI"
```

---

### Task 6: Documentation and Full RHEL Verification

**Files:**
- Modify: `simulation/README.md`
- Modify: `docs/efris-error-monitor.md`
- Modify: `.env.example`
- Test: full repository plus live RHEL verification.

- [ ] **Step 1: Document browser-controlled lifecycle and new settings**

Document:

```text
Browser Start -> detached worker -> Oracle source writes
Refresh/navigation/tab closure -> worker continues
Pause -> source stops, CDC drains
Resume -> same run and next sequence
Stop -> Draining -> Completed after reconciliation
```

`.env.example` contains only non-secret/default entries:

```text
DEBEZIUM_URL=http://localhost:8083
DEBEZIUM_FLAT_CONNECTOR=oracle-cdc-flat
KAFKA_BOOTSTRAP=localhost:9092
SIMULATOR_RUNTIME_DIR=runtime/simulator
SIMULATOR_STALE_SECONDS=10
```

Keep `CDC_APP_PASSWORD=` blank.

- [ ] **Step 2: Record the already-proven pre-Control-Room baseline accurately**

In `docs/efris-error-monitor.md`, record:

```text
Pre-Control-Room one-minute run:
841 commits from the old elapsed-time boundary loop
14.02 events/sec
0 source failures
841 ClickHouse rows
90 retries
188 taxpayers
335 devices
P50 6362 ms
P95 9914 ms
P99 10938 ms
```

Also state that the refactored finite engine deliberately changes the count boundary so new one-minute runs target exactly `840`.

- [ ] **Step 3: Run the complete automated suite**

```bash
pytest -q
python -m compileall -q app scripts
node --check app/static/js/api.js
node --check app/static/js/app.js
node --check app/static/js/simulator.js
node --check app/static/js/efris_errors.js
```

Expected: every command exits 0.

- [ ] **Step 4: Run a 60-second browser test and refresh mid-run**

Use `14 events/sec`, `60 seconds`, `12% retry`, expected `840`.

Verify RUNNING state, refresh at approximately 15–20 seconds, reconnect to the same run ID, navigate away/back, and finish at exactly 840 successful source commits if there are no source failures.

- [ ] **Step 5: Verify Pause/Resume in a second short run**

While paused, Oracle committed count stops, ClickHouse continues draining, and active elapsed time stops. Resume keeps the same run/source prefix and sequence and does not burst above the requested rate to compensate for paused time.

- [ ] **Step 6: Verify Stop -> Draining -> Completed**

Stop before target. Confirm no further Oracle source rows, DRAINING status, ClickHouse catches up, then COMPLETED when counts reconcile. Confirm the completed run remains in history and a new run can start.

- [ ] **Step 7: Verify duplicate Start protection from a second browser**

Expected: HTTP 409 `simulation_already_running`, active-run metadata shown, no second worker PID created.

- [ ] **Step 8: Reconcile the browser run directly in ClickHouse without manual prefix typing**

Extract the most recent run prefix from persisted history:

```bash
RUN_PREFIX=$(python3 - <<'PY'
import json
from pathlib import Path

runs = sorted(Path("runtime/simulator/runs").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
with runs[0].open() as handle:
    print(json.load(handle)["source_prefix"])
PY
)
echo "Run prefix: $RUN_PREFIX"
```

Then run ClickHouse using the shell variable:

```bash
sudo docker exec poc-clickhouse clickhouse-client --user kjt --database analytics --query "
SELECT
    count() AS error_events,
    uniqExact(tuple(tin, seller_reference_no)) AS affected_invoices,
    count() - uniqExact(tuple(tin, seller_reference_no)) AS retry_events,
    uniqExact(tin) AS taxpayers,
    uniqExact(device_no) AS devices,
    uniqExact(return_code) AS error_codes
FROM raw_efris_error_log
WHERE startsWith(ifNull(id, ''), '${RUN_PREFIX}-')"
```

Latency:

```bash
sudo docker exec poc-clickhouse clickhouse-client --user kjt --database analytics --query "
SELECT
    round(avg(dateDiff('millisecond', source_commit_ts, ingested_at)), 2) AS avg_ms,
    quantileExact(0.50)(dateDiff('millisecond', source_commit_ts, ingested_at)) AS p50_ms,
    quantileExact(0.95)(dateDiff('millisecond', source_commit_ts, ingested_at)) AS p95_ms,
    quantileExact(0.99)(dateDiff('millisecond', source_commit_ts, ingested_at)) AS p99_ms,
    max(dateDiff('millisecond', source_commit_ts, ingested_at)) AS max_ms
FROM raw_efris_error_log
WHERE startsWith(ifNull(id, ''), '${RUN_PREFIX}-')"
```

UI values must match these queries.

- [ ] **Step 9: Run the final 10-minute browser demo**

Use `14 events/sec`, `600 seconds`, `12% retry`, target `8,400`.

Success criteria:

```text
Oracle committed       8,400
Source failures        0
ClickHouse received    8,400 after drain
Missing after drain    0
Browser refresh        safe
Duplicate Start        prevented
No steadily growing CDC backlog
```

- [ ] **Step 10: Commit documentation and add verified evidence to PR #2**

```bash
git add simulation/README.md docs/efris-error-monitor.md .env.example
git commit -m "docs: document browser-controlled EFRIS simulation"
```

Add a PR #2 comment only with results actually observed: automated tests, 60-second browser run, refresh reconnect, Pause/Resume, Stop/Drain, duplicate Start, and 10-minute reconciliation.

---

## Self-Review

- Spec coverage: refresh safety, detached worker, one active run, Pause/Resume/Stop, durable identity, exact source/destination reconciliation, live lineage, CDC latency, health, history, responsive UX, and 14/sec verification all map to Tasks 1–6.
- Placeholder scan: no `TBD`, `TODO`, incomplete fixture, or manual filename placeholder remains. Runtime-dependent run prefixes are read automatically from persisted state in Task 6.
- Type consistency: `RunConfig`, `RunRecord`, `RunStore`, `SimulatorManager`, repository, service, API, and frontend all use the same run states and stable `source_prefix` join key.
