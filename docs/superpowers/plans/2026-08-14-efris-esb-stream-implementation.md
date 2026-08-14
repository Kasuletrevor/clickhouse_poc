# EFRIS ESB Streaming Ingestion Implementation Plan

> **For implementation:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.

## Goal

Ingest every currently retained message in Kafka topic `EAI_Efris` and then continue consuming live ESB traffic into ClickHouse, preserving the original JSON for seven days and a narrow long-term analytical event record without decrypting `data.content`.

## Architecture

Use one ClickHouse `Kafka` engine table as the consumer for `EAI_Efris`. The Kafka table reads each Kafka value as one opaque string (`RawBLOB`) so new JSON fields and malformed JSON cannot break Kafka deserialization. A single materialized view writes the exact payload plus Kafka lineage into `analytics.raw_efris_esb`. A second materialized view parses only valid JSON from the raw table into `analytics.efris_event`; invalid JSON remains visible through a view over the seven-day raw table. `efris_event` is eventually deduplicated by Kafka physical identity with `ReplacingMergeTree`, while the raw table preserves every ClickHouse delivery for forensic accounting. Kafka and raw ClickHouse retention are seven days; parsed events are retained long-term for the POC.

The initial ClickHouse consumer group is `clickhouse-efris-esb-poc-v1`. It must be positioned at the earliest retained offsets before the Kafka-to-raw materialized view is attached. This is deliberately separated from schema creation so no live consumer starts before the bootstrap offset is verified.

## Tech Stack

- Apache Kafka 4.3.x, topic `EAI_Efris`
- ClickHouse 26.7.x, database `analytics`
- ClickHouse Kafka table engine and materialized views
- Bash for idempotent Kafka policy and verification helpers
- Pytest contract tests for checked-in SQL/shell behavior
- Docker Compose runtime already used by the POC

## Delivery Boundary

This implementation delivers the **real ESB → Kafka → ClickHouse data plane and analytical foundation**. It does not redesign the existing web UI in the same change. Once this pipeline is verified against live EFRIS traffic, a separate UI task can switch/add dashboard pages backed by `analytics.efris_event`.

---

## Task 1: Add failing contract tests for the approved stream contract

**Files:**
- Create: `tests/test_efris_esb_stream_contract.py`
- Reference: `docs/superpowers/specs/2026-08-14-efris-esb-stream-design.md`

- [ ] **Step 1: Write tests before implementation files exist**

Create tests that expect the future implementation to provide all of the following:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_SCHEMA = ROOT / "clickhouse/sql/efris_esb/001_schema.sql"
SQL_START = ROOT / "clickhouse/sql/efris_esb/002_start_consumer.sql"
KAFKA_SCRIPT = ROOT / "scripts/configure_efris_esb_topic.sh"
VERIFY_SCRIPT = ROOT / "scripts/verify_efris_esb_stream.sh"


def test_schema_contract():
    sql = SQL_SCHEMA.read_text()
    assert "analytics.raw_efris_esb" in sql
    assert "analytics.efris_event" in sql
    assert "EAI_Efris" in sql
    assert "clickhouse-efris-esb-poc-v1" in sql
    assert "kafka_format = 'RawBLOB'" in sql
    assert "INTERVAL 7 DAY" in sql
    assert "return_code = '00'" in sql
    assert "isValidJSON" in sql
    assert "dataExchangeId" in sql
    assert "_partition" not in sql  # physical Kafka virtuals belong in start-consumer MV


def test_consumer_start_contract():
    sql = SQL_START.read_text()
    assert "efris_esb_kafka_to_raw_mv" in sql
    assert "_topic" in sql
    assert "_partition" in sql
    assert "_offset" in sql
    assert "_timestamp_ms" in sql


def test_kafka_retention_is_topic_scoped():
    script = KAFKA_SCRIPT.read_text()
    assert "EAI_Efris" in script
    assert "retention.ms=604800000" in script
    assert "retention.bytes=-1" in script
    assert "cleanup.policy=delete" in script
    assert "segment.ms=3600000" in script
    assert "--entity-type topics" in script


