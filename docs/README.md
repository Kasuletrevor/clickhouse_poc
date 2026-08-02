# Project Documentation

This directory contains the design, architecture, operating procedures, demo flow, implementation plan, and troubleshooting notes for the Oracle → Debezium → Kafka → ClickHouse CDC proof of concept.

## Documents

- [`cdc_internal_transaction_app_design_spec.md`](./cdc_internal_transaction_app_design_spec.md) — approved product and technical design for the internal transactional web application. This is the primary Codex handoff document.
- [`architecture.md`](./architecture.md) — system boundaries, data ownership, CDC flow, ClickHouse layers, ordering, and historical semantics.
- [`implementation-plan.md`](./implementation-plan.md) — recommended vertical build sequence and acceptance criteria.
- [`runbook.md`](./runbook.md) — day-to-day commands for bringing up, checking, and operating Oracle, Debezium, Kafka, ClickHouse, Kafbat, the simulator, and the future FastAPI app.
- [`demo-runbook.md`](./demo-runbook.md) — concise manager/demo sequence showing one source transaction flowing end-to-end.
- [`troubleshooting.md`](./troubleshooting.md) — known failure modes and fixes discovered while building the POC.

## Core rule

The source application writes only to Oracle.

```text
Browser / Simulator
       ↓
     Oracle
       ↓
 redo / LogMiner
       ↓
    Debezium
       ↓
      Kafka
       ↓
   ClickHouse
       ↓
 Power BI / analytical APIs
```

Do not introduce application-side writes to Kafka or ClickHouse.

## Business vs engineering screens

The planned internal application deliberately separates normal operational work from CDC observability.

Business-facing:

```text
Dashboard
Taxpayers
Stations
Payments
Reports
```

Engineering-facing:

```text
Pipeline Health
Event Monitor
Simulator
```

Operational screens read/write Oracle. Analytical and engineering screens read ClickHouse and infrastructure health endpoints.

## Historical semantics that must remain true

The POC has already proven the difference between `station_at_payment` and `current_station`.

A taxpayer may move stations after a payment. Historical payments must retain the station that was valid when the payment happened while also allowing analytics to show the taxpayer's current station.

This behavior depends on the SCD2/current-state modeling in ClickHouse and must not be replaced by a naive join to the latest taxpayer row.
