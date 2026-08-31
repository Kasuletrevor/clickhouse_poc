from __future__ import annotations

from datetime import datetime


def _clickhouse_datetime(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%Y-%m-%d %H:%M:%S.%f")


class StreamingPocRepository:
    def __init__(self, clickhouse_db):
        self.clickhouse_db = clickhouse_db

    def arrival_summary(self, started_at: str | None) -> dict:
        if not started_at:
            return {"received": 0, "payments": 0, "taxpayer_changes": 0}
        since = _clickhouse_datetime(started_at)
        rows = self.clickhouse_db.query(f"""
            SELECT
                sum(events) AS received,
                sumIf(events, entity = 'PAYMENT') AS payments,
                sumIf(events, entity = 'TAXPAYER') AS taxpayer_changes
            FROM
            (
                SELECT 'PAYMENT' AS entity, count() AS events
                FROM analytics.raw_oracle_payment_cdc
                WHERE ingested_at >= parseDateTime64BestEffort('{since}')

                UNION ALL

                SELECT 'TAXPAYER' AS entity, count() AS events
                FROM analytics.raw_oracle_taxpayer_cdc
                WHERE ingested_at >= parseDateTime64BestEffort('{since}')
            )
        """)
        if not rows:
            return {"received": 0, "payments": 0, "taxpayer_changes": 0}
        row = rows[0]
        return {
            "received": int(row.get("received") or 0),
            "payments": int(row.get("payments") or 0),
            "taxpayer_changes": int(row.get("taxpayer_changes") or 0),
        }

    def recent_events(self, started_at: str | None, limit: int = 40) -> list[dict]:
        if not started_at:
            return []
        since = _clickhouse_datetime(started_at)
        limit = max(1, min(int(limit), 100))
        return self.clickhouse_db.query(f"""
            SELECT
                event_type,
                action,
                entity_id,
                taxpayer_id,
                detail,
                source_commit_time,
                ingested_at,
                kafka_partition,
                kafka_offset,
                if(source_commit_time IS NULL, NULL,
                   dateDiff('millisecond', source_commit_time, ingested_at)) AS cdc_latency_ms
            FROM
            (
                SELECT
                    'PAYMENT' AS event_type,
                    multiIf(dbz_op = 'c', 'CREATED', dbz_op = 'u', 'UPDATED', dbz_op = 'd', 'DELETED', upper(ifNull(dbz_op, 'EVENT'))) AS action,
                    ifNull(payment_id, '') AS entity_id,
                    ifNull(taxpayer_id, '') AS taxpayer_id,
                    concat('UGX ', toString(ifNull(amount, 0)), ' · ', ifNull(status, '')) AS detail,
                    source_commit_time,
                    ingested_at,
                    kafka_partition,
                    kafka_offset
                FROM analytics.raw_oracle_payment_cdc
                WHERE ingested_at >= parseDateTime64BestEffort('{since}')

                UNION ALL

                SELECT
                    'TAXPAYER' AS event_type,
                    multiIf(dbz_op = 'c', 'CREATED', dbz_op = 'u', 'UPDATED', dbz_op = 'd', 'DELETED', upper(ifNull(dbz_op, 'EVENT'))) AS action,
                    ifNull(taxpayer_id, '') AS entity_id,
                    ifNull(taxpayer_id, '') AS taxpayer_id,
                    concat('Station ', ifNull(station_id, '—')) AS detail,
                    source_commit_time,
                    ingested_at,
                    kafka_partition,
                    kafka_offset
                FROM analytics.raw_oracle_taxpayer_cdc
                WHERE ingested_at >= parseDateTime64BestEffort('{since}')
            )
            ORDER BY ingested_at DESC
            LIMIT {limit}
        """)
