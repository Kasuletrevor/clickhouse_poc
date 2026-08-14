#!/usr/bin/env bash
set -euo pipefail

KAFKA_CONTAINER="${KAFKA_CONTAINER:-poc-kafka}"
KAFKA_BOOTSTRAP="${KAFKA_BOOTSTRAP:-kafka:19092}"
EFRIS_TOPIC="${EFRIS_TOPIC:-EAI_Efris}"
EFRIS_GROUP="${EFRIS_GROUP:-clickhouse-efris-esb-poc-v1}"

echo 'No ClickHouse server configuration or restart is required.'
echo 'Checking retained topic offsets before the new ClickHouse consumer is attached...'

echo
echo '=== KAFKA RETAINED OFFSETS ==='
sudo docker exec "$KAFKA_CONTAINER" \
  /opt/kafka/bin/kafka-get-offsets.sh \
  --bootstrap-server "$KAFKA_BOOTSTRAP" \
  --topic "$EFRIS_TOPIC" \
  --time earliest

sudo docker exec "$KAFKA_CONTAINER" \
  /opt/kafka/bin/kafka-get-offsets.sh \
  --bootstrap-server "$KAFKA_BOOTSTRAP" \
  --topic "$EFRIS_TOPIC" \
  --time latest

echo
echo '=== EXISTING CONSUMER GROUP CHECK ==='
if sudo docker exec "$KAFKA_CONTAINER" \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server "$KAFKA_BOOTSTRAP" \
  --describe \
  --group "$EFRIS_GROUP"; then
  echo
  echo "Consumer group $EFRIS_GROUP already exists. Do not attach the consumer until its offsets are reviewed."
  exit 2
else
  echo
  echo "Consumer group $EFRIS_GROUP is not present yet, as expected for first start."
  echo 'Proceed with scripts/start_efris_esb_consumer.sh; no ClickHouse restart is needed.'
fi
