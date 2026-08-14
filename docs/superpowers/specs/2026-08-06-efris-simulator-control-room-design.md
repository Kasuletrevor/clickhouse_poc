# EFRIS Simulator Control Room — Design Specification

Date: 2026-08-06
Branch: `feature/efris-error-monitor`

## 1. Purpose

Build a high-quality browser-based control room for the existing EFRIS error-log simulator. The page must let a user configure, start, pause, resume and stop a source simulation while continuously showing what has been generated in Oracle and what has arrived in ClickHouse through the real CDC path.

The simulator must preserve the architecture rule:

```text
Browser
  ↓ control only
FastAPI
  ↓
Server-side simulator worker
  ↓
Oracle T_INVOICE_ERROR_LOG
  ↓ redo
Debezium
  ↓
Kafka
  ↓
ClickHouse
```

The browser must never generate events itself and must never write to Kafka or ClickHouse.

## 2. User-experience principles

1. Browser refresh must be safe. Refreshing, navigating away, closing the tab, or reopening the app must not stop an active simulation.
2. The UI must reconnect to the active server-side run and reconstruct progress from backend state.
3. Only one simulator run may be active at a time on the POC host.
4. The UI must never fake pipeline progress. Exact source and destination counts are shown when measurable; intermediate stage health is shown separately from event counts.
5. Pause and Stop have different meanings:
   - **Pause**: stop creating new Oracle events but keep the run open; downstream CDC continues draining. Resume continues the same run and event sequence.
   - **Stop Run**: permanently end source generation for the run. The page remains in **Draining** until ClickHouse receives all committed source events, then marks the run **Completed**.
6. Progress is measured primarily by committed source-event count versus the configured target-event count, not by wall-clock time. Paused time does not consume the configured active generation duration.
7. Failure messages must be specific and recoverable. A source failure must never be presented as a successful commit.
8. The page must make the CDC story immediately understandable to a non-engineer while preserving enough lineage for technical reviewers.

## 3. Simulator page information architecture

The existing sidebar `Simulator` item becomes a real page under SYSTEM.

The page is distinct from `EFRIS Errors`:

- **Simulator** = configure, control and observe a test run.
- **EFRIS Errors** = business analytics over the error stream.

### 3.1 Idle state

The top of the page presents a compact configuration panel:

- Target rate, default `14.00 events/sec`.
- Duration, default `10 minutes`.
- Retry probability, default `12%`.
- Population summary: `200 taxpayers`, `500 devices`, `20 stations`, `15 error codes`.
- Expected event count calculated from rate × active duration.
- Primary action: **Start Simulation**.

The page also shows a concise architecture strip:

```text
Oracle → Debezium → Kafka → ClickHouse
```

with current health indicators where available.

### 3.2 Running state

The page becomes a live control room.

Header:

- Run ID.
- Status badge `RUNNING`.
- Target rate and actual rate.
- Active elapsed time.
- Remaining active time.
- Progress bar.
- Pause and Stop controls.

Primary pipeline strip:

```text
ORACLE                IN FLIGHT                CLICKHOUSE
3,463 committed   →       61       →          3,402 received
14.02 / sec                                    98.2% arrived
```

Health strip:

- Oracle connectivity.
- Debezium connector/task status.
- Kafka reachability.
- ClickHouse connectivity.

No event count is shown for Debezium or Kafka unless the implementation can measure it accurately. Intermediate stages are health indicators, not invented per-stage counts.

### 3.3 Paused state

Status badge becomes `PAUSED`.

- No new Oracle events are generated.
- Active-duration clock stops.
- The downstream pipeline continues updating.
- In-flight count should fall toward zero.
- Primary action becomes **Resume**.
- Stop remains available.

A clear helper message explains: `Source generation is paused. CDC is still draining committed events.`

### 3.4 Draining state

After Stop, generation is final for that run.

Status badge becomes `DRAINING` while:

