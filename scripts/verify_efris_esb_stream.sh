#!/usr/bin/env bash
set -euo pipefail

KAFKA_CONTAINER="${KAFKA_CONTAINER:-poc-kafka}"
KAFKA_BOOTSTRAP="${KAFKA_BOOTSTRAP:-kafka:19092}"
CLICKHOUSE_CONTAINER="${CLICKHOUSE_CONTAINER:-poc-clickhouse}"
EFRIS_TOPIC="${EFRIS_TOPIC:-EAI_Efris}"
EFRIS_GROUP="${EFRIS_GROUP:-clickhouse-efris-esb-poc-v1}"

ch_query() {
  local query="$1"
  sudo docker exec -e EFRIS_VERIFY_QUERY="$query" "$CLICKHOUSE_CONTAINER" \
    sh -lc 'clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query "$EFRIS_VERIFY_QUERY"'
}

echo '=== KAFKA EARLIEST RETAINED OFFSETS ==='
sudo docker exec "$KAFKA_CONTAINER" \
  /opt/kafka/bin/kafka-get-offsets.sh \
  --bootstrap-server "$KAFKA_BOOTSTRAP" \
  --topic "$EFRIS_TOPIC" \
  --time earliest

echo
echo '=== KAFKA LOG-END OFFSETS ==='
sudo docker exec "$KAFKA_CONTAINER" \
  /opt/kafka/bin/kafka-get-offsets.sh \
  --bootstrap-server "$KAFKA_BOOTSTRAP" \
  --topic "$EFRIS_TOPIC" \
  --time latest

echo
echo '=== CLICKHOUSE CONSUMER GROUP ==='
sudo docker exec "$KAFKA_CONTAINER" \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server "$KAFKA_BOOTSTRAP" \
  --describe \
  --group "$EFRIS_GROUP" || true

echo
echo '=== EFRIS CLICKHOUSE OBJECTS ==='
ch_query "SELECT name, engine FROM system.tables WHERE database='analytics' AND name IN ('efris_esb_kafka_queue','raw_efris_esb','efris_event','efris_esb_raw_to_event_mv','efris_esb_kafka_to_raw_mv','dim_efris_interface','v_efris_transactions','v_efris_success_transactions','v_efris_error_transactions','v_efris_observed_return_codes','v_efris_esb_invalid_messages') ORDER BY name FORMAT PrettyCompact"

echo
echo '=== STORAGE COUNTS ==='
ch_query "SELECT 'raw_efris_esb' AS object, count() AS rows FROM analytics.raw_efris_esb UNION ALL SELECT 'efris_event', count() FROM analytics.efris_event UNION ALL SELECT 'v_efris_transactions', count() FROM analytics.v_efris_transactions UNION ALL SELECT 'v_efris_success_transactions', count() FROM analytics.v_efris_success_transactions UNION ALL SELECT 'v_efris_error_transactions', count() FROM analytics.v_efris_error_transactions FORMAT PrettyCompact"

echo
echo '=== CLICKHOUSE OFFSET COVERAGE ==='
ch_query "SELECT kafka_partition, min(kafka_offset) AS min_offset_seen, max(kafka_offset) AS max_offset_seen, count() AS raw_rows FROM analytics.raw_efris_esb GROUP BY kafka_partition ORDER BY kafka_partition FORMAT PrettyCompact"

echo
echo '=== PARSE / LINEAGE HEALTH ==='
ch_query "SELECT count() AS parsed_rows, uniqExact((kafka_topic,kafka_partition,kafka_offset)) AS unique_kafka_records, countIf(event_id IS NULL) AS missing_event_id, countIf(interface_code='') AS missing_interface_code, countIf(return_code='') AS missing_return_code FROM analytics.efris_event FORMAT PrettyCompact"

echo
echo '=== INVALID JSON COUNT ==='
ch_query "SELECT count() AS invalid_messages FROM analytics.v_efris_esb_invalid_messages FORMAT PrettyCompact"
