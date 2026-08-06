# EFRIS Error-Log Traffic Simulator

This simulator creates source transactions in Oracle only. The downstream path remains:

```text
Simulator -> Oracle T_INVOICE_ERROR_LOG -> redo -> Debezium -> Kafka -> ClickHouse
```

It does not write directly to Kafka or ClickHouse.

## Demo population

The seed generator creates a deterministic synthetic population for the POC:

- 20 simulation stations (`SIM01` to `SIM20`) across Central, Eastern, Western and Northern regions.
- 200 synthetic company taxpayers (`SIMTIN000001` onward).
- 500 devices distributed across those taxpayers.
- ERP, POS, API and EFD device types.
- Per-taxpayer and per-device traffic weights so the workload is not uniform.

The source definitions are:

```text
simulation/stations.json
simulation/taxpayer_population.json
```

Running the seed script also exports the fully expanded population to:

```text
simulation/generated_taxpayers.json
simulation/generated_devices.json
```

These generated files are local runtime artifacts and are not committed.

## Error traffic

The simulator uses 15 EFRIS error codes from the earlier POC error-code dataset in:

```text
simulation/error_codes.json
```

The default workload is configured in:

```text
simulation/config.json
```

Current default:

```text
14 error-log INSERT + COMMIT transactions per second
600 seconds
8,400 expected source error events
12% retry probability
```

Retries reuse the same `(TIN, SELLER_REFERENCE_NO)` so ClickHouse can distinguish raw error-event count from affected invoice/reference count.

## 1. Generate and seed the population

From the repository root with the application virtual environment active and the Oracle environment variables configured:

```bash
python scripts/seed_efris_population.py
```

This is idempotent for the `SIM*` station, taxpayer and device identities. It uses Oracle `MERGE` statements and commits the complete seed population once.

To inspect the generated JSON without changing Oracle:

```bash
python scripts/seed_efris_population.py --export-only
```

## 2. Run a one-minute source test

```bash
python scripts/run_efris_simulator.py --rate 14 --duration 60
```

Expected source count is approximately:

```text
840 events
```

Every generated event is an individual Oracle transaction and is committed before the next event is counted as generated.

## 3. Run the ten-minute demo workload

```bash
python scripts/run_efris_simulator.py --rate 14 --duration 600
```

Expected source count:

```text
8,400 events
```

## 4. Run continuously

```bash
python scripts/run_efris_simulator.py --rate 14 --duration 0
```

Stop with `Ctrl+C`.

## Rate behavior

The simulator uses a monotonic deadline scheduler instead of sleeping a fixed amount after each transaction. At 14 events per second the target interval is about 71.4 ms. Oracle INSERT and COMMIT time therefore count against the interval instead of silently reducing throughput.

The console reports:

```text
generated=<count> failures=<count> actual=<rate>/s schedule_lag=<ms>
```

If the Oracle source cannot sustain the requested transaction rate, `schedule_lag` will grow and the achieved rate will fall below the target. That is useful evidence during the POC rather than being hidden by the generator.

## Kafka topic

The current EFRIS flat topic is:

```text
oracleflat.CDC_APP.T_INVOICE_ERROR_LOG
```

At the time this simulator was added it had one partition and replication factor one. One partition is sufficient for the 14 events/second demo and preserves simple total ordering for this stream.

## Important

The seed population is synthetic. Station labels are realistic geographic labels for demonstration, but the `SIM*` station IDs, `SIMTIN*` taxpayers and generated device identities are POC data and must not be presented as real taxpayer records.
