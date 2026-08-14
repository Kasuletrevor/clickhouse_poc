#!/usr/bin/env bash
set -euo pipefail

CLICKHOUSE_CONTAINER="${CLICKHOUSE_CONTAINER:-poc-clickhouse}"
SQL_FILE="${SQL_FILE:-clickhouse/sql/efris_esb/001_schema.sql}"

if [[ ! -f "$SQL_FILE" ]]; then
  echo "Missing $SQL_FILE" >&2
  exit 1
fi

sudo docker exec -i "$CLICKHOUSE_CONTAINER" sh -lc \
  'clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --multiquery' \
  < "$SQL_FILE"

echo 'EFRIS ESB storage, parser, dimension and business views are installed.'
