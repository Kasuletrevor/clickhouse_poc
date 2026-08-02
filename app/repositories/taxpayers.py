from app.oracle import OracleDatabase


TAXPAYER_SELECT = """
SELECT
    t.TAXPAYER_ID,
    t.TAXPAYER_NAME,
    t.TAXPAYER_TYPE,
    t.STATION_ID,
    s.STATION_NAME,
    t.UPDATED_AT
FROM TAXPAYER t
LEFT JOIN STATION s
  ON s.STATION_ID = t.STATION_ID
"""


class OracleTaxpayerRepository:
    def __init__(self, db: OracleDatabase):
        self.db = db

    @staticmethod
    def _row_to_taxpayer(row):
        if row is None:
            return None
        return {
            "taxpayer_id": row[0],
            "taxpayer_name": row[1],
            "taxpayer_type": row[2],
            "station_id": row[3],
            "station_name": row[4],
            "updated_at": row[5],
        }

    def list_taxpayers(self, search=None, taxpayer_type=None, station_id=None, limit=50, offset=0):
        predicates = []
        binds = {}

        if search:
            predicates.append(
                "(UPPER(t.TAXPAYER_ID) LIKE :search OR UPPER(t.TAXPAYER_NAME) LIKE :search)"
            )
            binds["search"] = f"%{search.strip().upper()}%"
        if taxpayer_type:
            predicates.append("UPPER(t.TAXPAYER_TYPE) = :taxpayer_type")
            binds["taxpayer_type"] = taxpayer_type.strip().upper()
        if station_id:
            predicates.append("t.STATION_ID = :station_id")
            binds["station_id"] = station_id.strip().upper()

        where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
        count_sql = f"SELECT COUNT(*) FROM TAXPAYER t {where}"
        data_sql = f"""
            {TAXPAYER_SELECT}
            {where}
            ORDER BY t.TAXPAYER_NAME, t.TAXPAYER_ID
            OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
        """
        data_binds = {**binds, "offset": offset, "limit": limit}

        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, binds)
                total = int(cur.fetchone()[0])
                cur.execute(data_sql, data_binds)
                items = [self._row_to_taxpayer(row) for row in cur.fetchall()]
        return items, total

    def taxpayer_summary(self):
        sql = """
        SELECT
            COUNT(*) AS TOTAL_TAXPAYERS,
            SUM(CASE WHEN UPPER(TAXPAYER_TYPE) = 'COMPANY' THEN 1 ELSE 0 END) AS COMPANY_COUNT,
            SUM(CASE WHEN UPPER(TAXPAYER_TYPE) <> 'COMPANY' THEN 1 ELSE 0 END) AS OTHER_TYPE_COUNT,
            COUNT(DISTINCT STATION_ID) AS STATIONS_REPRESENTED
        FROM TAXPAYER
        """
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
        return {
            "total_taxpayers": int(row[0] or 0),
            "companies": int(row[1] or 0),
            "other_types": int(row[2] or 0),
            "stations_represented": int(row[3] or 0),
        }

    def get_taxpayer(self, taxpayer_id):
        sql = f"{TAXPAYER_SELECT} WHERE t.TAXPAYER_ID = :taxpayer_id"
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, taxpayer_id=taxpayer_id)
                return self._row_to_taxpayer(cur.fetchone())

    def taxpayer_exists(self, taxpayer_id):
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM TAXPAYER WHERE TAXPAYER_ID = :taxpayer_id",
                    taxpayer_id=taxpayer_id,
                )
                return cur.fetchone() is not None

    def station_exists(self, station_id):
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM STATION WHERE STATION_ID = :station_id",
                    station_id=station_id,
                )
                return cur.fetchone() is not None

    def station_options(self):
        sql = """
        SELECT STATION_ID, STATION_NAME
        FROM STATION
        ORDER BY STATION_NAME, STATION_ID
        """
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [
                    {"station_id": row[0], "station_name": row[1]}
                    for row in cur.fetchall()
                ]

    def create_taxpayer(self, taxpayer_id, taxpayer_name, taxpayer_type, station_id):
        sql = """
        INSERT INTO TAXPAYER
            (TAXPAYER_ID, TAXPAYER_NAME, TAXPAYER_TYPE, STATION_ID, UPDATED_AT)
        VALUES
            (:taxpayer_id, :taxpayer_name, :taxpayer_type, :station_id, SYSTIMESTAMP)
        """
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    taxpayer_id=taxpayer_id,
                    taxpayer_name=taxpayer_name,
                    taxpayer_type=taxpayer_type,
                    station_id=station_id,
                )
            conn.commit()
        return self.get_taxpayer(taxpayer_id)

    def update_taxpayer(self, taxpayer_id, taxpayer_name, taxpayer_type, station_id):
        sql = """
        UPDATE TAXPAYER
        SET TAXPAYER_NAME = :taxpayer_name,
            TAXPAYER_TYPE = :taxpayer_type,
            STATION_ID = :station_id,
            UPDATED_AT = SYSTIMESTAMP
        WHERE TAXPAYER_ID = :taxpayer_id
        """
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    taxpayer_id=taxpayer_id,
                    taxpayer_name=taxpayer_name,
                    taxpayer_type=taxpayer_type,
                    station_id=station_id,
                )
                updated = cur.rowcount == 1
            if updated:
                conn.commit()
            else:
                conn.rollback()
        return updated
