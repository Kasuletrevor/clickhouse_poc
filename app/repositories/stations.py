from app.oracle import OracleDatabase


STATION_SELECT = """
SELECT
    s.STATION_ID,
    s.STATION_NAME,
    s.REGION,
    s.DISTRICT,
    s.UPDATED_AT,
    (
        SELECT COUNT(*)
        FROM TAXPAYER t
        WHERE t.STATION_ID = s.STATION_ID
    ) AS TAXPAYER_COUNT
FROM STATION s
"""


class OracleStationRepository:
    def __init__(self, db: OracleDatabase):
        self.db = db

    @staticmethod
    def _row_to_station(row):
        if row is None:
            return None
        return {
            "station_id": row[0],
            "station_name": row[1],
            "region": row[2],
            "district": row[3],
            "updated_at": row[4],
            "taxpayer_count": int(row[5] or 0),
        }

    def list_stations(self, search=None, region=None, limit=100, offset=0):
        predicates = []
        binds = {}

        if search:
            predicates.append(
                "(UPPER(s.STATION_ID) LIKE :search "
                "OR UPPER(s.STATION_NAME) LIKE :search "
                "OR UPPER(s.REGION) LIKE :search "
                "OR UPPER(s.DISTRICT) LIKE :search)"
            )
            binds["search"] = f"%{search.strip().upper()}%"

        if region:
            predicates.append("UPPER(s.REGION) = :region")
            binds["region"] = region.strip().upper()

        where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
        count_sql = f"SELECT COUNT(*) FROM STATION s{where}"
        data_sql = f"""
            {STATION_SELECT}
            {where}
            ORDER BY s.STATION_NAME, s.STATION_ID
            OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
        """
        data_binds = {**binds, "offset": offset, "limit": limit}

        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, binds)
                total = int(cur.fetchone()[0])
                cur.execute(data_sql, data_binds)
                items = [self._row_to_station(row) for row in cur.fetchall()]
        return items, total

    def station_summary(self):
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*),
                        COUNT(DISTINCT REGION),
                        COUNT(DISTINCT DISTRICT)
                    FROM STATION
                    """
                )
                station_row = cur.fetchone()
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM TAXPAYER
                    WHERE STATION_ID IS NOT NULL
                    """
                )
                taxpayer_count = int(cur.fetchone()[0] or 0)

        return {
            "total_stations": int(station_row[0] or 0),
            "regions": int(station_row[1] or 0),
            "districts": int(station_row[2] or 0),
            "taxpayers_assigned": taxpayer_count,
        }

    def get_station(self, station_id):
        sql = f"{STATION_SELECT} WHERE s.STATION_ID = :station_id"
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, station_id=station_id)
                return self._row_to_station(cur.fetchone())

    def station_exists(self, station_id):
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM STATION WHERE STATION_ID = :station_id",
                    station_id=station_id,
                )
                return cur.fetchone() is not None

    def create_station(self, station_id, station_name, region, district):
        sql = """
        INSERT INTO STATION
            (STATION_ID, STATION_NAME, REGION, DISTRICT, UPDATED_AT)
        VALUES
            (:station_id, :station_name, :region, :district, SYSTIMESTAMP)
        """
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    station_id=station_id,
                    station_name=station_name,
                    region=region,
                    district=district,
                )
            conn.commit()
        return self.get_station(station_id)

    def update_station(self, station_id, station_name, region, district):
        sql = """
        UPDATE STATION
        SET STATION_NAME = :station_name,
            REGION = :region,
            DISTRICT = :district,
            UPDATED_AT = SYSTIMESTAMP
        WHERE STATION_ID = :station_id
        """
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    station_id=station_id,
                    station_name=station_name,
                    region=region,
                    district=district,
                )
            conn.commit()
        return self.get_station(station_id)
