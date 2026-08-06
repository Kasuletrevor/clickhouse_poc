from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from datetime import datetime

from app.clickhouse import AnalyticsOperationError, AnalyticsUnavailableError
from app.oracle import SourceOperationError, SourceUnavailableError

_PREFIX_RE = re.compile(r"^S[0-9A-Z]+$")


def _validated_prefix(source_prefix: str) -> str:
    if not _PREFIX_RE.fullmatch(source_prefix):
        raise ValueError("Invalid simulator source prefix")
    return source_prefix


def _dt_iso(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class SimulatorRepository:
    def __init__(self, oracle_db, clickhouse_db, settings):
        self.oracle_db = oracle_db
        self.clickhouse_db = clickhouse_db
        self.settings = settings

    def oracle_run_summary(self, source_prefix: str) -> dict:
        sql = """
            SELECT
                COUNT(*) AS ERROR_EVENTS,
                COUNT(DISTINCT TIN || CHR(31) || SELLER_REFERENCE_NO) AS AFFECTED_INVOICES,
                COUNT(DISTINCT TIN) AS TAXPAYERS,
                COUNT(DISTINCT DEVICE_NO) AS DEVICES,
                COUNT(DISTINCT RETURN_CODE) AS ERROR_CODES,
                MIN(CREATE_DATE) AS FIRST_EVENT_TIME,
                MAX(CREATE_DATE) AS LAST_EVENT_TIME
            FROM T_INVOICE_ERROR_LOG
            WHERE ID LIKE :prefix
        """
        with self.oracle_db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, prefix=f"{_validated_prefix(source_prefix)}-%")
                row = cursor.fetchone()
        return {
            "oracle_committed": int(row[0] or 0),
            "affected_invoices": int(row[1] or 0),
            "taxpayers": int(row[2] or 0),
            "devices": int(row[3] or 0),
            "error_codes": int(row[4] or 0),
            "first_event_time": _dt_iso(row[5]),
            "last_event_time": _dt_iso(row[6]),
        }

    def clickhouse_run_summary(self, source_prefix: str) -> dict:
        prefix = _validated_prefix(source_prefix)
        rows = self.clickhouse_db.query(f"""
            SELECT
                count() AS clickhouse_received,
                uniqExact(tuple(tin, seller_reference_no)) AS affected_invoices,
                count() - uniqExact(tuple(tin, seller_reference_no)) AS retry_events,
                uniqExact(tin) AS taxpayers,
                uniqExact(device_no) AS devices,
                uniqExact(return_code) AS error_codes,
                round(avg(dateDiff('millisecond', source_commit_ts, ingested_at)), 2) AS avg_ms,
                quantileExact(0.50)(dateDiff('millisecond', source_commit_ts, ingested_at)) AS p50_ms,
                quantileExact(0.95)(dateDiff('millisecond', source_commit_ts, ingested_at)) AS p95_ms,
                quantileExact(0.99)(dateDiff('millisecond', source_commit_ts, ingested_at)) AS p99_ms,
                max(dateDiff('millisecond', source_commit_ts, ingested_at)) AS max_ms
            FROM analytics.raw_efris_error_log
            WHERE startsWith(ifNull(id, ''), '{prefix}-')
        """)
        if not rows:
            return self._empty_clickhouse_summary()
        row = rows[0]
        return {
            "clickhouse_received": int(row.get("clickhouse_received") or 0),
            "affected_invoices": int(row.get("affected_invoices") or 0),
            "retry_events": int(row.get("retry_events") or 0),
            "taxpayers": int(row.get("taxpayers") or 0),
            "devices": int(row.get("devices") or 0),
            "error_codes": int(row.get("error_codes") or 0),
            "avg_ms": float(row["avg_ms"]) if row.get("avg_ms") is not None else None,
            "p50_ms": int(row["p50_ms"]) if row.get("p50_ms") is not None else None,
            "p95_ms": int(row["p95_ms"]) if row.get("p95_ms") is not None else None,
            "p99_ms": int(row["p99_ms"]) if row.get("p99_ms") is not None else None,
            "max_ms": int(row["max_ms"]) if row.get("max_ms") is not None else None,
        }

    @staticmethod
    def _empty_clickhouse_summary():
        return {
            "clickhouse_received": 0,
            "affected_invoices": 0,
            "retry_events": 0,
            "taxpayers": 0,
            "devices": 0,
            "error_codes": 0,
            "avg_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
            "max_ms": None,
        }

    def arrival_throughput(self, source_prefix: str) -> list[dict]:
        prefix = _validated_prefix(source_prefix)
        return self.clickhouse_db.query(f"""
            SELECT
                toStartOfInterval(ingested_at, INTERVAL 5 SECOND) AS bucket,
                count() AS arrived,
                round(avg(dateDiff('millisecond', source_commit_ts, ingested_at)), 0) AS avg_latency_ms
            FROM analytics.raw_efris_error_log
            WHERE startsWith(ifNull(id, ''), '{prefix}-')
            GROUP BY bucket
            ORDER BY bucket DESC
            LIMIT 120
        """)[::-1]

    def _oracle_recent(self, source_prefix: str, limit: int) -> list[dict]:
        sql = f"""
            SELECT ERROR_EVENT_ID, ID, TIN, DEVICE_NO, SELLER_REFERENCE_NO,
                   RETURN_CODE, RETURN_MSG, CREATE_DATE
            FROM T_INVOICE_ERROR_LOG
            WHERE ID LIKE :prefix
            ORDER BY ERROR_EVENT_ID DESC
            FETCH FIRST {int(limit)} ROWS ONLY
        """
        rows = []
        with self.oracle_db.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, prefix=f"{_validated_prefix(source_prefix)}-%")
                for row in cursor.fetchall():
                    source_id = row[1]
                    try:
                        sequence = int(str(source_id).rsplit("-", 1)[-1])
                    except (TypeError, ValueError):
                        sequence = None
                    rows.append({
                        "error_event_id": int(row[0]),
                        "source_id": source_id,
                        "sequence": sequence,
                        "tin": row[2],
                        "device_no": row[3],
                        "seller_reference_no": row[4],
                        "return_code": row[5],
                        "return_msg": row[6],
                        "create_date": _dt_iso(row[7]),
                        "oracle_committed": True,
                        "clickhouse_received": False,
                        "cdc_latency_ms": None,
                        "source_commit_ts": None,
                        "ingested_at": None,
                        "source_scn": None,
                        "source_commit_scn": None,
                        "kafka_partition": None,
                        "kafka_offset": None,
                    })
        return rows

    def recent_events(self, source_prefix: str, limit: int = 40) -> list[dict]:
        limit = max(1, min(int(limit), 100))
        oracle_rows = self._oracle_recent(source_prefix, limit)
        if not oracle_rows:
            return []
        prefix = _validated_prefix(source_prefix)
        ch_rows = self.clickhouse_db.query(f"""
            SELECT id, source_commit_ts, ingested_at, source_scn, source_commit_scn,
                   kafka_partition, kafka_offset,
                   dateDiff('millisecond', source_commit_ts, ingested_at) AS cdc_latency_ms
            FROM analytics.raw_efris_error_log
            WHERE startsWith(ifNull(id, ''), '{prefix}-')
            ORDER BY error_event_id DESC
            LIMIT {limit}
        """)
        by_id = {row.get("id"): row for row in ch_rows}
        for event in oracle_rows:
            arrived = by_id.get(event["source_id"])
            if not arrived:
                continue
            event.update({
                "clickhouse_received": True,
                "cdc_latency_ms": int(arrived["cdc_latency_ms"]) if arrived.get("cdc_latency_ms") is not None else None,
                "source_commit_ts": arrived.get("source_commit_ts"),
                "ingested_at": arrived.get("ingested_at"),
                "source_scn": arrived.get("source_scn"),
                "source_commit_scn": arrived.get("source_commit_scn"),
                "kafka_partition": arrived.get("kafka_partition"),
                "kafka_offset": arrived.get("kafka_offset"),
            })
        return oracle_rows

    def _oracle_health(self):
        try:
            with self.oracle_db.connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM DUAL")
                    cursor.fetchone()
            return {"status": "healthy", "detail": "Source reachable"}
        except Exception:
            return {"status": "unavailable", "detail": "Source unavailable"}

    def _debezium_health(self):
        url = f"{self.settings.debezium_url.rstrip('/')}/connectors/{self.settings.debezium_flat_connector}/status"
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            connector = str(payload.get("connector", {}).get("state", "UNKNOWN")).upper()
            tasks = payload.get("tasks") or []
            task_states = [str(task.get("state", "UNKNOWN")).upper() for task in tasks]
            if connector == "RUNNING" and task_states and all(state == "RUNNING" for state in task_states):
                return {"status": "healthy", "detail": "Connector and task RUNNING"}
            return {"status": "degraded", "detail": f"Connector {connector}; task {','.join(task_states) or 'UNKNOWN'}"}
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
            return {"status": "unavailable", "detail": "Kafka Connect status unavailable"}

    def _kafka_health(self):
        target = str(self.settings.kafka_bootstrap).split(",", 1)[0].strip()
        try:
            host, port_text = target.rsplit(":", 1)
            with socket.create_connection((host, int(port_text)), timeout=1.0):
                pass
            return {"status": "healthy", "detail": "Broker reachable"}
        except (ValueError, OSError):
            return {"status": "unavailable", "detail": "Broker unreachable"}

    def _clickhouse_health(self):
        try:
            self.clickhouse_db.query("SELECT 1 AS ok")
            return {"status": "healthy", "detail": "Analytics reachable"}
        except Exception:
            return {"status": "unavailable", "detail": "Analytics unavailable"}

    def pipeline_health(self) -> dict:
        return {
            "oracle": self._oracle_health(),
            "debezium": self._debezium_health(),
            "kafka": self._kafka_health(),
            "clickhouse": self._clickhouse_health(),
        }
