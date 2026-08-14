# EFRIS ESB Streaming Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consume every message currently retained in Kafka topic `EAI_Efris`, then continue live ingestion into ClickHouse, keeping the exact JSON for seven days and a lean long-term analytical event without decrypting `data.content`.

**Architecture:** A ClickHouse `Kafka` engine table reads each Kafka message as one opaque `RawBLOB` string. One materialized view writes the exact payload plus Kafka lineage into `analytics.raw_efris_esb`; a second materialized view parses only valid JSON from raw into `analytics.efris_event`. Kafka physical identity `(topic, partition, offset)` is retained throughout. The Kafka-to-raw view is created only after the dedicated consumer group is proven to start at the earliest retained offsets.

**Tech Stack:** Apache Kafka 4.3.x, ClickHouse 26.7.x, ClickHouse Kafka engine/materialized views, Bash, Pytest, Docker Compose.

## Global Constraints

- Kafka topic: `EAI_Efris`.
- ClickHouse database: `analytics`.
- Consume **all currently retained messages plus live traffic**.
- Kafka `EAI_Efris` retention: 7 days after initial backlog catch-up is proven.
- ClickHouse `raw_efris_esb` TTL: 7 days.
- `efris_event`: long-term POC analytical history; no short TTL in this change.
- Success rule: `returnCode = '00'` only.
- Never decrypt, decode into business content, or duplicate encrypted `data.content` into `efris_event`.
- Preserve Kafka topic/partition/offset/timestamp lineage.
- Treat Kafka→ClickHouse as at-least-once; never claim exactly-once delivery.
- Do not change Kafka partition count or replication factor in this change.
- Do not apply EFRIS retention settings globally or to Kafka internal/Connect/Debezium topics.
- Do not edit `compose.yaml` unless runtime testing proves unavoidable; the RHEL working tree may contain a deliberate local advertised-listener change.
- No credentials or key material in source, SQL, tests, docs, or logs.
- UI/dashboard redesign is a separate bounded feature after the live data plane is verified.

---

### Task 1: Contract tests for the stream boundary

**Files:**
- Create: `tests/test_efris_esb_stream_contract.py`

**Interfaces:**
- Consumes: approved design at `docs/superpowers/specs/2026-08-14-efris-esb-stream-design.md`.
- Produces: executable repository contract for the SQL and shell files created in Tasks 2–4.

- [ ] **Step 1: Write the failing contract test**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "clickhouse/sql/efris_esb/001_schema.sql"
START = ROOT / "clickhouse/sql/efris_esb/002_start_consumer.sql"
KAFKA = ROOT / "scripts/configure_efris_esb_topic.sh"
VERIFY = ROOT / "scripts/verify_efris_esb_stream.sh"


def test_clickhouse_schema_contract():
    sql = SCHEMA.read_text()
    assert "analytics.raw_efris_esb" in sql
    assert "analytics.efris_event" in sql
    assert "analytics.efris_esb_kafka_queue" in sql
    assert "EAI_Efris" in sql
    assert "clickhouse-efris-esb-poc-v1" in sql
    assert "kafka_format = 'RawBLOB'" in sql
    assert "INTERVAL 7 DAY" in sql
    assert "isValidJSON" in sql
    assert "dataExchangeId" in sql
    assert "returnCode" in sql
    assert "= '00'" in sql


def test_start_consumer_preserves_kafka_lineage():
    sql = START.read_text()
    assert "efris_esb_kafka_to_raw_mv" in sql
    assert "_topic" in sql
    assert "_partition" in sql
    assert "_offset" in sql
    assert "_timestamp_ms" in sql


def test_kafka_policy_is_topic_scoped_and_seven_days():
    script = KAFKA.read_text()
    assert "EAI_Efris" in script
    assert "--entity-type topics" in script
    assert "retention.ms=604800000" in script
    assert "retention.bytes=-1" in script
    assert "cleanup.policy=delete" in script
    assert "segment.ms=3600000" in script
    assert "--partitions" not in script


def test_verifier_checks_offsets_and_tables():
    script = VERIFY.read_text()
    assert "kafka-get-offsets" in script
    assert "kafka-consumer-groups" in script
    assert "raw_efris_esb" in script
    assert "efris_event" in script
```

- [ ] **Step 2: Run the focused test and confirm RED**

```bash
python -m pytest -q tests/test_efris_esb_stream_contract.py
```

Expected: FAIL because the implementation files do not exist.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/test_efris_esb_stream_contract.py
git commit -m "test: define EFRIS ESB stream contract"
```

---

### Task 2: Kafka policy helper and ClickHouse schema

