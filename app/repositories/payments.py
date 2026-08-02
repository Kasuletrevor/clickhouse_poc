from __future__ import annotations

from decimal import Decimal

from app.oracle import OracleDatabase


PAYMENT_SELECT = """
SELECT
    p.PAYMENT_ID,
    p.TAXPAYER_ID,
    t.TAXPAYER_NAME,
    p.AMOUNT,
    p.STATUS,
    p.PAYMENT_TIME,
    p.UPDATED_AT,
    t.STATION_ID,
    s.STATION_NAME
FROM PAYMENT p
JOIN TAXPAYER t
  ON t.TAXPAYER_ID = p.TAXPAYER_ID
LEFT JOIN STATION s
  ON s.STATION_ID = t.STATION_ID
"""


class OraclePaymentRepository:
    def __init__(self, db: OracleDatabase):
        self.db = db

    @staticmethod
    def _row_to_payment(row):
        if row is None:
            return None
        return {
            "payment_id": row[0],
            "taxpayer_id": row[1],
            "taxpayer_name": row[2],
            "amount": row[3],
            "status": row[4],
            "payment_time": row[5],
            "updated_at": row[6],
            "station_id": row[7],
            "station_name": row[8],
        }

    def list_payments(self, search=None, status=None, limit=50, offset=0):
        predicates = []
        binds = {}

        if search:
            predicates.append("(UPPER(p.PAYMENT_ID) LIKE :search OR UPPER(p.TAXPAYER_ID) LIKE :search OR UPPER(t.TAXPAYER_NAME) LIKE :search)")
            binds["search"] = f"%{search.strip().upper()}%"
        if status:
            predicates.append("p.STATUS = :status")
            binds["status"] = status.strip().upper()

        where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
        count_sql = f"""
            SELECT COUNT(*)
            FROM PAYMENT p
            JOIN TAXPAYER t ON t.TAXPAYER_ID = p.TAXPAYER_ID
            {where}
        """
        data_sql = f"""
            {PAYMENT_SELECT}
            {where}
            ORDER BY p.PAYMENT_TIME DESC, p.PAYMENT_ID DESC
            OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
        """
        data_binds = {**binds, "offset": offset, "limit": limit}

        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, binds)
                total = int(cur.fetchone()[0])
                cur.execute(data_sql, data_binds)
                items = [self._row_to_payment(row) for row in cur.fetchall()]
        return items, total

    def payment_summary(self):
        sql = """
        SELECT
            COUNT(*) AS PAYMENTS_TODAY,
            SUM(CASE WHEN STATUS = 'SUCCESSFUL' THEN 1 ELSE 0 END) AS SUCCESSFUL,
            SUM(CASE WHEN STATUS = 'PENDING' THEN 1 ELSE 0 END) AS PENDING,
            SUM(CASE WHEN STATUS = 'REVERSED' THEN 1 ELSE 0 END) AS REVERSED,
            NVL(SUM(AMOUNT), 0) AS AMOUNT_TODAY
        FROM PAYMENT
        WHERE PAYMENT_TIME >= TRUNC(SYSTIMESTAMP)
          AND PAYMENT_TIME < TRUNC(SYSTIMESTAMP) + INTERVAL '1' DAY
        """
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
        return {
            "payments_today": int(row[0] or 0),
            "successful": int(row[1] or 0),
            "pending": int(row[2] or 0),
            "reversed": int(row[3] or 0),
            "amount_today": row[4] or Decimal("0"),
        }

    def get_payment(self, payment_id):
        sql = f"{PAYMENT_SELECT} WHERE p.PAYMENT_ID = :payment_id"
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, payment_id=payment_id)
                return self._row_to_payment(cur.fetchone())

    def taxpayer_context(self, taxpayer_id):
        sql = """
        SELECT
            t.TAXPAYER_ID,
            t.TAXPAYER_NAME,
            t.TAXPAYER_TYPE,
            t.STATION_ID,
            s.STATION_NAME
        FROM TAXPAYER t
        LEFT JOIN STATION s ON s.STATION_ID = t.STATION_ID
        WHERE t.TAXPAYER_ID = :taxpayer_id
        """
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, taxpayer_id=taxpayer_id)
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "taxpayer_id": row[0],
            "taxpayer_name": row[1],
            "taxpayer_type": row[2],
            "station_id": row[3],
            "station_name": row[4],
        }

    def payment_exists(self, payment_id):
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM PAYMENT WHERE PAYMENT_ID = :payment_id", payment_id=payment_id)
                return cur.fetchone() is not None

    def create_payment(self, payment_id, taxpayer_id, amount, status):
        sql = """
        INSERT INTO PAYMENT
            (PAYMENT_ID, TAXPAYER_ID, AMOUNT, STATUS, PAYMENT_TIME, UPDATED_AT)
        VALUES
            (:payment_id, :taxpayer_id, :amount, :status, SYSTIMESTAMP, SYSTIMESTAMP)
        """
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    payment_id=payment_id,
                    taxpayer_id=taxpayer_id,
                    amount=amount,
                    status=status,
                )
            conn.commit()
        return self.get_payment(payment_id)

    def update_status(self, payment_id, expected_status, new_status):
        sql = """
        UPDATE PAYMENT
        SET STATUS = :new_status,
            UPDATED_AT = SYSTIMESTAMP
        WHERE PAYMENT_ID = :payment_id
          AND STATUS = :expected_status
        """
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    payment_id=payment_id,
                    expected_status=expected_status,
                    new_status=new_status,
                )
                updated = cur.rowcount == 1
            if updated:
                conn.commit()
            else:
                conn.rollback()
        return updated