```text
clickhouse_received < oracle_committed
```

The UI keeps updating source and destination reconciliation and CDC latency. Once counts reconcile, status becomes `COMPLETED`.

### 3.5 Completed state

The final screen preserves the run summary:

- Source events committed.
- ClickHouse events received.
- Missing/in-flight count.
- Achieved source rate.
- Active runtime.
- Affected invoices.
- Retry events and retry percentage.
- Taxpayers represented.
- Devices represented.
- Error codes represented.
- CDC average, P50, P95, P99 and max latency.

A **Start New Run** action returns the page to configuration state without deleting the completed-run metadata.

## 4. Live event stream

The page contains a compact scrolling feed for the current run.

Each row contains:

- Source event sequence.
- TIN.
- Device.
- Error code.
- Short error message.
- Seller reference.
- Oracle commit state.
- ClickHouse arrival state.

Before ClickHouse ingestion:

```text
#003463  SIMTIN000142  POS  1600  Oracle ✓  Waiting for CDC…
```

After ClickHouse ingestion:

```text
#003463  SIMTIN000142  POS  1600  Oracle ✓  ClickHouse ✓  6.18s
```

Expanded event detail may show truthful lineage that is already retained downstream:

- Oracle source commit timestamp.
- source SCN / commit SCN.
- Kafka partition.
- Kafka offset.
- ClickHouse ingestion timestamp.
- calculated CDC latency.

The UI must not animate or claim an event reached Debezium/Kafka before evidence exists.

## 5. Run analytics

The running page includes small live KPIs for the active run only:

- Error Events.
- Affected Invoices.
- Retry Events.
- Taxpayers.
- Devices.
- Error Codes.

Two compact visualizations are included:

1. Source/arrival throughput over time.
2. CDC latency trend or distribution with P50/P95 emphasis.

The page should feel operational rather than like a general BI report; large business-analysis charts remain on `EFRIS Errors`.

## 6. Run identity and event traceability

Every run receives a durable `run_id` and a compact `source_prefix` that fits inside the existing `T_INVOICE_ERROR_LOG.ID VARCHAR2(32)`.

Example:

```text
run_id:        EFR-20260806-084701-A1
source_prefix: S260806A1
```

Event IDs become deterministic within a run:

```text
S260806A1-000001
S260806A1-000002
S260806A1-000003
```

This allows exact filtering of one run in Oracle and ClickHouse without changing the source-table schema.

The sequence is monotonic within the run and is preserved across Pause/Resume.

## 7. Server-side worker architecture

The HTTP request that starts a run must return quickly; it must not execute the 10-minute loop itself.

Recommended implementation:

1. FastAPI validates the requested configuration.
2. It rejects Start if another run is active.
3. It creates the run registry entry.
4. It launches a dedicated simulator worker process on the RHEL host.
5. The worker owns the Oracle connection and event-generation loop.
6. The worker updates run state after each successful Oracle commit and at a throttled heartbeat interval.
7. The browser polls the backend for status and analytics.

A separate worker is preferred over a browser-bound request or JavaScript timer because it remains active through page refresh and tab closure.

## 8. Run-state persistence

For this single-host POC, use a small local run registry under an ignored runtime directory, for example:

```text
runtime/simulator/
  active.json
  runs/
    EFR-20260806-084701-A1.json
```

Runtime state must never contain passwords or connection strings.

Each run record contains at minimum:

```json
{
  "run_id": "EFR-20260806-084701-A1",
  "source_prefix": "S260806A1",
  "status": "running",
  "pid": 12345,
  "rate": 14.0,
  "duration_seconds": 600,
  "target_events": 8400,
  "retry_probability": 0.12,
  "started_at": "...",
  "active_elapsed_seconds": 247.1,
  "paused_seconds": 0,
  "generated": 3463,
  "failures": 0,
  "last_sequence": 3463,
  "last_heartbeat": "..."
}
```