def test_verification_checks_offsets_and_live_ingestion():
    script = VERIFY_SCRIPT.read_text()
    assert "kafka-get-offsets" in script
    assert "kafka-consumer-groups" in script
    assert "raw_efris_esb" in script
    assert "efris_event" in script
```

Do not make the test depend on secrets, live Kafka, or a running ClickHouse container. Runtime verification comes later.

- [ ] **Step 2: Run the focused test and verify it fails for missing implementation files**

Run:

```bash
python -m pytest -q tests/test_efris_esb_stream_contract.py
```

Expected: FAIL because the new SQL/scripts do not exist yet.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/test_efris_esb_stream_contract.py
git commit -m "test: define EFRIS ESB stream contract"
```

---

## Task 2: Add the topic-scoped seven-day Kafka policy

**Files:**
- Create: `scripts/configure_efris_esb_topic.sh`
- Test: `tests/test_efris_esb_stream_contract.py`

- [ ] **Step 1: Implement an idempotent topic configuration script**

The script must configure **only** `EAI_Efris` by default and must not alter partitions or replication factor.

Core command:

```bash
/opt/kafka/bin/kafka-configs.sh \
  --bootstrap-server kafka:19092 \
  --entity-type topics \
  --entity-name EAI_Efris \
  --alter \
  --add-config 'cleanup.policy=delete,retention.ms=604800000,retention.bytes=-1,segment.ms=3600000'
```

Use environment-overridable shell variables for container name, bootstrap server, and topic, with safe defaults matching the POC. Execute through `sudo docker exec poc-kafka ...`. End by describing the topic configuration so the operator sees the applied values.

Do **not** add any global broker retention setting and do **not** touch `__consumer_offsets`, Kafka Connect state topics, or Debezium schema-history topics.

- [ ] **Step 2: Run the focused contract test**

```bash
python -m pytest -q tests/test_efris_esb_stream_contract.py
```

Expected: the Kafka-policy assertions pass; SQL/start/verification assertions remain red until later tasks.

- [ ] **Step 3: Shell syntax check**