**Files:**
- Create: `scripts/configure_efris_esb_topic.sh`
- Create: `clickhouse/sql/efris_esb/001_schema.sql`
- Test: `tests/test_efris_esb_stream_contract.py`

**Interfaces:**
- Consumes: Kafka broker `kafka:19092`, topic `EAI_Efris`.
- Produces: an idempotent topic-retention helper and all ClickHouse objects except the Kafka→raw consumer-start MV.

- [ ] **Step 1: Implement the topic-scoped retention helper**

Use environment-overridable defaults (`KAFKA_CONTAINER=poc-kafka`, `KAFKA_BOOTSTRAP=kafka:19092`, `EFRIS_TOPIC=EAI_Efris`) and run only:

```bash
/opt/kafka/bin/kafka-configs.sh \
  --bootstrap-server "$KAFKA_BOOTSTRAP" \
  --entity-type topics \
  --entity-name "$EFRIS_TOPIC" \
  --alter \
  --add-config 'cleanup.policy=delete,retention.ms=604800000,retention.bytes=-1,segment.ms=3600000'
```

Then describe the topic. Do not alter partitions, replication, or broker defaults.

- [ ] **Step 2: Define `analytics.raw_efris_esb`**

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

Raw intentionally preserves every consumed delivery for forensic/reconciliation purposes.

- [ ] **Step 3: Define `analytics.efris_event`**

