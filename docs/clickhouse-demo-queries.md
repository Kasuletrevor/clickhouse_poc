# ClickHouse Demo Queries

This document is a copy/paste query guide for demonstrating the Oracle → Debezium → Kafka → ClickHouse pipeline from the ClickHouse web UI.

## Important note for the browser UI

In the current environment, do **not** rely on:

```sql
USE analytics;
SHOW TABLES;
```

That combination did not return useful results in the browser UI during testing.

For demos, use fully qualified object names everywhere:

```text
analytics.<table_or_view>
```

For example:

```sql
SELECT *
FROM analytics.fact_oracle_payment_current
LIMIT 10;
```

This makes each query self-contained and avoids depending on the browser session's selected database.

---

## 1. Show the analytical objects in the `analytics` database

Instead of `SHOW TABLES`, use:

```sql
SELECT
    name,
    engine
FROM system.tables
WHERE database = 'analytics'
ORDER BY name;
```

Useful objects to point out include:

```text
raw_oracle_payment_cdc
raw_oracle_taxpayer_cdc
raw_oracle_station_cdc
fact_oracle_payment_current
dim_oracle_taxpayer_current
dim_oracle_station_current
dim_oracle_taxpayer_history
vw_oracle_payment_analytics
```

> The `raw_*` tables retain CDC history, the `*_current` tables reconstruct current state, the history table preserves changing taxpayer context, and the serving view exposes business-ready analytics.

---

## 1A. Inspect a view definition

The quickest way to read the full SQL definition of a ClickHouse view is:

```sql
SHOW CREATE TABLE analytics.vw_oracle_payment_analytics;
```

ClickHouse uses `SHOW CREATE TABLE` for tables and views, so the same command works even though `vw_oracle_payment_analytics` is a view.

This is useful during a demo because it shows exactly how the serving layer is built from the underlying fact and dimension objects.

You can also read the definition from ClickHouse metadata:

```sql
SELECT
    database,
    name,
    engine,
    create_table_query
FROM system.tables
WHERE database = 'analytics'
  AND name = 'vw_oracle_payment_analytics';
```

To list the definitions of all views in the `analytics` database:

```sql
SELECT
    name,
    engine,
    create_table_query
FROM system.tables
WHERE database = 'analytics'
  AND engine IN ('View', 'MaterializedView')
ORDER BY name;
```

For any specific current-state or materialized object, replace the name, for example:

```sql
SHOW CREATE TABLE analytics.fact_oracle_payment_current;
```

or:

```sql
SHOW CREATE TABLE analytics.dim_oracle_taxpayer_current;
```

> `SHOW CREATE TABLE` lets us inspect the exact transformation logic ClickHouse is using. This is especially useful for proving how raw CDC events are turned into current-state tables, history tables and the final business-serving view.

---

## 2. Show current payments

```sql
SELECT
    payment_id,
    taxpayer_id,
    amount,
    status,
    payment_time,
    latest_event_version
FROM analytics.fact_oracle_payment_current
ORDER BY payment_time DESC
LIMIT 20;
```

> These are not raw Kafka events. ClickHouse has reconstructed the latest state of each payment.

---

## 3. Show the business-ready serving view

```sql
SELECT
    payment_id,
    taxpayer_id,
    taxpayer_name,
    amount,
    payment_status,
    payment_time,
    station_at_payment,
    current_station
FROM analytics.vw_oracle_payment_analytics
ORDER BY payment_time DESC
LIMIT 20;
```

This is one of the strongest demo queries because it exposes both:

```text
station_at_payment
current_station
```

> A payment keeps the station that was valid when it occurred, while the same result can also show the taxpayer's current station.

---

## 4. Show raw payment CDC events

```sql
SELECT
    payment_id,
    taxpayer_id,
    amount,
    status,
    dbz_op,
    source_scn,
    source_commit_scn,
    source_tx_id,
    kafka_partition,
    kafka_offset,
    kafka_timestamp,
    ingested_at
FROM analytics.raw_oracle_payment_cdc
ORDER BY ingested_at DESC
LIMIT 20;
```

Typical Debezium operation values include:

```text
c = create
u = update
```

> This is below the business layer. These are the change events that travelled Oracle → Debezium → Kafka → ClickHouse.

---

## 5. Show all versions of one payment

Replace `PAY101` with a payment that has been updated.

```sql
SELECT
    payment_id,
    status,
    dbz_op,
    source_commit_scn,
    source_scn,
    kafka_offset,
    ingested_at
FROM analytics.raw_oracle_payment_cdc
WHERE payment_id = 'PAY101'
ORDER BY
    source_commit_scn,
    source_scn,
    kafka_offset;
```

A useful result is conceptually:

```text
PAY101   PENDING      c
PAY101   SUCCESSFUL   u
```

Then compare it with current state:

```sql
SELECT *
FROM analytics.fact_oracle_payment_current
WHERE payment_id = 'PAY101';
```

> Raw history keeps every version; the current-state table resolves the latest valid state.

---

## 6. Show taxpayer CDC events

```sql
SELECT
    taxpayer_id,
    taxpayer_name,
    station_id,
    dbz_op,
    source_commit_scn,
    source_scn,
    kafka_offset,
    source_commit_time,
    ingested_at
FROM analytics.raw_oracle_taxpayer_cdc
ORDER BY
    source_commit_scn DESC,
    source_scn DESC,
    kafka_offset DESC
LIMIT 20;
```

