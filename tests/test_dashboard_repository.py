from app.repositories.dashboard import DashboardRepository


class FakeClickHouse:
    def __init__(self):
        self.sql = []

    def query(self, sql):
        self.sql.append(sql)
        if "dashboard_summary" in sql:
            return [{"total_taxpayers": 3, "total_stations": 3, "payments_today": 47, "amount_collected_today": 41250000}]
        if "payments_by_station" in sql:
            return [{"station_name": "Jinja", "payment_count": 20, "successful_amount": 16000000}]
        if "status_summary" in sql:
            return [{"status": "SUCCESSFUL", "payment_count": 44, "amount": 40000000}]
        if "recent_payments" in sql:
            return [{"payment_id": "PAY103", "status": "SUCCESSFUL", "station_at_payment": "Jinja"}]
        if "recent_taxpayer_events" in sql:
            return [{"taxpayer_id": "TIN001", "previous_station_id": "ST001", "station_id": "ST002"}]
        if "station_name_map" in sql:
            return [{"station_id": "ST001", "station_name": "Kampala Central"}]
        raise AssertionError(sql)


def test_summary_uses_eat_and_successful_amount_only():
    db = FakeClickHouse()
    result = DashboardRepository(db).summary()

    assert result["amount_collected_today"] == 41250000
    sql = db.sql[0]
    assert "Africa/Kampala" in sql
    assert "payment_status = 'SUCCESSFUL'" in sql
    assert "vw_oracle_payment_analytics" in sql


def test_station_aggregation_uses_station_at_payment():
    db = FakeClickHouse()
    rows = DashboardRepository(db).payments_by_station()

    assert rows[0]["station_name"] == "Jinja"
    assert "station_at_payment" in db.sql[0]
    assert "successful_amount DESC" in db.sql[0]


def test_recent_taxpayer_events_use_source_ordering_not_ingested_at():
    db = FakeClickHouse()
    DashboardRepository(db).recent_taxpayer_events()

    sql = db.sql[0]
    for column in ("source_commit_scn", "source_scn", "source_ssn", "kafka_partition", "kafka_offset"):
        assert column in sql
    assert "ORDER BY ingested_at" not in sql