Use these columns exactly:

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
ORDER BY (kafka_topic, kafka_partition, kafka_offset);
```

This provides eventual analytical deduplication by Kafka identity without pretending ingestion itself is exactly once.

- [ ] **Step 4: Define the Kafka queue without starting consumption**

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

Do not create `analytics.efris_esb_kafka_to_raw_mv` in `001_schema.sql`. The consumer-start view belongs in Task 3 after earliest offsets are established.

- [ ] **Step 5: Define raw→parsed materialization**

Create `analytics.efris_esb_raw_to_event_mv TO analytics.efris_event` and parse only:

```sql
WHERE isValidJSON(payload)
```

Use `JSONExtractString(payload, 'globalInfo', ...)`, `JSONExtractString(payload, 'returnStateInfo', ...)`, and `JSONExtractString(payload, 'data', 'dataDescription', ...)` for the approved narrow fields. Convert empty optional strings with `nullIf(..., '')`. Parse `globalInfo.requestTime` with a best-effort `OrNull` DateTime64 parser in `Africa/Kampala`.

Derivations:

```sql
is_success = (return_code = '00')
content_present = notEmpty(JSONExtractString(payload, 'data', 'content'))
content_bytes = length(JSONExtractString(payload, 'data', 'content'))
content_encrypted = (JSONExtractString(payload, 'data', 'dataDescription', 'encryptCode') = '1')
```

For `normalized_return_message`, preserve the original `return_message` separately and initially remove only a trailing parameter block beginning with `(TIN:`. Do not invent undocumented error-code meanings.

- [ ] **Step 6: Define invalid-message and observed-code views**

```sql
CREATE VIEW IF NOT EXISTS analytics.v_efris_esb_invalid_messages AS
SELECT *
FROM analytics.raw_efris_esb
WHERE NOT isValidJSON(payload);
```

Create `analytics.v_efris_observed_return_codes` grouped by `(interface_code, return_code, normalized_return_message)` and expose `first_seen`, `last_seen`, `event_count`, `distinct_taxpayers`, `distinct_devices`, and `is_success`.

- [ ] **Step 7: Define the interface dimension idempotently**

Create `analytics.dim_efris_interface(interface_code String, interface_name String)` and seed the documented interface mappings used in the POC. Insert only codes not already present so rerunning `001_schema.sql` does not multiply rows. Include at least T104, T106, T108, T109, T110, T113, T114, T115, T118, T119, T124, T125, T126, T127, T128, T129, T130, T131, T137, T138 and T139. Unknown codes must remain analyzable through LEFT JOINs.

- [ ] **Step 8: Run focused tests and syntax checks**

```bash
python -m pytest -q tests/test_efris_esb_stream_contract.py
bash -n scripts/configure_efris_esb_topic.sh
```

Expected: Kafka/schema assertions pass; consumer-start/verifier assertions remain red.

- [ ] **Step 9: Commit**

```bash
git add scripts/configure_efris_esb_topic.sh clickhouse/sql/efris_esb/001_schema.sql tests/test_efris_esb_stream_contract.py
git commit -m "feat: add EFRIS ESB stream schema"
```

---

### Task 3: Controlled consumer start and runtime verifier

**Files:**
- Create: `clickhouse/sql/efris_esb/002_start_consumer.sql`
- Create: `scripts/verify_efris_esb_stream.sh`
- Test: `tests/test_efris_esb_stream_contract.py`

**Interfaces:**
- Consumes: `analytics.efris_esb_kafka_queue`, `analytics.raw_efris_esb`, consumer group `clickhouse-efris-esb-poc-v1`.
- Produces: background Kafka→raw ingestion and a read-only health/reconciliation report.

- [ ] **Step 1: Create the consumer-start MV**

`002_start_consumer.sql` must contain:

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

- [ ] **Step 2: Implement the read-only verifier**

`scripts/verify_efris_esb_stream.sh` must report:

```text
Kafka partition/end offsets
consumer-group current offset and lag
raw count and unique (topic,partition,offset)
valid/invalid JSON counts
parsed count and unique Kafka identities
raw duplicate-delivery count
success/failure counts and rate
distinct interfaces/taxpayers/devices
newest event/Kafka/ingestion timestamps
observed return-code sample
raw table TTL definition
```

Use `kafka-get-offsets.sh`, `kafka-consumer-groups.sh`, and `clickhouse-client`. Accept ClickHouse authentication only from environment variables; never embed or echo credentials.

- [ ] **Step 3: Run the focused tests and shell syntax checks**

```bash
python -m pytest -q tests/test_efris_esb_stream_contract.py
bash -n scripts/configure_efris_esb_topic.sh
bash -n scripts/verify_efris_esb_stream.sh
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add clickhouse/sql/efris_esb/002_start_consumer.sql scripts/verify_efris_esb_stream.sh tests/test_efris_esb_stream_contract.py
git commit -m "feat: add EFRIS Kafka consumer bootstrap"
```

---

### Task 4: Deploy from earliest retained offsets and prove catch-up/live continuity

**Files:**
- Use: `clickhouse/sql/efris_esb/001_schema.sql`
- Use: `clickhouse/sql/efris_esb/002_start_consumer.sql`
- Use: `scripts/configure_efris_esb_topic.sh`
- Use: `scripts/verify_efris_esb_stream.sh`

**Interfaces:**
- Consumes: live `EAI_Efris` topic on `datalake-test02`.
- Produces: verified `raw_efris_esb` + `efris_event` live pipeline and recorded bootstrap reconciliation evidence.

- [ ] **Step 1: Protect the server working tree**

```bash
git status --short
git branch --show-current
```

Preserve any local `compose.yaml` advertised-listener modification. Do not reset it.

- [ ] **Step 2: Capture the current retained Kafka range before changing retention**

```bash
sudo docker exec poc-kafka /opt/kafka/bin/kafka-get-offsets.sh \
  --bootstrap-server kafka:19092 --topic EAI_Efris --time -2

sudo docker exec poc-kafka /opt/kafka/bin/kafka-get-offsets.sh \
  --bootstrap-server kafka:19092 --topic EAI_Efris --time -1
```

Record earliest and end offset per partition. **Do not shorten Kafka retention yet**; the requirement is to ingest every message that is currently retained.

- [ ] **Step 3: Apply the ClickHouse schema only**

```bash
sudo docker exec -i poc-clickhouse clickhouse-client \
  --user kjt --password "$CLICKHOUSE_PASSWORD" --multiquery \
  < clickhouse/sql/efris_esb/001_schema.sql
```

Verify `efris_esb_kafka_queue`, `raw_efris_esb`, and `efris_event` exist and `efris_esb_kafka_to_raw_mv` does not.

- [ ] **Step 4: Position the dedicated inactive group at earliest**

Dry run:

```bash
sudo docker exec poc-kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:19092 \
  --group clickhouse-efris-esb-poc-v1 \
  --topic EAI_Efris \
  --reset-offsets --to-earliest
```

Execute:

```bash
sudo docker exec poc-kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:19092 \
  --group clickhouse-efris-esb-poc-v1 \
  --topic EAI_Efris \
  --reset-offsets --to-earliest --execute
```

Describe the group and prove its current offset equals the captured earliest offset for each partition.

**Hard gate:** if Kafka refuses to initialize/reset the new inactive group, do not create the consumer MV and do not accept a default-to-latest start. Stop and add a tested ClickHouse/librdkafka `auto.offset.reset=smallest` configuration scoped to this stream before continuing.

- [ ] **Step 5: Start background consumption**

```bash
sudo docker exec -i poc-clickhouse clickhouse-client \
  --user kjt --password "$CLICKHOUSE_PASSWORD" --multiquery \
  < clickhouse/sql/efris_esb/002_start_consumer.sql
```

- [ ] **Step 6: Watch the backlog catch up**

```bash
sudo docker exec poc-kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:19092 \
  --group clickhouse-efris-esb-poc-v1 --describe
```

Repeat until lag reaches zero or stays near zero only because new ESB events are still arriving.

- [ ] **Step 7: Prove no bootstrap history was skipped**

For each partition, verify ClickHouse contains the captured initial range. For the original one-partition topic:

```text
min(raw kafka_offset) = captured earliest
unique raw offsets below captured initial end = initial_end - initial_earliest
```

Use `uniqExact((kafka_topic,kafka_partition,kafka_offset))`; do not rely on raw `count(*)` because at-least-once redelivery can duplicate raw rows.

- [ ] **Step 8: Prove parsed reconciliation and malformed-message accounting**

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

Expected: `parsed_unique` equals unique valid raw Kafka identities; invalid raw JSON is visible rather than blocking consumption.

- [ ] **Step 9: Prove success/encrypted-content behavior**

Verify `return_code='00'` implies `is_success=1`. Confirm `efris_event` has only `content_present`, `content_bytes`, and `content_encrypted` for payload-content metadata and has no `content` or `signature` analytical column.

- [ ] **Step 10: Prove live continuation**

Record ClickHouse's current maximum Kafka offset, wait for the next real ESB event, and show the maximum advances without any batch trigger.

- [ ] **Step 11: Only after backlog proof, shorten `EAI_Efris` retention to seven days**

```bash
bash scripts/configure_efris_esb_topic.sh
```

Verify `cleanup.policy=delete`, `retention.ms=604800000`, `retention.bytes=-1`, and `segment.ms=3600000` on `EAI_Efris`. This ordering prevents a retention-policy change from deleting older currently-retained messages before the first ClickHouse catch-up.

- [ ] **Step 12: Run the consolidated verifier**

```bash
bash scripts/verify_efris_esb_stream.sh
```

Expected: healthy consumer, reconciled raw/parsed physical identities, explicit invalid-message count, seven-day raw TTL, and fresh live arrivals.

---

### Task 5: Runbook, full regression verification, and PR evidence

**Files:**
- Create: `docs/efris-esb-stream.md`
- Modify: `README.md` only to add a short runbook link if it fits the existing structure.

**Interfaces:**
- Consumes: verified runtime objects from Task 4.
- Produces: operator recovery instructions and auditable PR evidence.

- [ ] **Step 1: Document the final object map**

```text
EAI_Efris
  -> analytics.efris_esb_kafka_queue
  -> analytics.efris_esb_kafka_to_raw_mv
  -> analytics.raw_efris_esb             (7-day TTL)
  -> analytics.efris_esb_raw_to_event_mv
  -> analytics.efris_event               (long-term POC)
  -> analytics.dim_efris_interface
  -> analytics.v_efris_observed_return_codes
  -> analytics.v_efris_esb_invalid_messages
```

Document consumer group `clickhouse-efris-esb-poc-v1`, seven-day Kafka policy, at-least-once semantics, physical Kafka identity, and the no-decryption rule.

- [ ] **Step 2: Document recovery**

State explicitly:

```text
ClickHouse restart -> resume from committed group offsets.
Replay within Kafka retention -> stop/detach consumer, reset only this dedicated group while inactive, reattach.
Never reset unrelated groups.
ClickHouse outage > Kafka retention -> older topic events may no longer be recoverable from Kafka.
Raw ClickHouse payload -> expires after 7 days.
Parsed event history -> remains.
Future Hudi/HDFS -> durable raw archive if approved/required.
```

- [ ] **Step 3: Run focused and full verification**

```bash
python -m pytest -q tests/test_efris_esb_stream_contract.py
python -m pytest -q
python -m compileall -q app scripts
bash -n scripts/configure_efris_esb_topic.sh
bash -n scripts/verify_efris_esb_stream.sh
node --check app/static/js/simulator_controller.js
```

Expected: all pass.

- [ ] **Step 4: Commit the runbook**

```bash
git add docs/efris-esb-stream.md README.md
git commit -m "docs: add EFRIS ESB stream runbook"
```

- [ ] **Step 5: Record PR evidence before claiming completion**

```text
Kafka initial earliest/end offsets: captured
Consumer starts at earliest retained offsets: proven
Initial retained backlog fully present in raw: proven
Consumer lag after catch-up: zero/near-zero
Raw unique Kafka identities: N
Parsed valid unique Kafka identities: N
Invalid JSON identities: N
returnCode=00 -> is_success=1: proven
Live ESB offset advances automatically: proven
Kafka EAI_Efris retention: 7 days
ClickHouse raw TTL: 7 days
Full pytest: pass
```

Do not claim operational completion if any runtime evidence above is missing.