On application startup or page refresh, the backend reconciles registry state with the recorded PID/heartbeat. A stale run must be shown as failed/stale instead of incorrectly claiming it is still running.

## 9. API design

### Start

```text
POST /api/simulator/runs
```

Request:

```json
{
  "rate": 14,
  "duration_seconds": 600,
  "retry_probability": 0.12
}
```

Response contains the created run and initial state.

If an active run exists, return `409` with the active-run metadata and a UI-friendly code such as `simulation_already_running`.

### Current status

```text
GET /api/simulator/status
```

Returns:

- active/current run metadata;
- exact committed source count;
- exact ClickHouse-received count for the run prefix;
- derived in-flight count;
- source-rate metrics;
- run-level business metrics;
- CDC latency metrics;
- stage health.

### Pause

```text
POST /api/simulator/runs/{run_id}/pause
```

Valid only from `running`.

### Resume

```text
POST /api/simulator/runs/{run_id}/resume
```

Valid only from `paused`.

### Stop

```text
POST /api/simulator/runs/{run_id}/stop
```

Stops future source generation. State changes to `draining` until ClickHouse reconciliation completes, then to `completed`.

### Recent events

May be included in the status payload or exposed separately:

```text
GET /api/simulator/runs/{run_id}/events?limit=50
```

The query uses the run's source-prefix filter.

### Run history

```text
GET /api/simulator/runs?limit=20
```

A compact history is useful for previous demo runs and regression comparisons, but it is secondary to the active-run experience.

## 10. Refresh/reconnect behavior

On every Simulator page load:

1. Render a skeleton immediately.
2. Call `GET /api/simulator/status`.
3. If no active run exists, render configuration.
4. If a run is active, render its current state and show a short non-blocking notice: `Reconnected to active simulation <run_id>`.
5. Begin one-second status refresh while the tab is visible.
6. When the document becomes hidden, reduce refresh frequency to lower unnecessary backend load.
7. When visible again, immediately refresh current state.

There is no `beforeunload` warning for normal page refresh because refresh is intentionally safe.

## 11. Control safety

- Start is disabled while a run is active.
- If a second browser tries to start another run, show the active-run card and a `View Active Simulation` action.
- Pause and Resume are idempotent at the API boundary where practical.
- Stop requires a lightweight confirmation because it is final for that run.
- Stopping a run never deletes already committed Oracle rows.
- A failed Oracle commit increments failure state only if the worker continues; fatal source errors mark the run `failed` and stop generation.

## 12. Status model

Supported run states:

```text
idle
starting
running
paused
draining
completed
failed
stale
```

Transitions:

```text
idle → starting → running
running → paused → running
running → draining → completed
paused → draining → completed
starting/running/paused/draining → failed
active state with lost worker/expired heartbeat → stale
```

## 13. Metrics definitions

For one run:

- `oracle_committed`: successful simulator commits for the run, cross-checkable by Oracle `ID` prefix.
- `clickhouse_received`: rows in `analytics.raw_efris_error_log` matching the run prefix.
- `in_flight`: `max(oracle_committed - clickhouse_received, 0)`.
- `delivery_percent`: `clickhouse_received / oracle_committed * 100` when source count > 0.
- `actual_source_rate`: successful commits / active-generation elapsed time.
- `affected_invoices`: distinct `(tin, seller_reference_no)`.
- `retry_events`: `error_events - affected_invoices`.
- `cdc_latency_ms`: `ingested_at - source_commit_ts` for rows received in ClickHouse.

Latency panel shows average, P50, P95, P99 and max.

## 14. Stage health

Health is independently reported and visually separated from event reconciliation.

- Oracle: lightweight source connectivity check.
- Debezium: connector and task state from Kafka Connect REST.
- Kafka: broker/topic reachability using a supported client or a lightweight connectivity check; do not depend on privileged Docker CLI from the web application.
- ClickHouse: analytical query/connectivity check.