For a single taxpayer:

```sql
SELECT
    taxpayer_id,
    taxpayer_name,
    station_id,
    dbz_op,
    source_commit_scn,
    source_commit_time
FROM analytics.raw_oracle_taxpayer_cdc
WHERE taxpayer_id = 'TIN001'
ORDER BY
    source_commit_scn,
    source_scn,
    kafka_offset;
```

This is useful for showing a station movement such as:

```text
ST001 → ST002
```

---

## 7. Show the historical station-at-payment proof

```sql
SELECT
    payment_id,
    payment_time,
    taxpayer_id,
    taxpayer_name,
    station_at_payment,
    current_station
FROM analytics.vw_oracle_payment_analytics
WHERE taxpayer_id = 'TIN001'
ORDER BY payment_time;
```

The important result is conceptually:

```text
PAY102   ...   Kampala Central   Jinja
PAY103   ...   Jinja             Jinja
```

> PAY102 happened while the taxpayer belonged to Kampala Central, so its historical station remains Kampala Central even though the taxpayer later moved to Jinja. PAY103 happened after the move, so both values are Jinja.

This demonstrates why the model is more than a simple latest-row join.

---

## 8. Payment status summary

```sql
SELECT
    payment_status,
    count() AS payments,
    sum(amount) AS total_amount
FROM analytics.vw_oracle_payment_analytics
GROUP BY payment_status
ORDER BY payments DESC;
```

This corresponds closely to the Payment Status visualization on the internal Dashboard.

---

## 9. Payments by station

```sql
SELECT
    station_at_payment,
    count() AS payments,
    sumIf(amount, payment_status = 'SUCCESSFUL') AS successful_amount
FROM analytics.vw_oracle_payment_analytics
GROUP BY station_at_payment
ORDER BY successful_amount DESC;
```

This corresponds closely to the Dashboard's Payments by Station graph.

---

## 10. Today's business KPIs

The POC uses `Africa/Kampala` as the business-day timezone.

```sql
SELECT
    count() AS payments_today,
    sumIf(amount, payment_status = 'SUCCESSFUL') AS amount_collected_today
FROM analytics.vw_oracle_payment_analytics
WHERE toDate(payment_time, 'Africa/Kampala')
      = toDate(now('Africa/Kampala'));
```

> Payments Today counts today's transactions, while Amount Collected Today includes only payments whose current status is SUCCESSFUL.

---

## 11. Show Kafka lineage inside ClickHouse

```sql
SELECT
    kafka_topic,
    kafka_partition,
    count() AS events,
    min(kafka_offset) AS first_offset,
    max(kafka_offset) AS latest_offset
FROM analytics.raw_oracle_payment_cdc
GROUP BY
    kafka_topic,
    kafka_partition
ORDER BY kafka_partition;
```

> These Kafka topic, partition and offset values prove that the analytical records arrived through the Kafka CDC stream rather than through an application-side Oracle-to-ClickHouse copy.

---

## 12. Inspect recent event lineage in detail

```sql
SELECT
    payment_id,
    dbz_op,
    source_scn,
    source_commit_scn,
    source_tx_id,
    kafka_partition,
    kafka_offset,
    kafka_timestamp,
    ingested_at
FROM analytics.raw_oracle_payment_cdc
ORDER BY ingested_at DESC
LIMIT 20;
```

This is useful when explaining observability and ordering.

Important distinction:

```text
source_commit_scn / source_scn = source ordering
kafka_offset                   = transport lineage
ingested_at                    = ClickHouse arrival time
```

Do not describe `ingested_at` as the authoritative business ordering field.

---

## 13. Approximate Oracle-to-ClickHouse latency

```sql
SELECT
    payment_id,
    source_commit_time,
    kafka_timestamp,
    ingested_at,
    dateDiff(
        'millisecond',
        source_commit_time,
        ingested_at
    ) AS oracle_to_clickhouse_ms
FROM analytics.raw_oracle_payment_cdc
WHERE source_commit_time IS NOT NULL
ORDER BY ingested_at DESC
LIMIT 20;
```

> This gives an approximate commit-to-ClickHouse propagation time for recent CDC events.

If ClickHouse reports a timestamp type mismatch on a particular environment/version, skip this query during the live demo rather than changing the underlying model at presentation time.

---

## 14. Current taxpayer state

```sql
SELECT *
FROM analytics.dim_oracle_taxpayer_current
ORDER BY taxpayer_id;
```

This can be compared with the raw taxpayer event query to explain history versus current state.

---

## 15. Current station state

```sql
SELECT *
FROM analytics.dim_oracle_station_current
ORDER BY station_id;
```

This is useful when explaining how business-friendly station names are resolved downstream.

---

## Recommended six-query demo sequence

For a short presentation, use these in order:

1. Business serving view — Query 3
2. Raw CDC events — Query 4
3. Multiple versions of one payment — Query 5
4. Historical station proof — Query 7
5. Payments by station — Query 9
6. Kafka lineage / latency — Query 11 or 13

The story becomes:

```text
business result
    ↓
raw CDC history
    ↓
latest-state reconstruction
    ↓
historical correctness
    ↓
analytics
    ↓
lineage / latency
```

That sequence explains the architecture without requiring the audience to understand every internal ClickHouse table first.
