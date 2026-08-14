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