```bash
bash -n scripts/configure_efris_esb_topic.sh
```

Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add scripts/configure_efris_esb_topic.sh tests/test_efris_esb_stream_contract.py
git commit -m "feat: configure EFRIS Kafka retention"
```

---

## Task 3: Create the ClickHouse raw and parsed schema without starting Kafka consumption

**Files:**
- Create: `clickhouse/sql/efris_esb/001_schema.sql`
- Test: `tests/test_efris_esb_stream_contract.py`

- [ ] **Step 1: Define the seven-day raw table**

Use a persistent raw table similar to:

```sql
CREATE TABLE IF NOT EXISTS analytics.raw_efris_esb
(
    payload String,
    kafka_topic LowCardinality(String),
    kafka_partition UInt64,
    kafka_offset UInt64,
    kafka_timestamp Nullable(DateTime64(3)),
    ingested_at DateTime64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(ingested_at)
ORDER BY (kafka_topic, kafka_partition, kafka_offset, ingested_at)
TTL ingested_at + INTERVAL 7 DAY DELETE;
```

The raw table intentionally preserves every delivery rather than pretending the Kafka→ClickHouse path is exactly once.

- [ ] **Step 2: Define the narrow analytical event table**

Use `ReplacingMergeTree(ingested_at)` keyed by physical Kafka identity so duplicate deliveries converge during merges while remaining explicitly at-least-once at ingestion time.

Required columns:

```sql
event_id Nullable(String),
event_time Nullable(DateTime64(3, 'Africa/Kampala')),
interface_code String,
tin Nullable(String),
taxpayer_id Nullable(String),
legal_name Nullable(String),
taxpayer_user_id Nullable(String),
device_no Nullable(String),
return_code String,
return_message String,
normalized_return_message String,
is_success UInt8,
app_id Nullable(String),
version Nullable(String),
content_present UInt8,
content_bytes UInt64,
content_encrypted UInt8,
kafka_topic LowCardinality(String),
kafka_partition UInt64,
kafka_offset UInt64,
kafka_timestamp Nullable(DateTime64(3)),
ingested_at DateTime64(3)
```

Use:

```sql
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ingested_at)
ORDER BY (kafka_topic, kafka_partition, kafka_offset)
```

Do not add the encrypted `data.content` or `signature` to this table.

- [ ] **Step 3: Define the Kafka engine table but do not attach its materialized view yet**

Create one-column queue table:

```sql
CREATE TABLE IF NOT EXISTS analytics.efris_esb_kafka_queue
(
    payload String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'kafka:19092',
    kafka_topic_list = 'EAI_Efris',
    kafka_group_name = 'clickhouse-efris-esb-poc-v1',
    kafka_format = 'RawBLOB',
    kafka_num_consumers = 1,
    kafka_thread_per_consumer = 1,
    kafka_max_block_size = 10000,
    kafka_poll_max_batch_size = 10000;
```

Keep `kafka_num_consumers = 1` while the topic has one partition. Increasing partitions later is a separate operational change; consumer count can then be increased to match useful parallelism.

Do not create `analytics.efris_esb_kafka_to_raw_mv` in this file. That separation is what lets us establish/verify the earliest consumer-group position before live consumption begins.

- [ ] **Step 4: Create the raw→parsed materialized view with tolerant extraction**

The materialized view must read from `analytics.raw_efris_esb`, not directly from Kafka, and must include:

```sql
WHERE isValidJSON(payload)
```

Use `JSONExtractString` only for the agreed narrow fields. Convert empty optional strings using `nullIf(..., '')`. Parse `globalInfo.requestTime` as Africa/Kampala time with a best-effort `OrNull` parser. Derive:

```sql
return_code = JSONExtractString(payload, 'returnStateInfo', 'returnCode')
is_success = return_code = '00'
content_present = notEmpty(JSONExtractString(payload, 'data', 'content'))
content_bytes = length(JSONExtractString(payload, 'data', 'content'))
content_encrypted = JSONExtractString(payload, 'data', 'dataDescription', 'encryptCode') = '1'
```

Normalize the known parameterized message pattern conservatively while retaining the original message. The first implementation should strip only trailing contextual text beginning with `(TIN:` rather than attempting to infer every future EFRIS message pattern.

- [ ] **Step 5: Add an invalid-message view instead of duplicating raw payloads**

```sql
CREATE VIEW IF NOT EXISTS analytics.v_efris_esb_invalid_messages AS
SELECT *
FROM analytics.raw_efris_esb
WHERE NOT isValidJSON(payload);
```

This accounts for malformed JSON during the same seven-day raw window without another raw-payload copy.

- [ ] **Step 6: Add the documented interface dimension**

Create `analytics.dim_efris_interface` and seed the documented mappings currently used by the POC, including at minimum T104, T106, T108, T109, T110, T113, T114, T115, T118, T119, T124, T125, T126, T127, T128, T129, T130, T131, T137, T138 and T139. Unknown codes must remain usable through LEFT JOINs; never reject them.

- [ ] **Step 7: Add the observed return-code view**

Create a view grouped by:

```text
(interface_code, return_code, normalized_return_message)
```

Expose:

```text
first_seen
last_seen
event_count
distinct_taxpayers
distinct_devices
is_success
```

The view must learn from the stream; do not hard-code undocumented return-code meanings. `00` is the only initial success rule.

- [ ] **Step 8: Re-run contract tests**

```bash
python -m pytest -q tests/test_efris_esb_stream_contract.py
```

Expected: schema-related assertions pass; start-consumer and verification assertions still fail until their files exist.

- [ ] **Step 9: Commit**

```bash
git add clickhouse/sql/efris_esb/001_schema.sql tests/test_efris_esb_stream_contract.py
git commit -m "feat: add EFRIS ESB ClickHouse schema"
```

---

## Task 4: Add the controlled consumer-start SQL and verification helper

**Files:**
- Create: `clickhouse/sql/efris_esb/002_start_consumer.sql`
- Create: `scripts/verify_efris_esb_stream.sh`
- Test: `tests/test_efris_esb_stream_contract.py`

- [ ] **Step 1: Create the Kafka→raw materialized view in a separate file**

The complete consumer-start file should create only the bridge from the already-defined Kafka queue to the raw table:

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.efris_esb_kafka_to_raw_mv
TO analytics.raw_efris_esb
AS
SELECT
    payload,
    _topic AS kafka_topic,
    _partition AS kafka_partition,
    _offset AS kafka_offset,
    _timestamp_ms AS kafka_timestamp,
    now64(3) AS ingested_at
FROM analytics.efris_esb_kafka_queue;
```

Using `_topic`, `_partition`, `_offset`, and `_timestamp_ms` preserves Kafka lineage in every raw row.

- [ ] **Step 2: Add a verification script that does not mutate data**

The script must report, not hide:

- Kafka topic partition count and end offsets
- ClickHouse consumer-group current offset and lag
- raw total rows and unique `(topic, partition, offset)` count
- valid versus invalid JSON raw rows
- parsed event total/physical-identity count
- `returnCode='00'` success count/rate
- distinct interfaces, taxpayers and devices
- newest Kafka timestamp / event time / ClickHouse ingestion time
- duplicate-delivery count (`raw count - unique physical identities`)
- observed return-code samples
- raw TTL definition

Use `kafka-get-offsets.sh` and `kafka-consumer-groups.sh` for Kafka. Use `clickhouse-client` for ClickHouse. Accept the ClickHouse password only through an environment variable if authentication requires it; never embed a password in the repository or print it.

- [ ] **Step 3: Finish the contract tests**

```bash
python -m pytest -q tests/test_efris_esb_stream_contract.py
bash -n scripts/configure_efris_esb_topic.sh
bash -n scripts/verify_efris_esb_stream.sh
```

Expected: all focused tests/syntax checks pass.

- [ ] **Step 4: Commit**

```bash
git add clickhouse/sql/efris_esb/002_start_consumer.sql scripts/verify_efris_esb_stream.sh tests/test_efris_esb_stream_contract.py
git commit -m "feat: add EFRIS stream consumer bootstrap"
```

---

## Task 5: Deploy on `datalake-test02` from the earliest retained Kafka offsets

**Files used:**
- `scripts/configure_efris_esb_topic.sh`
- `clickhouse/sql/efris_esb/001_schema.sql`
- `clickhouse/sql/efris_esb/002_start_consumer.sql`
- `scripts/verify_efris_esb_stream.sh`

This task is runtime verification; no success claim is allowed before its commands pass on the RHEL host.

- [ ] **Step 1: Pull the branch without overwriting the host's local Kafka advertised-listener edit**

First inspect:

```bash
git status --short
git branch --show-current
```

The host may still show a local modification to `compose.yaml` for the external advertised Kafka listener. Preserve it. Do not reset or overwrite it as part of this feature.

Then update the feature branch using the safest path compatible with that local modification.

- [ ] **Step 2: Capture the Kafka retained range before starting ClickHouse**

Run both earliest and latest offsets and save/display them for reconciliation:

```bash
sudo docker exec poc-kafka /opt/kafka/bin/kafka-get-offsets.sh \
  --bootstrap-server kafka:19092 --topic EAI_Efris --time -2

sudo docker exec poc-kafka /opt/kafka/bin/kafka-get-offsets.sh \
  --bootstrap-server kafka:19092 --topic EAI_Efris --time -1
```

For each partition, `latest - earliest` is the retained backlog existing at bootstrap time.

- [ ] **Step 3: Apply the seven-day Kafka topic policy**

```bash
bash scripts/configure_efris_esb_topic.sh
```

Verify the describe output shows:

```text
cleanup.policy=delete
retention.ms=604800000
retention.bytes=-1
segment.ms=3600000
```

Do not change the partition count in this task.

- [ ] **Step 4: Create the ClickHouse schema while the Kafka-to-raw MV is still absent**

Run the schema SQL through the existing ClickHouse container/client using credentials supplied from the environment, never from checked-in files:

```bash
sudo docker exec -i poc-clickhouse clickhouse-client \
  --user kjt --password "$CLICKHOUSE_PASSWORD" --multiquery \
  < clickhouse/sql/efris_esb/001_schema.sql
```

Then confirm the queue exists but the start MV does not:

```sql
SELECT name, engine
FROM system.tables
WHERE database = 'analytics'
  AND name IN ('efris_esb_kafka_queue', 'raw_efris_esb', 'efris_event', 'efris_esb_kafka_to_raw_mv')
ORDER BY name;
```

Expected: the three tables exist; `efris_esb_kafka_to_raw_mv` is absent.

- [ ] **Step 5: Position the dedicated consumer group at the earliest retained offsets**

While no ClickHouse Kafka-to-raw MV is attached, execute a dry run first:

```bash
sudo docker exec poc-kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:19092 \
  --group clickhouse-efris-esb-poc-v1 \
  --topic EAI_Efris \
  --reset-offsets --to-earliest
```

Then execute:

```bash
sudo docker exec poc-kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:19092 \
  --group clickhouse-efris-esb-poc-v1 \
  --topic EAI_Efris \
  --reset-offsets --to-earliest --execute
```

Immediately describe the group and verify each partition's current offset equals the captured earliest retained offset.

**Hard gate:** if the broker/CLI refuses to initialize/reset this new inactive group, do **not** attach the materialized view and do not allow the consumer to default to latest. Stop here and implement a tested ClickHouse/librdkafka `auto.offset.reset=smallest` configuration scoped to this stream before proceeding. The requirement is all retained + live, not live-only.

- [ ] **Step 6: Attach the Kafka→raw materialized view**

Only after earliest offsets are proven:

```bash
sudo docker exec -i poc-clickhouse clickhouse-client \
  --user kjt --password "$CLICKHOUSE_PASSWORD" --multiquery \
  < clickhouse/sql/efris_esb/002_start_consumer.sql
```

This is the moment live/background consumption begins.

- [ ] **Step 7: Watch the consumer catch up**

Run repeatedly:

```bash
sudo docker exec poc-kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:19092 \
  --group clickhouse-efris-esb-poc-v1 \
  --describe
```

Expected: lag decreases toward zero while the topic continues receiving live ESB traffic.

- [ ] **Step 8: Prove the bootstrap backlog was not skipped**

Using the retained earliest/end offsets captured before Step 6, query ClickHouse per partition and confirm the raw table contains physical offsets covering that initial range. For the initial one-partition topic this means the raw minimum offset equals the captured earliest offset and the number of unique offsets below the captured initial end offset equals `initial_end - initial_earliest`.

Use physical Kafka identities, not only `count(*)`, because at-least-once redelivery may produce duplicate raw rows.

- [ ] **Step 9: Prove parsed reconciliation**

Run checks equivalent to:

```sql
SELECT count() AS raw_rows,
       uniqExact((kafka_topic, kafka_partition, kafka_offset)) AS raw_unique
FROM analytics.raw_efris_esb;

SELECT countIf(isValidJSON(payload)) AS valid_json,
       countIf(NOT isValidJSON(payload)) AS invalid_json
FROM analytics.raw_efris_esb;

SELECT count() AS parsed_rows,
       uniqExact((kafka_topic, kafka_partition, kafka_offset)) AS parsed_unique
FROM analytics.efris_event FINAL;
```

Expected: `parsed_unique` equals the unique physical identities among valid raw JSON; invalid raw JSON is explicitly accounted rather than blocking the consumer.

- [ ] **Step 10: Prove success and encrypted-content behavior**

Verify known success events satisfy:

```text
return_code = '00'
is_success = 1
```

and that successful encrypted payloads expose only `content_present`, `content_bytes`, and `content_encrypted` in `efris_event`; there must be no analytical `content`/`signature` column.

- [ ] **Step 11: Prove live continuation**

Record the latest raw Kafka offset in ClickHouse, wait for the next real ESB event, and show that the maximum offset advances without running a batch job or manually triggering ClickHouse.

- [ ] **Step 12: Run the verification helper**

```bash
bash scripts/verify_efris_esb_stream.sh
```

Expected: healthy consumer, near-zero/zero lag depending on live arrival rate, raw/parsed reconciliation, seven-day TTL, and current event freshness.

---

## Task 6: Document the operational runbook and run the full repository verification

**Files:**
- Create: `docs/efris-esb-stream.md`
- Update: `README.md` only if a short link to the new runbook fits the existing documentation structure

- [ ] **Step 1: Document the final object map**

Document:

```text
EAI_Efris
  -> analytics.efris_esb_kafka_queue
  -> analytics.efris_esb_kafka_to_raw_mv
  -> analytics.raw_efris_esb           (7-day TTL)
  -> analytics.efris_esb_raw_to_event_mv
  -> analytics.efris_event             (long-term POC)
  -> analytics.dim_efris_interface
  -> analytics.v_efris_observed_return_codes
  -> analytics.v_efris_esb_invalid_messages
```

Include the consumer group, seven-day Kafka policy, at-least-once semantics, Kafka physical identity, and the rule that the POC never decrypts `data.content`.

- [ ] **Step 2: Add recovery notes**

Cover:

- ClickHouse restart: resume from committed consumer offsets.
- Reprocessing inside Kafka's retained seven-day window: detach/drop the consumer MV as appropriate, reset the dedicated group only while inactive, then reattach.
- Never reset unrelated consumer groups.
- If ClickHouse is down longer than Kafka retention, old Kafka events may no longer be recoverable from this topic.
- Raw ClickHouse data expires after seven days; parsed history remains.
- Future Hudi/HDFS is the intended durable raw archive if long-term raw retention becomes a requirement.

- [ ] **Step 3: Run focused and full tests**

```bash
python -m pytest -q tests/test_efris_esb_stream_contract.py
python -m pytest -q
python -m compileall -q app scripts
bash -n scripts/configure_efris_esb_topic.sh
bash -n scripts/verify_efris_esb_stream.sh
node --check app/static/js/simulator_controller.js
```

Expected: all existing repository tests continue to pass; the stream contract test passes.

- [ ] **Step 4: Commit documentation**

```bash
git add docs/efris-esb-stream.md README.md
git commit -m "docs: add EFRIS ESB stream runbook"
```

- [ ] **Step 5: Final implementation verification before PR**

Record evidence for the PR:

```text
Kafka topic config: 7-day retention
Initial retained offsets: captured
Consumer starts at earliest retained offsets: proven
Consumer lag after catch-up: near zero/zero
Raw unique Kafka identities: N
Parsed valid unique Kafka identities: N
Malformed/invalid JSON accounted: N
Success events returnCode=00 -> is_success=1: proven
New live ESB event arrives automatically in ClickHouse: proven
Raw TTL: 7 days
Full pytest: pass
```

Do not claim the feature complete if any of those runtime checks are missing.

---

## Notes for the Implementer

1. **Do not edit `compose.yaml` for this feature unless runtime testing proves it unavoidable.** The RHEL working tree may carry a deliberate local advertised-listener change for external ESB access, and this ingestion path can use Docker-internal `kafka:19092`.
2. **Do not hard-code credentials** in SQL, shell scripts, docs, tests, or commits.
3. **Do not decrypt success content.** The raw table holds the original message for seven days; `efris_event` stores only content presence/length/encryption flags.
4. **Do not silently skip retained Kafka history.** The earliest-offset bootstrap is a hard requirement.
5. **Do not call the path exactly once.** Raw delivery is at-least-once. `efris_event` uses Kafka identity plus `ReplacingMergeTree` for eventual analytical deduplication; verification must still measure duplicate deliveries explicitly.
6. **Do not increase Kafka partitions as part of this implementation.** One partition is sufficient to bring the live stream online. If throughput later requires more, increase the topic partitions deliberately and then raise `kafka_num_consumers` no higher than the partition count.
7. **Keep the UI out of this PR.** First prove real ESB traffic is flowing and modeled correctly. The live operational dashboard becomes the next bounded feature.
