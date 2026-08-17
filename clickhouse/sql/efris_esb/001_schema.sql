CREATE DATABASE IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.raw_efris_esb
(
    payload String,
    kafka_topic LowCardinality(String),
    kafka_partition UInt64,
    kafka_offset UInt64,
    kafka_timestamp Nullable(DateTime64(3)),
    ingested_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(ingested_at)
ORDER BY (kafka_topic, kafka_partition, kafka_offset, ingested_at)
TTL ingested_at + INTERVAL 7 DAY DELETE;

CREATE TABLE IF NOT EXISTS analytics.efris_event
(
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
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(
    coalesce(
        event_time,
        toDateTime64('1970-01-01 00:00:00', 3, 'Africa/Kampala')
    )
)
ORDER BY (kafka_topic, kafka_partition, kafka_offset);

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

CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.efris_esb_raw_to_event_mv
TO analytics.efris_event
AS
WITH
    JSONExtractString(payload, 'globalInfo', 'dataExchangeId') AS event_id_raw,
    JSONExtractString(payload, 'globalInfo', 'requestTime') AS event_time_raw,
    JSONExtractString(payload, 'globalInfo', 'interfaceCode') AS interface_code_raw,
    JSONExtractString(payload, 'globalInfo', 'tin') AS tin_raw,
    JSONExtractString(payload, 'globalInfo', 'taxpayerID') AS taxpayer_id_raw,
    JSONExtractString(payload, 'globalInfo', 'legalName') AS legal_name_raw,
    JSONExtractString(payload, 'globalInfo', 'taxpayerUserId') AS taxpayer_user_id_raw,
    JSONExtractString(payload, 'globalInfo', 'deviceNo') AS device_no_raw,
    JSONExtractString(payload, 'globalInfo', 'appId') AS app_id_raw,
    JSONExtractString(payload, 'globalInfo', 'version') AS version_raw,
    JSONExtractString(payload, 'returnStateInfo', 'returnCode') AS return_code_raw,
    JSONExtractString(payload, 'returnStateInfo', 'returnMessage') AS return_message_raw,
    JSONExtractString(payload, 'data', 'content') AS content_raw,
    JSONExtractString(payload, 'data', 'dataDescription', 'encryptCode') AS encrypt_code_raw
SELECT
    nullIf(event_id_raw, '') AS event_id,
    parseDateTime64BestEffortOrNull(event_time_raw, 3, 'Africa/Kampala') AS event_time,
    interface_code_raw AS interface_code,
    nullIf(tin_raw, '') AS tin,
    nullIf(taxpayer_id_raw, '') AS taxpayer_id,
    nullIf(legal_name_raw, '') AS legal_name,
    nullIf(taxpayer_user_id_raw, '') AS taxpayer_user_id,
    nullIf(device_no_raw, '') AS device_no,
    return_code_raw AS return_code,
    return_message_raw AS return_message,
    trimBoth(replaceRegexpOne(return_message_raw, '(?s)\\s*\\(TIN:.*$', '')) AS normalized_return_message,
    toUInt8(return_code_raw = '00') AS is_success,
    nullIf(app_id_raw, '') AS app_id,
    nullIf(version_raw, '') AS version,
    toUInt8(notEmpty(content_raw)) AS content_present,
    length(content_raw) AS content_bytes,
    toUInt8(encrypt_code_raw = '1') AS content_encrypted,
    kafka_topic,
    kafka_partition,
    kafka_offset,
    kafka_timestamp,
    ingested_at
FROM analytics.raw_efris_esb
WHERE isValidJSON(payload);

CREATE TABLE IF NOT EXISTS analytics.dim_efris_interface
(
    interface_code String,
    interface_name String
)
ENGINE = ReplacingMergeTree
ORDER BY interface_code;

INSERT INTO analytics.dim_efris_interface
SELECT
    tupleElement(item, 1) AS interface_code,
    tupleElement(item, 2) AS interface_name
FROM
(
    SELECT arrayJoin([
        ('T104', 'Get symmetric key'),
        ('T106', 'Invoice / receipt query'),
        ('T108', 'Invoice details'),
        ('T109', 'Billing upload'),
        ('T110', 'Credit application'),
        ('T111', 'Credit note application status query'),
        ('T113', 'Credit note application detail'),
        ('T114', 'Cancel approved credit / debit note'),
        ('T115', 'System dictionary update'),
        ('T118', 'Credit note application / cancellation details'),
        ('T119', 'Query taxpayer information by TIN'),
        ('T124', 'Query commodity category'),
        ('T125', 'Query excise duty'),
        ('T126', 'Get all exchange rates'),
        ('T127', 'Goods / services inquiry'),
        ('T128', 'Query stock quantity'),
        ('T129', 'Batch invoice upload'),
        ('T130', 'Goods upload'),
        ('T131', 'Goods stock maintain'),
        ('T137', 'Check taxpayer type / special VAT treatment'),
        ('T138', 'Get all branches'),
        ('T139', 'Goods stock transfer')
    ]) AS item
)
WHERE tupleElement(item, 1) NOT IN
(
    SELECT interface_code
    FROM analytics.dim_efris_interface
);

-- Recreate business views so re-applying this schema also repairs existing deployments.
-- Keep FINAL inside subqueries and apply success/error filtering before the LEFT JOIN.
DROP VIEW IF EXISTS analytics.v_efris_success_transactions;
DROP VIEW IF EXISTS analytics.v_efris_error_transactions;
DROP VIEW IF EXISTS analytics.v_efris_transactions;

CREATE VIEW analytics.v_efris_transactions AS
SELECT
    e.event_id,
    e.event_time,
    e.interface_code,
    d.interface_name,
    e.tin,
    e.taxpayer_id,
    e.legal_name,
    e.taxpayer_user_id,
    e.device_no,
    e.return_code,
    e.return_message,
    e.normalized_return_message,
    e.is_success,
    e.app_id,
    e.version,
    e.content_present,
    e.content_bytes,
    e.content_encrypted,
    e.kafka_topic,
    e.kafka_partition,
    e.kafka_offset,
    e.kafka_timestamp,
    e.ingested_at
FROM
(
    SELECT
        event_id,
        event_time,
        interface_code,
        tin,
        taxpayer_id,
        legal_name,
        taxpayer_user_id,
        device_no,
        return_code,
        return_message,
        normalized_return_message,
        is_success,
        app_id,
        version,
        content_present,
        content_bytes,
        content_encrypted,
        kafka_topic,
        kafka_partition,
        kafka_offset,
        kafka_timestamp,
        ingested_at
    FROM analytics.efris_event FINAL
) AS e
LEFT JOIN
(
    SELECT
        interface_code,
        interface_name
    FROM analytics.dim_efris_interface FINAL
) AS d
    ON e.interface_code = d.interface_code;

CREATE VIEW analytics.v_efris_success_transactions AS
SELECT
    e.event_id,
    e.event_time,
    e.interface_code,
    d.interface_name,
    e.tin,
    e.taxpayer_id,
    e.legal_name,
    e.taxpayer_user_id,
    e.device_no,
    e.return_code,
    e.return_message,
    e.normalized_return_message,
    e.is_success,
    e.app_id,
    e.version,
    e.content_present,
    e.content_bytes,
    e.content_encrypted,
    e.kafka_topic,
    e.kafka_partition,
    e.kafka_offset,
    e.kafka_timestamp,
    e.ingested_at
FROM
(
    SELECT
        event_id,
        event_time,
        interface_code,
        tin,
        taxpayer_id,
        legal_name,
        taxpayer_user_id,
        device_no,
        return_code,
        return_message,
        normalized_return_message,
        is_success,
        app_id,
        version,
        content_present,
        content_bytes,
        content_encrypted,
        kafka_topic,
        kafka_partition,
        kafka_offset,
        kafka_timestamp,
        ingested_at
    FROM analytics.efris_event FINAL
    WHERE is_success = 1
) AS e
LEFT JOIN
(
    SELECT
        interface_code,
        interface_name
    FROM analytics.dim_efris_interface FINAL
) AS d
    ON e.interface_code = d.interface_code;

CREATE VIEW analytics.v_efris_error_transactions AS
SELECT
    e.event_id,
    e.event_time,
    e.interface_code,
    d.interface_name,
    e.tin,
    e.taxpayer_id,
    e.legal_name,
    e.taxpayer_user_id,
    e.device_no,
    e.return_code,
    e.return_message,
    e.normalized_return_message,
    e.is_success,
    e.app_id,
    e.version,
    e.content_present,
    e.content_bytes,
    e.content_encrypted,
    e.kafka_topic,
    e.kafka_partition,
    e.kafka_offset,
    e.kafka_timestamp,
    e.ingested_at
FROM
(
    SELECT
        event_id,
        event_time,
        interface_code,
        tin,
        taxpayer_id,
        legal_name,
        taxpayer_user_id,
        device_no,
        return_code,
        return_message,
        normalized_return_message,
        is_success,
        app_id,
        version,
        content_present,
        content_bytes,
        content_encrypted,
        kafka_topic,
        kafka_partition,
        kafka_offset,
        kafka_timestamp,
        ingested_at
    FROM analytics.efris_event FINAL
    WHERE is_success = 0
) AS e
LEFT JOIN
(
    SELECT
        interface_code,
        interface_name
    FROM analytics.dim_efris_interface FINAL
) AS d
    ON e.interface_code = d.interface_code;

CREATE VIEW IF NOT EXISTS analytics.v_efris_esb_invalid_messages AS
SELECT
    payload,
    kafka_topic,
    kafka_partition,
    kafka_offset,
    kafka_timestamp,
    ingested_at
FROM analytics.raw_efris_esb
WHERE NOT isValidJSON(payload);

CREATE VIEW IF NOT EXISTS analytics.v_efris_observed_return_codes AS
SELECT
    interface_code,
    return_code,
    normalized_return_message,
    min(event_time) AS first_seen,
    max(event_time) AS last_seen,
    count() AS event_count,
    uniqExactIf(tin, isNotNull(tin)) AS distinct_taxpayers,
    uniqExactIf(device_no, isNotNull(device_no)) AS distinct_devices,
    toUInt8(return_code = '00') AS is_success
FROM analytics.efris_event FINAL
GROUP BY
    interface_code,
    return_code,
    normalized_return_message;
