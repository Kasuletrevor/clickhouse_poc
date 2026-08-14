#!/usr/bin/env bash
set -euo pipefail

CLICKHOUSE_CONTAINER="${CLICKHOUSE_CONTAINER:-poc-clickhouse}"
CONFIG_FILE="${CONFIG_FILE:-clickhouse/config.d/efris_kafka_earliest.xml}"
TARGET_FILE="/etc/clickhouse-server/config.d/efris_kafka_earliest.xml"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing $CONFIG_FILE" >&2
  exit 1
fi

echo 'Installing topic-scoped initial-offset configuration for EAI_Efris...'
sudo docker cp "$CONFIG_FILE" "$CLICKHOUSE_CONTAINER:$TARGET_FILE"

echo 'Restarting ClickHouse so the Kafka consumer configuration is loaded...'
sudo docker restart "$CLICKHOUSE_CONTAINER" >/dev/null

echo 'Waiting for ClickHouse...'
for _ in $(seq 1 60); do
  if sudo docker exec "$CLICKHOUSE_CONTAINER" sh -lc \
    'clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query "SELECT 1"' \
    >/dev/null 2>&1; then
    echo 'ClickHouse is ready.'
    exit 0
  fi
  sleep 2
done

echo 'ClickHouse did not become ready within 120 seconds.' >&2
exit 1
