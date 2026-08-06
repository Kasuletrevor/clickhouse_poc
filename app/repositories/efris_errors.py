class EfrisErrorRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _minutes(value):
        return max(1, min(int(value), 10080))

    def summary(self, minutes=60):
        minutes = self._minutes(minutes)
        rows = self.db.query(
            """
            /* efris_error_summary */
            SELECT
                count() AS error_events,
                uniqExact(seller_reference_no) AS affected_invoices,
                uniqExact(tin) AS affected_taxpayers,
                uniqExact(device_no) AS affected_devices,
                sumIf(gross_amount, upper(trimBoth(currency)) = 'UGX') AS ugx_gross_amount,
                sumIf(tax_amount, upper(trimBoth(currency)) = 'UGX') AS ugx_tax_amount
            FROM analytics.raw_efris_error_log
            WHERE create_date >= now() - INTERVAL {minutes} MINUTE
            """.format(minutes=minutes)
        )
        if not rows:
            return {
                "error_events": 0,
                "affected_invoices": 0,
                "affected_taxpayers": 0,
                "affected_devices": 0,
                "ugx_gross_amount": 0,
                "ugx_tax_amount": 0,
            }
        return rows[0]

    def top_codes(self, minutes=60, limit=8):
        minutes = self._minutes(minutes)
        limit = max(1, min(int(limit), 25))
        return self.db.query(
            """
            /* efris_error_top_codes */
            SELECT
                return_code,
                any(return_msg) AS message,
                count() AS occurrences,
                uniqExact(seller_reference_no) AS invoices,
                uniqExact(tin) AS taxpayers
            FROM analytics.raw_efris_error_log
            WHERE create_date >= now() - INTERVAL {minutes} MINUTE
            GROUP BY return_code
            ORDER BY occurrences DESC, return_code ASC
            LIMIT {limit}
            """.format(minutes=minutes, limit=limit)
        )

    def top_taxpayers(self, minutes=60, limit=8):
        minutes = self._minutes(minutes)
        limit = max(1, min(int(limit), 25))
        return self.db.query(
            """
            /* efris_error_top_taxpayers */
            SELECT
                tin,
                count() AS error_events,
                uniqExact(device_no) AS devices,
                uniqExact(seller_reference_no) AS invoices,
                uniqExact(return_code) AS error_codes
            FROM analytics.raw_efris_error_log
            WHERE create_date >= now() - INTERVAL {minutes} MINUTE
            GROUP BY tin
            ORDER BY error_events DESC, tin ASC
            LIMIT {limit}
            """.format(minutes=minutes, limit=limit)
        )

    def trend(self, minutes=60):
        minutes = self._minutes(minutes)
        bucket_minutes = 1 if minutes <= 180 else (15 if minutes <= 1440 else 60)
        return self.db.query(
            """
            /* efris_error_trend */
            SELECT
                toStartOfInterval(create_date, INTERVAL {bucket} MINUTE) AS bucket,
                count() AS error_events
            FROM analytics.raw_efris_error_log
            WHERE create_date >= now() - INTERVAL {minutes} MINUTE
            GROUP BY bucket
            ORDER BY bucket ASC
            """.format(bucket=bucket_minutes, minutes=minutes)
        )

    def recent(self, minutes=60, limit=50):
        minutes = self._minutes(minutes)
        limit = max(1, min(int(limit), 100))
        return self.db.query(
            """
            /* efris_error_recent */
            SELECT
                error_event_id,
                create_date,
                tin,
                device_no,
                seller_reference_no,
                return_code,
                return_msg,
                gross_amount,
                tax_amount,
                currency,
                operation,
                source_scn,
                source_commit_scn,
                kafka_partition,
                kafka_offset,
                ingested_at
            FROM analytics.raw_efris_error_log
            WHERE create_date >= now() - INTERVAL {minutes} MINUTE
            ORDER BY create_date DESC, error_event_id DESC
            LIMIT {limit}
            """.format(minutes=minutes, limit=limit)
        )
