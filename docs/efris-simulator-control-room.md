# EFRIS Simulator Control Room

## Purpose

The Simulator Control Room turns the existing EFRIS command-line workload into a refresh-safe browser-controlled test console while preserving the source/CDC architecture:

```text
Browser -> FastAPI control API -> detached simulator worker -> Oracle T_INVOICE_ERROR_LOG
                                                       Oracle redo -> Debezium -> Kafka -> ClickHouse
```

The worker writes only to Oracle. The browser and FastAPI control layer never publish source events directly to Kafka or ClickHouse.

## User experience

The **Simulator** item under **SYSTEM** now provides:

- configurable target events/sec, active duration and retry probability;
- expected source-event count before Start;
- a detached server-side run that survives browser refresh, navigation and tab closure;
- one-active-run protection across browsers;
- Pause, Resume and final Stop controls;
- `RUNNING`, `PAUSED`, `DRAINING`, `COMPLETED`, `FAILED` and `STALE` states;
- exact Oracle committed count versus ClickHouse received count;
- in-flight/backlog and delivery percentage;
- active-generation progress, target/actual source rate and remaining active time;
- independent health for Oracle, Debezium, Kafka and ClickHouse;
- run-level affected invoices, retry events, taxpayers, devices and error-code coverage;
- CDC latency average/P50/P95/P99/max from real downstream timestamps;
- a live event journey that shows Oracle commit immediately and ClickHouse/Kafka lineage only after real downstream evidence exists;
- previous-run history.

Normal browser refresh has no warning because it is intentionally safe. When an active run exists, the page reconnects to it instead of starting a second workload.

## Run identity

Each run is assigned a compact traceable source prefix that fits the existing `T_INVOICE_ERROR_LOG.ID VARCHAR2(32)` column.

Example:

```text
run_id        EFR-20260806-084701-A1
source_prefix S260806A1
source IDs    S260806A1-000001
              S260806A1-000002
              ...
```

The prefix is the exact reconciliation key in Oracle and ClickHouse.

## Lifecycle

```text
STARTING -> RUNNING <-> PAUSED
                 |
                 +-> DRAINING -> COMPLETED

STARTING / RUNNING / PAUSED -> FAILED or STALE when the worker fails
```

Pause freezes source generation and active-generation time. CDC continues draining. Resume keeps the same run ID, retry pool and event sequence and resets the pacing deadline so there is no catch-up burst.

Stop is final for the run. It stops future source commits but leaves already committed Oracle rows untouched. The run stays `DRAINING` until ClickHouse receives all committed rows, then becomes `COMPLETED`.

## Exact finite-run behavior

The old CLI stopped on an elapsed-time boundary and the proven 60-second test produced 841 events. The shared engine now stops finite workloads by exact event target and schedules the first event one interval after run start.

Therefore, when there are no source failures:

```text
14 events/sec x 60 sec  =   840 source commits
14 events/sec x 600 sec = 8,400 source commits
```

The CLI and browser worker share the same weighted taxpayer/device/error-code factory and pacing logic.

## Runtime state

The detached worker and FastAPI processes coordinate through an atomic JSON registry under:

```text
runtime/simulator/
```

The registry uses a Linux `fcntl` file lock and atomic file replacement so concurrent browser processes cannot create two active runs. State contains run metadata and counters only; no passwords or connection strings are persisted.

The runtime directory is ignored by Git.

## API

```text
POST /api/simulator/runs
GET  /api/simulator/status
GET  /api/simulator/runs?limit=20
GET  /api/simulator/runs/{run_id}/events?limit=40
POST /api/simulator/runs/{run_id}/pause
POST /api/simulator/runs/{run_id}/resume
POST /api/simulator/runs/{run_id}/stop
```

A duplicate Start returns HTTP `409` with error code `simulation_already_running` and the active-run metadata so the UI can reconnect cleanly.

## Metric definitions

For one source prefix:

```text
oracle_committed   = exact Oracle rows matching the run prefix
clickhouse_received = exact raw_efris_error_log rows matching the run prefix
in_flight           = max(oracle_committed - clickhouse_received, 0)
delivery_percent    = clickhouse_received / oracle_committed * 100
actual_source_rate  = successful worker commits / active-generation elapsed time
affected_invoices   = distinct (TIN, SELLER_REFERENCE_NO)
retry_events        = error_events - affected_invoices
cdc_latency_ms      = ClickHouse ingested_at - Debezium source_commit_ts
```

If Oracle is temporarily unavailable, the UI labels the persisted worker count as a fallback rather than presenting it as an exact Oracle query. If ClickHouse is unavailable, destination state is explicitly shown as unavailable rather than fabricating delivery.

## Pipeline health

Health is deliberately separate from per-event delivery evidence:

- Oracle: lightweight `SELECT 1 FROM DUAL`;
- Debezium: Kafka Connect REST connector/task status;
- Kafka: broker TCP reachability for the configured bootstrap endpoint;
- ClickHouse: lightweight analytical query.

Kafka reachability means the broker endpoint is reachable. It is not presented as proof that a particular event has reached Kafka. Kafka partition/offset is shown for an event only after that lineage is present in the ClickHouse raw row.

## Proven baseline before Control Room runtime verification

The existing one-minute CLI test demonstrated:

```text
Generated                  841
Source failures              0
Actual source rate        14.02/s
ClickHouse received         841
Affected invoices           751
Retry events                 90
Taxpayers represented       188
Devices represented         335
P50 CDC latency            6362 ms
P95 CDC latency            9914 ms
P99 CDC latency           10938 ms
```

That run used the old elapsed-time boundary. The next host verification should use the browser Control Room and expect exactly 840 source commits for a 60-second 14/sec finite run.

## Host verification sequence

After pulling the implementation on the RHEL POC host:

1. Run the automated test/syntax suite.
2. Start a browser run at 14/sec for 60 seconds.
3. Refresh mid-run and verify the same run reconnects and continues.
4. Navigate away/back and verify the worker continues.
5. Verify exact final count of 840 source commits and ClickHouse reconciliation.
6. In a separate short run, Pause and confirm source count freezes while downstream drains; Resume and confirm the same run sequence continues.
7. Stop a run early and verify `DRAINING -> COMPLETED`.
8. Attempt Start from a second browser while active and verify no second worker is launched.
9. Only then run the 10-minute 14/sec workload with an exact target of 8,400.
