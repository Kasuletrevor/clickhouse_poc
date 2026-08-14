# EFRIS ESB Streaming Ingestion Design

## Goal

Build the real EFRIS streaming path from the ESB-created Kafka topic `EAI_Efris` into ClickHouse so the POC can analyze existing retained messages and continue consuming live traffic.

The first production-like use case is real-time EFRIS operational intelligence: interface activity, success/failure, taxpayer/device impact, observed return codes, retries, anomalies, and incident visibility. The encrypted business `data.content` is not decrypted in this phase.

## Scope

In scope:

- Consume all retained `EAI_Efris` messages from the earliest available offset, then continue live.
- Preserve the original Kafka message in a raw ClickHouse table for 7 days.
- Parse a narrow analytical event table for long-term POC analysis.
- Preserve Kafka partition/offset/timestamp metadata for traceability.
- Derive success using `returnCode = '00'`.
- Derive content-presence/size/encryption metadata without copying encrypted content into the analytical table.
- Build an interface dictionary and an observed return-code view/dictionary.
- Keep malformed or variant payloads from stopping ingestion.
- Configure `EAI_Efris` Kafka event retention to 7 days at the topic level.

Out of scope:

- Decrypting `data.content` or handling private keys/AES keys.
- Deep invoice/item/tax analytics from the encrypted payload.
- Replacing Kafka with Spark or adding Hudi/HDFS in this phase.
- Applying the EFRIS retention policy globally to Kafka internal or Debezium topics.
- Production HA, multi-broker replication, or enterprise TLS/SASL hardening.

## Recommended Architecture

```text
EFRIS response
    ↓
ESB
    ↓
Kafka topic: EAI_Efris
    ↓  new ClickHouse consumer group, earliest retained offset
ClickHouse Kafka Engine
    ↓
raw_efris_esb              TTL 7 days
    ↓ materialized parsing
analytics.efris_event       long-term POC analytics
    ├── dim_efris_interface
    └── observed return-code view
```

The Kafka Engine approach is preferred over a custom Python consumer because it removes an unnecessary service and lets Kafka remain the replay/buffering layer. Spark Structured Streaming remains a later lake-integration option rather than part of this first real-time POC.

## Kafka Topic Policy

Apply the following only to `EAI_Efris`:

- `cleanup.policy=delete`
- `retention.ms=604800000` (7 days)
- `retention.bytes=-1` so a size cap does not shorten the time window
- hourly log-segment rolling is preferred so retention cleanup can happen with useful granularity

Do not apply this business-event retention policy to Kafka internal topics, Kafka Connect state topics, or Debezium schema-history topics.

The ClickHouse consumer group must be new so it has no committed offsets. Its first start must use the earliest available retained offset. Once caught up, committed offsets allow normal restart/resume behavior.

The design must work with the topic's current partition count. ClickHouse consumer parallelism must never exceed the number of Kafka partitions. If `EAI_Efris` is later increased to three partitions, the ClickHouse consumer count can be increased to three.

## Raw Table

`raw_efris_esb` stores the message exactly once and keeps it for seven days.

Required fields:

- raw JSON payload
- Kafka topic
- Kafka partition
- Kafka offset
- Kafka timestamp
- ClickHouse ingestion timestamp

The raw table is the short replay/investigation buffer inside ClickHouse. The analytical table must not duplicate the encrypted `data.content`.

## Analytical Event Grain

One row in `efris_event` represents one EFRIS API response observed at the ESB.

Primary event identity is `globalInfo.dataExchangeId` when present. Kafka `(topic, partition, offset)` remains the physical ingestion identity and traceability fallback.

Keep only the fields that answer who, what interface, when, and what happened:

- `event_id` ← `globalInfo.dataExchangeId`
- `event_time` ← `globalInfo.requestTime`
- `interface_code`
- `tin`
- `taxpayer_id`
- `legal_name` nullable
- `taxpayer_user_id` nullable
- `device_no`
- `return_code`
- `return_message`
- `is_success` ← `return_code = '00'`
- `app_id`
- `version`
- `content_present`
- `content_bytes`
- `content_encrypted` ← `dataDescription.encryptCode = '1'`
- Kafka partition
- Kafka offset
- Kafka timestamp
- ClickHouse ingestion timestamp

