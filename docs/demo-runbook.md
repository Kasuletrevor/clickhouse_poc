# Manager Demo Runbook

This runbook is optimized for a short, clear demonstration of the CDC architecture.

The story to tell is:

> The transactional application writes to Oracle normally. Oracle redo is captured by Debezium, streamed through Kafka, modeled in ClickHouse, and exposed to Power BI without the source application writing to the analytical systems.

---

## 1. Pre-demo checks

Run these before the audience arrives.

### Containers

```bash
cd /home/jkasule/cdc-clickhouse-poc
sudo docker compose ps
```

Ensure Oracle, Kafka, Debezium and ClickHouse are healthy/running.

### Debezium

```bash
curl -s http://localhost:8083/connectors/oracle-cdc-flat/status | python -m json.tool
```

Confirm connector and task are `RUNNING`.

### Kafka lag

```bash
sudo docker exec poc-kafka \
 /opt/kafka/bin/kafka-consumer-groups.sh \
 --bootstrap-server kafka:19092 \
 --describe --group clickhouse-oracle-payment-poc-v1
```

Prefer starting the demo with lag 0.

### ClickHouse

```bash
sudo docker exec poc-clickhouse clickhouse-client \
  --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
  --database analytics \
  --query '
SELECT count() AS payments,
       max(payment_time) AS latest_payment
FROM fact_oracle_payment_current
'
```

### Power BI

Open the prepared report and ensure the connection works before the presentation.

### Kafbat

Open:

```text
http://10.1.78.38:8080
```

Pre-navigate to the Oracle payment topic if possible.

---

## 2. Recommended presentation order

### Step 1 — Start with the business result

Show Power BI first.

Explain:

> This is the analytical result. The important part is how a source transaction reaches this view without the source application being coupled to the analytics platform.

Keep this brief.

---

### Step 2 — Show the source-system action

Use the internal app when available.

Until then, use the Oracle-only simulator.

Example:

```bash
python simulator/oracle_simulator.py \
  payment \
  --id PAY_DEMO_001 \
  --taxpayer TIN001 \
  --amount 925000 \
  --status PENDING
```

Explain:

> This program only connects to Oracle. It does not call Kafka, Debezium or ClickHouse.

---

## 3. Verify Oracle source truth

Query the newly created payment in Oracle.

Example SQL:

```sql
SELECT PAYMENT_ID,
       TAXPAYER_ID,
       AMOUNT,
       STATUS,
       PAYMENT_TIME,
       UPDATED_AT
FROM CDC_APP.PAYMENT
WHERE PAYMENT_ID = 'PAY_DEMO_001';
```

Explain:

> At this point the source transaction is committed. The downstream flow is driven by redo-based CDC.

---

## 4. Show Debezium/Kafka evidence

Use Kafbat for the visual demonstration.

Show either:

```text
oraclecdc.CDC_APP.PAYMENT
```

for the native envelope, or:

```text
oracleflat.CDC_APP.PAYMENT
```

for the flattened event.

Point out fields such as:

```text
PAYMENT_ID
STATUS
__op
__source_scn
__source_commit_scn
__source_txId
```

Explain:

> Debezium reads the Oracle redo stream with LogMiner. Kafka provides a durable buffer and consumer offsets between capture and analytics.

Do not spend too long reading raw JSON unless the audience asks.

---

## 5. Show ClickHouse ingestion

Query the raw history:

```bash
sudo docker exec poc-clickhouse clickhouse-client \
  --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
  --database analytics \
  --query "
SELECT payment_id,
       status,
       dbz_op,
       source_scn,
       source_commit_scn,
       kafka_partition,
       kafka_offset,
       ingested_at
FROM raw_oracle_payment_cdc
WHERE payment_id = 'PAY_DEMO_001'
ORDER BY event_version
"
```

Then current state:

```bash
sudo docker exec poc-clickhouse clickhouse-client \
  --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
  --database analytics \
  --query "
SELECT *
FROM fact_oracle_payment_current
WHERE payment_id = 'PAY_DEMO_001'
FORMAT Vertical
"
```

Explain:

> Raw history retains the events; the current view resolves the latest valid state using source ordering, not ClickHouse arrival time.

---

## 6. Demonstrate an update

Change the same payment from pending to successful.

Use the source application/simulator, not direct ClickHouse SQL.

Then show two rows in raw history:

```text
CREATE / PENDING
UPDATE / SUCCESSFUL
```

and one latest row in:

```text
fact_oracle_payment_current
```

Explain:

> We keep the event history while exposing a clean current-state view for applications and analytics.

---

## 7. Demonstrate station history

This is the strongest semantic demonstration.

Explain the known scenario:

```text
TIN001 at Kampala Central
PAY102 happens
TIN001 moves to Jinja
PAY103 happens
```

Query:

```bash
sudo docker exec poc-clickhouse clickhouse-client \
  --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
  --database analytics \
  --query '
SELECT payment_id,
       taxpayer_id,
       payment_time,
       station_at_payment,
       current_station
FROM vw_oracle_payment_analytics
WHERE payment_id IN (\'PAY102\', \'PAY103\')
ORDER BY payment_time
'
```

Expected conceptual result:

```text
PAY102  Kampala Central  Jinja
PAY103  Jinja            Jinja
```

Explain:

> We preserve the business context that was true at transaction time while also showing the taxpayer's current state.

This is more valuable than simply copying rows from one database to another.

---

## 8. Show Kafka lag

```bash
sudo docker exec poc-kafka \
 /opt/kafka/bin/kafka-consumer-groups.sh \
 --bootstrap-server kafka:19092 \
 --describe --group clickhouse-oracle-payment-poc-v1
```

Explain:

> Lag tells us whether analytics is keeping up with the source stream. In normal POC operation it returns to zero.

---

## 9. Return to Power BI

Refresh the report or let DirectQuery retrieve the latest state.

Show the newly created/updated transaction.

Close with:

> The source application made an ordinary Oracle transaction. Everything after the commit was handled by the CDC architecture.

---

## 10. Optional continuous-load demo

If you want the report to stay visibly active:

```bash
nohup python -u simulator/run_load.py \
  --transactions-per-minute 10 \
  > simulator/load.log 2>&1 &
```

Monitor:

```bash
tail -f simulator/load.log
```

and/or:

```bash
watch -n 2 'sudo docker exec poc-clickhouse clickhouse-client \
  --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
  --database analytics \
  --query "SELECT count(), max(payment_time) FROM fact_oracle_payment_current"'
```

Stop after the demo:

```bash
pkill -f 'simulator/run_load.py'
```

---

## 11. Key messages to repeat

1. **No source-table polling.** Capture is redo/log-based.
2. **The source app knows only Oracle.**
3. **Kafka decouples capture from analytics.**
4. **ClickHouse keeps raw history and serves analytical state.**
5. **Historical business context is preserved.**
6. **Kafka lag and CDC metadata make the pipeline observable.**
7. **Power BI consumes the serving layer, not raw CDC complexity.**

---

## 12. What not to do during the demo

Avoid risky last-minute changes such as:

- recreating connectors
- resetting active consumer offsets
- changing Oracle logging
- rebuilding ClickHouse tables
- changing Docker networking
- changing proxy/firewall settings
- introducing new versions/images

Freeze the working architecture before the presentation.
