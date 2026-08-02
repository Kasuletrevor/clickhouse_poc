# Oracle → Kafka → ClickHouse CDC POC

A hands-on Change Data Capture (CDC) proof of concept showing how transactional changes in **Oracle** can be captured from the database redo logs, streamed through **Debezium** and **Kafka**, materialized in **ClickHouse**, and exposed to analytical consumers such as **Power BI**.

The project is intentionally designed so that the source application only knows about Oracle. It does **not** write directly to Kafka or ClickHouse.

```text
Transactional app / simulator
            │
            ▼
         Oracle
            │
      redo / LogMiner
            │
            ▼
        Debezium
            │
            ▼
          Kafka
            │
            ▼
       ClickHouse
            │
            ▼
        Power BI
```

## What this POC demonstrates

- Log-based CDC from Oracle rather than polling source tables.
- Debezium Oracle Connector using LogMiner.
- Kafka as the durable event-streaming layer.
- Flat analytics-friendly CDC events alongside native Debezium events.
- ClickHouse raw CDC history and current-state serving models.
- Source-derived event ordering using Oracle SCN/commit metadata.
- SCD2-style taxpayer history.
- Correct distinction between **station at payment time** and **current taxpayer station**.
- A Python workload simulator that writes only to Oracle.
- Power BI consuming the ClickHouse serving layer.
- A planned internal transactional web application built with FastAPI + HTML/CSS/JavaScript.

## Architecture principle

The most important rule in this project is:

> Business applications write to Oracle. CDC is responsible for propagating committed changes downstream.

```text
WRITE PATH
Browser / Simulator → Oracle

CDC PATH
Oracle → Debezium → Kafka → ClickHouse

ANALYTICS PATH
ClickHouse → Power BI / analytical APIs
```

This separation allows the source application to continue operating independently of the analytical stack.

## Source domain

The POC currently models three transactional entities:

### Stations

A station has an identifier, name, region, district, operational status, and update timestamp.

### Taxpayers

A taxpayer has a TIN, name, taxpayer type, current station assignment, operational status, and update timestamp.

### Payments

A payment belongs to a taxpayer and includes an amount, status, payment time, and update time.

Typical payment states are:

```text
PENDING → SUCCESSFUL
PENDING → REVERSED
SUCCESSFUL → REVERSED
REVERSED → terminal
```

## Historical semantics

A core requirement is preserving both:

1. the taxpayer's station **when a payment happened**, and
2. the taxpayer's **current station**.

For example:

```text
Taxpayer starts at Kampala Central
        │
        ├── PAY102 occurs
        │
        ├── Taxpayer moves to Jinja
        │
        └── PAY103 occurs
```

The analytical model must correctly return:

```text
PAY102  station_at_payment = Kampala Central
        current_station    = Jinja

PAY103  station_at_payment = Jinja
        current_station    = Jinja
```

This is implemented with current-state views plus taxpayer history rather than a naive join to the latest taxpayer record.

## CDC topics

Two Debezium topic families are used intentionally.

### Native Debezium topics

```text
oraclecdc.CDC_APP.PAYMENT
oraclecdc.CDC_APP.TAXPAYER
oraclecdc.CDC_APP.STATION
```

These preserve the normal Debezium envelope and are useful for forensic inspection and debugging.

### Flattened analytics topics

```text
oracleflat.CDC_APP.PAYMENT
oracleflat.CDC_APP.TAXPAYER
oracleflat.CDC_APP.STATION
```

These use Debezium's `ExtractNewRecordState` SMT and retain useful CDC lineage such as operation type, SCN, commit SCN, transaction ID, source timestamp, and deletion state while producing simpler JSON for ClickHouse ingestion.

## ClickHouse model

The analytical database is organized into layers.

### Raw CDC history

```text
raw_oracle_payment_cdc
raw_oracle_taxpayer_cdc
raw_oracle_station_cdc
```

Raw tables retain multiple versions of the same business entity.

### Current state / history

```text
fact_oracle_payment_current
dim_oracle_taxpayer_current
dim_oracle_station_current
dim_oracle_taxpayer_history
```

### Serving layer

```text
vw_oracle_payment_analytics
```

The serving view provides business-friendly payment data including taxpayer details, station-at-payment attributes, current station attributes, and CDC lineage.

## Time and ordering

The project deliberately keeps different timestamps separate:

```text
PAYMENT_TIME       business event time
UPDATED_AT         source application update time
source_commit_time Oracle commit/CDC time
kafka_timestamp    Kafka timestamp
ingested_at        ClickHouse ingestion time
```

`ingested_at` is useful for observability but is **not** used as the authoritative business version order. Current-state logic uses source-derived ordering information such as Oracle SCN/commit SCN and related lineage.

## Simulator

The Python simulator generates realistic source-side activity by writing directly to Oracle.

Examples of generated events include:

- new payments
- payment status transitions
- taxpayer station movements

Typical workload:

```text
80% new payments
15% payment status updates
5% taxpayer station movements
```

Example:

```bash
python simulator/run_load.py --transactions-per-minute 10
```

The simulator must never publish directly to Kafka or insert directly into ClickHouse.

## Internal transaction application

The next application layer is a trusted internal web app built with:

```text
FastAPI
HTML
CSS
Vanilla JavaScript
```

No React/Node build chain is required for the POC.

Business-facing screens:

```text
Dashboard
Taxpayers
Stations
Payments
Reports
```

Engineering screens:

```text
Pipeline Health
Event Monitor
Simulator
```

Operational screens read/write Oracle. Analytical and engineering screens read ClickHouse and infrastructure health APIs.

### UI direction

The approved direction is a professional internal-system interface with:

- dark navy navigation
- warm yellow/gold primary actions
- white/light-gray content surfaces
- compact enterprise tables
- status badges and drawers
- no organizational logo
- CDC terminology kept out of normal business screens

![Payments dashboard concept](./Payments%20Dashboard%20Overview%20%281%29.png)

## Repository safety

Runtime database files and secrets must not be committed.

Examples that should remain ignored:

```text
.env
Oracle data files
Kafka broker data
ClickHouse data/logs
connector JSON containing credentials
Python virtual environments
runtime logs
```

Use environment variables for credentials and provide only placeholder/example configuration in Git.

## Development workflow

Recommended branch workflow:

```text
main
  └── feature/internal-transaction-app
```

For application work, implement vertically rather than building every screen at once.

Suggested order:

1. Application shell.
2. Payments vertical slice.
3. Taxpayers.
4. Stations.
5. Dashboard.
6. Event Monitor.
7. Pipeline Health.
8. Simulator controls.
9. Reports and polish.
10. systemd deployment.

## First application milestone

The first complete milestone should provide:

- FastAPI application startup
- persistent sidebar/header
- SPA-style navigation
- Payments page backed by Oracle
- Create Payment drawer
- Payment Detail drawer
- payment state transitions
- friendly validation/errors
- toasts
- approved navy/yellow styling

Creating a payment from the UI must follow the real path:

```text
UI → FastAPI → Oracle COMMIT → Debezium → Kafka → ClickHouse → analytics
```

## Acceptance principle

The finished POC should communicate two things at the same time.

To a business user:

> This behaves like a normal internal transactional application.

To an engineer:

> Every committed Oracle change is captured from redo and propagated through Debezium, Kafka, and ClickHouse without the source application knowing anything about the analytics pipeline.

That separation is the core of the project.
