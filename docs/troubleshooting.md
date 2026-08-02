# Troubleshooting Guide

This document captures problems already encountered while building the CDC POC and the fixes/diagnostic patterns that worked.

Use it before changing architecture or rebuilding services.

---

## 1. Git shows Docker data permission errors

Symptom:

```text
warning: could not open directory 'clickhouse/data/...': Permission denied
```

Cause:

Git is traversing container-owned persistent runtime data that should never be version controlled.

Correct fix:

Ignore runtime data:

```text
oracle/oradata/
kafka/data/
clickhouse/data/
clickhouse/logs/
```

Do **not** `chown` or `chmod` database runtime directories merely to make Git read them. Container ownership may be required for the services to function.

Verify:

```bash
git check-ignore -v clickhouse/data/
git check-ignore -v kafka/data/
git check-ignore -v oracle/oradata/
```

---

## 2. Secrets appear as untracked files

Sensitive local files include:

```text
.env
debezium/oracle-cdc.json
debezium/oracle-cdc-flat.json
```

They should remain ignored if they contain real credentials.

Verify:

```bash
git check-ignore -v .env
git check-ignore -v debezium/oracle-cdc.json
git check-ignore -v debezium/oracle-cdc-flat.json
```

Do not commit a password simply because the repository is temporarily private or used for a POC.

---

## 3. Oracle official container registry times out

Observed behavior:

- `container-registry.oracle.com/database/free:latest-lite` timed out while retrieving image layers/manifests through the corporate proxy.
- direct registry HEAD through proxy reached the registry and received an expected authentication challenge, showing basic connectivity existed.
- the Johannesburg registry mirror failed DNS through the proxy.

Working fallback:

```text
gvenzl/oracle-free:latest
```

The environment successfully pulled and ran that image.

Do not repeatedly rebuild a working Oracle container merely to switch image source during the POC.

---

## 4. Oracle LogMiner / Debezium prerequisites

If Debezium cannot mine changes, verify the basics before touching connector transformations:

```sql
SELECT LOG_MODE FROM V$DATABASE;
```

Expected:

```text
ARCHIVELOG
```

Also verify supplemental logging and the Debezium common user grants.

The POC already established these successfully, so a new failure is more likely connector state/configuration or database availability than a need to repeat the entire setup.

---

## 5. SQL*Plus pasted statements become malformed

Observed symptom included statements being concatenated around `COMMIT`, producing errors such as:

```text
ORA-03405
```

Cause:

Large pasted blocks/blank-line behavior in SQL*Plus can produce unexpected parsing during interactive use.

Safer workflow:

```sql
UPDATE ...;
```

wait for response, then:

```sql
COMMIT;
```

For repeatable multi-statement changes, prefer a reviewed `.sql` script rather than rapid interactive paste.

---

## 6. Debezium connector validation returns confusing errors

Kafka Connect's connector validation endpoint expects the **flat config map**, with `name` inserted into that map.

It does not expect the outer connector creation wrapper:

```json
{
  "name": "...",
  "config": { ... }
}
```

Use the known validation pattern:

```bash
curl -s \
 -X PUT \
 -H "Content-Type: application/json" \
 --data "$(python -c "import json; d=json.load(open('debezium/oracle-cdc.json')); c=d['config']; c['name']=d['name']; print(json.dumps(c))")" \
 http://localhost:8083/connector-plugins/io.debezium.connector.oracle.OracleConnector/config/validate \
 | python -c "
import sys,json
d=json.load(sys.stdin)
print('error_count =', d['error_count'])
for x in d['configs']:
    errs=(x.get('value') or {}).get('errors', [])
    if errs:
        print(x['definition']['name'], ':', *errs)
"
```

---

## 7. Debezium Decimal appears as base64 in native JSON

Observed native event behavior:

Oracle `NUMBER(18,2)` through Kafka Connect's precise Decimal representation may appear encoded as bytes/base64 in the JSON converter output.

This is expected for Kafka Connect Decimal logical types under that representation.

For the flattened analytics connector, the POC uses:

```text
decimal.handling.mode=string
```

so amount appears as readable text such as:

```json
"AMOUNT": "880000.00"
```

Do not mistake the native base64 representation for corrupted Oracle data.

---

## 8. Flat connector loses useful metadata

If using `ExtractNewRecordState`, remember that the native envelope is removed.

The POC explicitly copies useful metadata before/while unwrapping via:

```text
transforms.unwrap.add.fields=
op,
table,
source.scn,
source.commit_scn,
source.txId,
source.ssn,
source.commit_ts_ms,
source.user_name
```

