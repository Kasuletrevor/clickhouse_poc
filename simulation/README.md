# EFRIS Error-Log Traffic Simulator

The simulator creates source transactions in Oracle only. The downstream path remains:

```text
Browser / CLI -> simulator worker -> Oracle T_INVOICE_ERROR_LOG
                                      -> redo -> Debezium -> Kafka -> ClickHouse
```

Neither the browser, FastAPI control layer nor CLI writes directly to Kafka or ClickHouse.

## Demo population

The deterministic POC population contains:

- 20 simulation stations (`SIM01` to `SIM20`) across Central, Eastern, Western and Northern regions;
- 200 synthetic company taxpayers (`SIMTIN000001` onward);
- 500 ERP/POS/API/EFD devices;
- per-taxpayer and per-device traffic weights;
- 15 weighted EFRIS error codes.

Generate and seed it once from the repository root:

```bash
python scripts/seed_efris_population.py
```

The seed is idempotent for the `SIM*` identities. To regenerate the local JSON only:

```bash
python scripts/seed_efris_population.py --export-only
```

The generated files are local runtime artifacts and are not committed:

```text
simulation/generated_taxpayers.json
simulation/generated_devices.json
```

## Default workload

`simulation/config.json` defines the workload defaults:

```text
14 error-log INSERT + COMMIT transactions per second
600 seconds active generation time
8,400 exact finite-run source events
12% retry probability
```

Retries reuse the same `(TIN, SELLER_REFERENCE_NO)` while producing a new source event. This lets ClickHouse distinguish error-event count from affected invoice/reference count.

## Browser-controlled mode

The **Simulator** page in the internal application is now the preferred demonstration mode.

Lifecycle:

```text
Browser Start -> detached server-side worker -> Oracle source writes
Browser refresh/navigation/tab closure       -> no effect on the worker
Pause                                         -> no new Oracle commits; CDC keeps draining
Resume                                        -> same run ID, source prefix and next sequence
Stop                                          -> source generation ends permanently
Stop / natural target                         -> DRAINING until ClickHouse reconciles
Reconciled source + destination               -> COMPLETED
```

Only one simulator run may be active on the POC host. If a second browser attempts Start, the API returns the active run instead of launching another worker.

Every run receives a traceable identity such as:

```text
run_id        EFR-20260806-084701-A1
source_prefix S260806A1
source IDs    S260806A1-000001, S260806A1-000002, ...
```

This lets Oracle and ClickHouse reconcile exactly one run without changing the source-table schema.

The server-side run registry is stored under:

```text
runtime/simulator/
```

It contains run metadata, counters, state and worker logs only. It must never contain database passwords or connection strings and is ignored by Git.

Non-secret runtime settings:

```text
DEBEZIUM_URL=http://localhost:8083
DEBEZIUM_FLAT_CONNECTOR=oracle-cdc-flat
KAFKA_BOOTSTRAP=localhost:9092
SIMULATOR_RUNTIME_DIR=runtime/simulator
SIMULATOR_STALE_SECONDS=10
```

The application process still needs the existing Oracle and ClickHouse environment configuration. Keep real credentials only in `.env`.

### Simulator API

```text
POST /api/simulator/runs
GET  /api/simulator/status
POST /api/simulator/runs/{run_id}/pause
POST /api/simulator/runs/{run_id}/resume
POST /api/simulator/runs/{run_id}/stop
GET  /api/simulator/runs/{run_id}/events?limit=40
GET  /api/simulator/runs?limit=20
```

The status API combines worker state, exact Oracle source rows, ClickHouse-arrived rows, CDC latency and independent health checks for Oracle, Debezium, Kafka and ClickHouse. Debezium/Kafka health is not presented as per-event proof.

## CLI mode

The engineering CLI remains available and uses the same workload engine as the browser worker.

One minute:

```bash
python scripts/run_efris_simulator.py --rate 14 --duration 60
```

A successful finite run now stops by exact event target, so the expected source count is exactly:

```text
840 events
```

Ten minutes:

```bash
python scripts/run_efris_simulator.py --rate 14 --duration 600
```

Expected source count:

```text
8,400 events
```

Continuous:

```bash
python scripts/run_efris_simulator.py --rate 14 --duration 0
```

Stop continuous CLI mode with `Ctrl+C`.

Each generated event is an individual Oracle `INSERT + COMMIT` transaction. The shared rate pacer uses monotonic deadlines so Oracle insert/commit time counts against the requested interval instead of silently reducing throughput. After Pause, the browser worker resets its pacing deadline so it does not produce a catch-up burst.

## Proven pre-control-room baseline

The earlier CLI implementation used an elapsed-time boundary and therefore produced one extra boundary event in the observed one-minute test. That historical run remains valid evidence and is recorded separately from the new exact-count behavior:

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

Future finite runs use exact target counts: `14 x 60 = 840` and `14 x 600 = 8,400` when there are no source failures.

## Kafka topic

The EFRIS flat topic is:

```text
oracleflat.CDC_APP.T_INVOICE_ERROR_LOG
```

The current POC topic has one partition and replication factor one. At 14 events/second, one partition is sufficient and keeps simple total ordering for this stream.

## Important

The seed population is synthetic. Station labels are realistic geographic labels for demonstration, but `SIM*` station IDs, `SIMTIN*` taxpayers and generated device identities are POC data and must not be presented as real taxpayer records.