Do not promote low-value/default fields such as `agentType`, `brn`, `deviceMAC`, latitude/longitude, `requestCode`, `responseCode`, `userName`, signature, `codeType`, `zipCode`, or interface-specific `extendField` members into first-class analytical columns yet. They remain recoverable from the seven-day raw JSON.

## Encrypted Content Handling

Successful responses may carry a Base64-encoded encrypted `data.content`. The POC must not decrypt it, log decrypted secrets, or persist extracted key material.

The analytical table records only:

- whether content exists
- its encoded byte/character length
- whether the envelope marks it as encrypted

This enables response-integrity checks such as success-with-content versus success-with-missing-content without increasing the sensitive-data surface.

## Interface Dictionary

Maintain a small `dim_efris_interface` mapping for documented interface codes used in analysis. Initial mappings may include documented codes such as T104, T109, T115, T119, T124, T125, T126, T127, T128, T129, T130, T131, T137, T138, T139, T106, T108, T110, T113, T114, and T118.

Unknown interface codes must remain visible as their raw code and must not break parsing.

## Observed Return-Code Dictionary

Do not wait for a complete official return-code catalogue before analyzing the stream.

Create an observed return-code view keyed initially by:

```text
(interface_code, return_code)
```

Expose:

- interface code
- return code
- observed/normalized message
- first seen
- last seen
- event count
- distinct affected taxpayers
- distinct affected devices
- success flag

Use the interface together with the return code rather than assuming the same numeric code always means the same thing across every EFRIS interface.

Normalize parameterized return messages for grouping while retaining the original message in `efris_event`. For example, a message containing a specific TIN, device number, interface code, or IP should group under its stable semantic message rather than fragment into a separate error for every taxpayer/device.

## Failure Tolerance

The live pipeline must favor continuity over strict rejection.

- Missing optional JSON fields become null/default analytical values.
- New `extendField` structures are ignored by the narrow parser and remain in raw JSON.
- Unknown interface or return codes remain queryable.
- Malformed messages must be observable/quarantined rather than permanently blocking the Kafka consumer.
- Parsing failures must retain enough Kafka metadata to identify the offending topic/partition/offset and raw message during the seven-day window.

Implementation will verify the exact ClickHouse Kafka error-handling settings supported by the deployed ClickHouse version before applying them.

## Retention

- Kafka `EAI_Efris`: 7 days.
- ClickHouse `raw_efris_esb`: TTL 7 days.
- ClickHouse `efris_event`: no short POC TTL; keep for long-term analytical history. A formal production retention period must be agreed before production deployment because the parsed table still contains taxpayer/device identifiers.
- Future Hudi/HDFS: intended long-term raw/archive layer if required.

## Initial Analytical Outcomes

The model must immediately support:

- total events and events/sec
- success/failure counts and rates
- interface activity and interface success rate
- distinct taxpayers/devices and affected taxpayers/devices
- top return codes/messages
- first-seen/new return codes
- repeated failures and retry patterns
- time-series failure spikes
- interface-specific anomaly detection
- current Kafka-to-ClickHouse ingestion freshness using event/Kafka/ingestion timestamps where valid

## Verification Criteria

The implementation is successful when:

1. A new ClickHouse consumer reads the earliest retained `EAI_Efris` offsets rather than starting only at new traffic.
2. It catches up to the current Kafka end offsets and then continues live.
3. Raw row count and parsed row count reconcile for valid parseable messages, with any rejected/malformed messages explicitly accounted for.
4. Known success events produce `is_success = 1` for `returnCode = '00'`.
5. Failure events with empty content still parse correctly.
6. Success events with encrypted content store content presence/size/encryption metadata but do not duplicate encrypted content into `efris_event`.
7. Missing optional fields such as `legalName` or `taxpayerUserId` do not stop ingestion.
8. Kafka partition/offset metadata is queryable in ClickHouse.
9. The raw ClickHouse table has a seven-day TTL.
10. `EAI_Efris` has topic-level seven-day retention without changing Kafka internal/Debezium topic policies.
11. After catch-up, a newly produced ESB message becomes visible in `efris_event` without a manual batch job.

## Future Extension

When approved decrypted transaction content becomes available, add a deeper transaction/detail fact keyed or correlated through the existing event identity. The envelope event table remains the operational streaming fact; the POC pipeline does not need to be redesigned.