and uses delete rewrite behavior so deletions remain analytically visible.

If metadata disappears after changing SMT config, inspect this first.

---

## 9. Flat and raw connectors show different initial operation types

When a new connector is created later than another connector, its initial snapshot can produce `op=r` events for rows that the older connector originally saw as live `op=c` transactions.

That does not mean the connectors disagree about the row's current data.

For proving both connectors observe the same live transaction, create a new transaction **after both connectors are RUNNING**.

---

## 10. Kafka console command deprecation warnings

Kafka 4.x may warn that some console `--property` options are deprecated in favor of newer formatter/reader-property arguments.

A warning does not necessarily mean the command failed.

Read the output separately from warnings.

When modernizing scripts, update the CLI arguments deliberately rather than changing a working demo command immediately before a presentation.

---

## 11. ClickHouse Kafka consumer starts at the wrong offset

When attaching a newly created consumer group/materialized view to a topic with existing backlog, decide explicitly whether to consume from earliest or only new records.

For intentional replay, reset the group before starting/attaching the consumer:

```bash
sudo docker exec poc-kafka \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:19092 \
  --reset-offsets \
  --group clickhouse-oracle-payment-poc-v1 \
  --topic oracleflat.CDC_APP.PAYMENT \
  --to-earliest \
  --execute
```

Do not reset offsets casually for an active production-like group.

---

## 12. Unsupported ClickHouse Kafka setting

An earlier handcrafted setup attempted:

```text
kafka_auto_offset_reset
```

which was unsupported in the ClickHouse version/configuration being used.

The setting was removed.

Offset behavior was instead controlled through Kafka consumer-group offsets.

If ClickHouse rejects a Kafka-engine setting, verify it against the actual running ClickHouse version rather than assuming an example from another version applies.

---

## 13. ClickHouse current-state aggregate alias error

Observed error:

```text
ILLEGAL_AGGREGATION
```

A problematic pattern was using the same name as a source column for an aggregate alias, for example conceptually:

```sql
max(source_version) AS source_version
```

Use an unambiguous alias such as:

```sql
max(source_version) AS latest_source_version
```

This avoids name-resolution/aggregation ambiguity.

---

## 14. ClickHouse view exposes qualified names instead of clean BI columns

An early serving view definition relied on implicit output names such as:

```text
p.taxpayer_id
```

Power BI/queries expecting `taxpayer_id` then failed.

Correct pattern:

Explicitly alias every serving-column expression:

```sql
p.taxpayer_id AS taxpayer_id
```

Do this consistently for BI-facing views.

Verify with:

```sql
DESCRIBE TABLE vw_oracle_payment_analytics;
```

Serving-layer column names should be stable, clean and business-friendly.

---

## 15. Several ClickHouse events get the same `ingested_at`

This can happen when an existing Kafka backlog is consumed in a batch after the ClickHouse materialized view is attached.

It does not imply all source events happened at the same time.

Use:

```text
PAYMENT_TIME
source_commit_time
source_scn / source_commit_scn
kafka offset/timestamp
```

for event/source chronology.

Use `ingested_at` to answer:

> When did ClickHouse receive this event?

not:

> When did the business event happen?

---

## 16. Two changes have the same commit SCN

Multiple row changes may be committed in one Oracle transaction and therefore share commit-level metadata.

Do not assume every row change has a globally unique commit SCN.

Keep additional sequence/lineage fields such as source SCN, source sequence number and Kafka offset available for deterministic event ordering where required.

Also distinguish business time (`UPDATED_AT`, `PAYMENT_TIME`) from transaction commit time.

---

## 17. Historical station gets overwritten by current station

Symptom:

Old payments suddenly show the taxpayer's latest station as if that had always been the station.

Cause:

A naive join from payment to `dim_oracle_taxpayer_current` is being used for historical attribution.

Correct design:

- current station comes from current taxpayer state
- station at payment comes from taxpayer history valid at `payment_time`

The POC already proved this with PAY102/PAY103.

Treat regression of this behavior as a blocking correctness bug.

---

## 18. Kafka lag is non-zero

First inspect group state:

```bash
sudo docker exec poc-kafka \
 /opt/kafka/bin/kafka-consumer-groups.sh \
 --bootstrap-server kafka:19092 \
 --describe --group clickhouse-oracle-payment-poc-v1
```

Then check:

