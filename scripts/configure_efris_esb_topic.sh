#!/usr/bin/env bash
set -euo pipefail

KAFKA_CONTAINER="${KAFKA_CONTAINER:-poc-kafka}"
KAFKA_BOOTSTRAP="${KAFKA_BOOTSTRAP:-kafka:19092}"
EFRIS_TOPIC="${EFRIS_TOPIC:-EAI_Efris}"

sudo docker exec "$KAFKA_CONTAINER" \
  /opt/kafka/bin/kafka-configs.sh \
  --bootstrap-server "$KAFKA_BOOTSTRAP" \
  --entity-type topics \
  --entity-name "$EFRIS_TOPIC" \
  --alter \
  --add-config 'cleanup.policy=delete,retention.ms=604800000,retention.bytes=-1,segment.ms=3600000'

sudo docker exec "$KAFKA_CONTAINER" \
  /opt/kafka/bin/kafka-configs.sh \
  --bootstrap-server "$KAFKA_BOOTSTRAP" \
  --entity-type topics \
  --entity-name "$EFRIS_TOPIC" \
  --describe
