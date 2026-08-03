class DashboardRepository:
    def __init__(self, db):
        self.db = db

    def summary(self):
        rows = self.db.query(
            """
            /* dashboard_summary */
            SELECT
                (SELECT count() FROM analytics.dim_oracle_taxpayer_current) AS total_taxpayers,
                (SELECT count() FROM analytics.dim_oracle_station_current) AS total_stations,
                countIf(
                    toDate(payment_time, 'Africa/Kampala') = toDate(now('Africa/Kampala'))
                ) AS payments_today,
                sumIf(
                    amount,
                    payment_status = 'SUCCESSFUL'
                    AND toDate(payment_time, 'Africa/Kampala') = toDate(now('Africa/Kampala'))
                ) AS amount_collected_today
            FROM analytics.vw_oracle_payment_analytics
            """
        )
        if not rows:
            return {
                "total_taxpayers": 0,
                "total_stations": 0,
                "payments_today": 0,
                "amount_collected_today": 0,
            }
        return rows[0]

    def payments_by_station(self):
        return self.db.query(
            """
            /* payments_by_station */
            SELECT
                if(empty(station_at_payment), 'Unassigned', station_at_payment) AS station_name,
                count() AS payment_count,
                sumIf(amount, payment_status = 'SUCCESSFUL') AS successful_amount
            FROM analytics.vw_oracle_payment_analytics
            GROUP BY station_name
            ORDER BY successful_amount DESC, payment_count DESC, station_name ASC
            """
        )

    def status_summary(self):
        return self.db.query(
            """
            /* status_summary */
            SELECT
                payment_status AS status,
                count() AS payment_count,
                sum(amount) AS amount
            FROM analytics.vw_oracle_payment_analytics
            WHERE payment_status IN ('SUCCESSFUL', 'PENDING', 'REVERSED')
            GROUP BY status
            ORDER BY indexOf(['SUCCESSFUL', 'PENDING', 'REVERSED'], status)
            """
        )

    def recent_payments(self, limit=8):
        safe_limit = max(1, min(int(limit), 20))
        return self.db.query(
            """
            /* recent_payments */
            SELECT
                payment_id,
                taxpayer_id,
                taxpayer_name,
                amount,
                payment_status AS status,
                payment_time,
                station_at_payment
            FROM analytics.vw_oracle_payment_analytics
            ORDER BY payment_time DESC, payment_id DESC
            LIMIT {limit}
            """.format(limit=safe_limit)
        )

    def recent_taxpayer_events(self, limit=12):
        safe_limit = max(1, min(int(limit), 30))
        return self.db.query(
            """
            /* recent_taxpayer_events */
            SELECT
                taxpayer_id,
                taxpayer_name,
                taxpayer_type,
                station_id,
                dbz_op,
                source_commit_scn,
                source_scn,
                source_ssn,
                kafka_partition,
                kafka_offset,
                source_commit_time,
                previous_taxpayer_name,
                previous_taxpayer_type,
                previous_station_id
            FROM
            (
                SELECT
                    taxpayer_id,
                    taxpayer_name,
                    taxpayer_type,
                    station_id,
                    dbz_op,
                    source_commit_scn,
                    source_scn,
                    source_ssn,
                    kafka_partition,
                    kafka_offset,
                    source_commit_time,
                    lagInFrame(toString(taxpayer_name), 1, '') OVER w AS previous_taxpayer_name,
                    lagInFrame(toString(taxpayer_type), 1, '') OVER w AS previous_taxpayer_type,
                    lagInFrame(toString(station_id), 1, '') OVER w AS previous_station_id
                FROM analytics.raw_oracle_taxpayer_cdc
                WHERE is_deleted = 0
                WINDOW w AS (
                    PARTITION BY taxpayer_id
                    ORDER BY source_commit_scn, source_scn, source_ssn, kafka_partition, kafka_offset
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                )
            )
            ORDER BY source_commit_scn DESC, source_scn DESC, source_ssn DESC,
                     kafka_partition DESC, kafka_offset DESC
            LIMIT {limit}
            """.format(limit=safe_limit)
        )

    def station_name_map(self):
        rows = self.db.query(
            """
            /* station_name_map */
            SELECT station_id, station_name
            FROM analytics.dim_oracle_station_current
            """
        )
        return {row["station_id"]: row["station_name"] for row in rows}