1. ClickHouse container is healthy.
2. Kafka engine/materialized view exists and is active.
3. Topic exists.
4. Consumer group is the expected one.
5. ClickHouse logs do not show JSON/schema parse failures.
6. New messages conform to the expected flat-event schema.

A brief transient lag during a burst can be normal. Persistently increasing lag is the important signal.

---

## 19. Debezium connector is FAILED/PAUSED

Check:

```bash
curl -s http://localhost:8083/connectors/oracle-cdc-flat/status | python -m json.tool
```

Read the task trace before recreating anything.

If merely paused:

```bash
curl -s -X PUT http://localhost:8083/connectors/oracle-cdc-flat/resume
```

If failed, classify the error first:

```text
Oracle connectivity/auth
LogMiner/archive availability
schema/config validation
Kafka connectivity
data conversion
```

Do not delete/recreate the connector as the first troubleshooting step because doing so can change snapshot/offset behavior.

---

## 20. ClickHouse port works on jump server but not desktop

Observed network behavior:

- desktop could reach port 8080
- direct desktop TCP to ClickHouse 8123/9000 timed out
- jump server could reach 8123/9000 directly
- desktop HTTP request to 8123 through the corporate proxy succeeded

Interpretation:

This is a network/ACL routing policy issue, not proof that ClickHouse or Docker port publishing is broken.

For Power BI, the working approach was to use the jump server where direct ClickHouse connectivity exists.

Do not repeatedly change ClickHouse Docker networking to solve a client-subnet ACL problem.

---

## 21. Power BI cannot see a serving view

Check the object exists:

```sql
SHOW TABLES FROM analytics;
```

and:

```sql
DESCRIBE TABLE analytics.vw_oracle_payment_analytics;
```

If the view was created after Power BI Navigator was opened, refresh/reconnect Navigator metadata.

If columns look qualified/incorrect, see the explicit-alias issue above.

---

## 22. Power BI semantic correctness

Power BI should consume serving objects such as:

```text
vw_oracle_payment_analytics
```

not the Kafka engine table and not raw CDC tables for ordinary business visuals.

Raw CDC belongs in engineering/diagnostic views.

If a Power BI measure produces strange double counting, confirm it is querying current/serving state rather than event history containing multiple versions per entity.

---

## 23. Detached simulator log appears frozen

Python stdout may be buffered under `nohup`.

Use:

```bash
nohup python -u simulator/run_load.py \
  --transactions-per-minute 10 \
  > simulator/load.log 2>&1 &
```

or set `PYTHONUNBUFFERED=1`.

Then:

```bash
tail -f simulator/load.log
```

---

## 24. More than one simulator is running

Check:

```bash
pgrep -af run_load.py
```

Stop duplicate workers:

```bash
pkill -f 'simulator/run_load.py'
```

Then start exactly one desired instance.

The future FastAPI simulator controller should prevent duplicate unmanaged workers.

---

## 25. FastAPI works in terminal but dies after SSH disconnect

Foreground development:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Detached short-term development:

```bash
nohup uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  > fastapi.log 2>&1 &
```

Once stable, use systemd so the application survives disconnects/reboots and automatically restarts.

---

## 26. Operational screens fail because ClickHouse is down

This is an application architecture bug.

Expected behavior:

```text
Payments     → Oracle → should work
Taxpayers    → Oracle → should work
Stations     → Oracle → should work
```

Only analytical/engineering screens should degrade when ClickHouse is unavailable.

Check for accidental shared startup dependencies or middleware that requires ClickHouse before serving any request.

---

## 27. App produces Kafka messages itself

This violates the core POC architecture.

Correct source path:

```text
App → Oracle COMMIT
```

Then independently:

```text
Oracle redo → Debezium → Kafka → ClickHouse
```

Remove any application-side Kafka publishing introduced for business CRUD unless it is explicitly part of a future, separately designed architecture.

---

## 28. App writes directly to ClickHouse after Oracle

Also a design violation.

Do not implement dual-write logic such as:

```text
write Oracle
write ClickHouse
```

It creates consistency problems and defeats the purpose of the CDC POC.

ClickHouse must be updated by the streaming pipeline.

---

## 29. Pre-demo troubleshooting priority

If something fails shortly before a presentation, diagnose in this order:

```text
1. Is Oracle source operation working?
2. Is Debezium connector/task RUNNING?
3. Is the event in Kafka?
4. Is consumer lag moving?
5. Did raw ClickHouse receive the event?
6. Does current/serving state resolve correctly?
7. Can Power BI query the serving layer?
```

This isolates the broken stage without guessing.

Avoid architecture changes immediately before the demo.