States are `healthy`, `degraded`, `unavailable` or `unknown`.

## 15. Visual design

Use the existing navy/gold internal application design language, but the Simulator page should feel like an operations console.

Visual hierarchy:

1. Run state and primary controls.
2. Source → CDC → destination reconciliation.
3. Progress and actual rate.
4. Pipeline health.
5. Live events.
6. Run analytics and latency.

Color must not be the only status indicator; always pair color with icon/text.

The running screen should avoid excessive animation. Numbers can update smoothly, but the interface should remain readable at 14 events/sec. The event feed should update in small batches rather than visually inserting fourteen rows every second.

## 16. Performance behavior

The UI should not request one HTTP call per event.

Recommended behavior:

- worker commits at target source rate;
- worker persists lightweight counters/heartbeat periodically;
- browser status polling approximately once per second while visible;
- recent-event panel displays only the latest 25–50 rows;
- ClickHouse aggregate queries are scoped to the source prefix and can be cached for a short interval if needed.

## 17. Existing simulator refactor

The current `scripts/run_efris_simulator.py` contains useful generation logic and has already demonstrated 14.02 events/sec with zero source failures in the POC.

Implementation should extract reusable simulator-engine logic instead of duplicating it. The CLI remains useful and should call the same engine where possible.

The browser-controlled worker and CLI must preserve:

- weighted taxpayer selection;
- device ownership;
- 15-code weighted catalogue;
- retry behavior;
- Oracle-only writes;
- monotonic pacing;
- source failure handling.

## 18. Test requirements

Backend unit tests:

- valid run-state transitions;
- duplicate Start rejection;
- pause/resume timing excludes paused duration;
- deterministic source ID formatting and sequence continuation;
- stop moves to draining rather than deleting data;
- stale-worker detection;
- metric calculations.

API tests:

- Start/status/pause/resume/stop contracts;
- `409 simulation_already_running`;
- invalid-state operations;
- friendly source-unavailable errors.

Frontend behavior tests or targeted manual verification:

- refresh during running reconnects without stopping generation;
- navigation away/back reconnects;
- second browser sees active run instead of starting another;
- Pause drains in-flight events;
- Resume continues same run ID and sequence;
- Stop enters draining then completed;
- live counts reconcile to ClickHouse;
- event feed never presents unsupported intermediate-stage claims.

End-to-end host verification:

1. Start 14 events/sec for 60 seconds from the browser.
2. Refresh the page mid-run.
3. Navigate away and back.
4. Pause and confirm source count stops while ClickHouse catches up.
5. Resume and confirm sequence continues.
6. Stop and confirm Draining → Completed.
7. Reconcile Oracle committed count to ClickHouse received count.
8. Run the 10-minute 14 events/sec workload from the UI.

## 19. Out of scope for this iteration

- Multiple simultaneous simulator runs.
- Distributed worker orchestration.
- Authentication/authorization changes.
- Direct Kafka publishing from the simulator.
- Direct ClickHouse writes from the simulator.
- Production-grade job queues such as Celery unless later needed.
- Automatic modification of Debezium/Kafka configuration.
- Claiming real EFRIS taxpayer identities; the seeded `SIM*` population remains synthetic.

## 20. Success criteria

The feature is successful when a user can open the Simulator page, start a 14 events/sec workload, refresh or close/reopen the browser without interrupting it, pause/resume the same run, stop it cleanly, and watch committed Oracle events reconcile into ClickHouse with truthful run-level lineage and latency metrics.

The resulting demo should make the following story visually obvious:

```text
The source generated 14 committed EFRIS error transactions every second.
Oracle remained the only write target.
Debezium captured the changes from redo.
Kafka carried the stream.
ClickHouse received and analyzed the same run.
The control room continuously showed throughput, progress, retries, in-flight events and CDC latency.
```
