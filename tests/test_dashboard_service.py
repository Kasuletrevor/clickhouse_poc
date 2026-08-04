from app.services.dashboard import DashboardService


class FakeRepo:
    def summary(self):
        return {
            "total_taxpayers": 3,
            "total_stations": 3,
            "payments_today": 47,
            "amount_collected_today": 41250000,
        }

    def payments_by_station(self):
        return [{"station_name": "Jinja", "payment_count": 20, "successful_amount": 16000000}]

    def status_summary(self):
        return [
            {"status": "SUCCESSFUL", "payment_count": 44, "amount": 40000000},
            {"status": "PENDING", "payment_count": 3, "amount": 1250000},
        ]

    def recent_payments(self):
        return [{"payment_id": "PAY103", "status": "SUCCESSFUL"}]

    def station_name_map(self):
        return {"ST001": "Kampala Central", "ST002": "Jinja"}

    def recent_taxpayer_events(self):
        return [
            {
                "taxpayer_id": "TIN004",
                "taxpayer_name": "New Traders",
                "taxpayer_type": "COMPANY",
                "station_id": "ST001",
                "dbz_op": "c",
                "source_commit_time": "2026-08-02 15:10:00",
                "previous_taxpayer_name": "",
                "previous_taxpayer_type": "",
                "previous_station_id": "",
            },
            {
                "taxpayer_id": "TIN003",
                "taxpayer_name": "XYZ Holdings",
                "taxpayer_type": "COMPANY",
                "station_id": "ST002",
                "dbz_op": "u",
                "source_commit_time": "2026-08-02 15:12:00",
                "previous_taxpayer_name": "XYZ Holdings",
                "previous_taxpayer_type": "COMPANY",
                "previous_station_id": "ST001",
            },
            {
                "taxpayer_id": "TIN002",
                "taxpayer_name": "ABC Enterprises Ltd",
                "taxpayer_type": "COMPANY",
                "station_id": "ST002",
                "dbz_op": "u",
                "source_commit_time": "2026-08-02 15:14:00",
                "previous_taxpayer_name": "ABC Enterprises",
                "previous_taxpayer_type": "COMPANY",
                "previous_station_id": "ST002",
            },
        ]


def test_status_summary_always_returns_all_three_payment_states():
    rows = DashboardService(FakeRepo()).status_summary()

    assert [row["status"] for row in rows] == ["SUCCESSFUL", "PENDING", "REVERSED"]
    assert rows[2]["payment_count"] == 0


def test_recent_activity_translates_create_station_move_and_details_update():
    body = DashboardService(FakeRepo()).recent_activity()
    activity = body["recent_taxpayer_activity"]

    assert activity[0]["action"] == "Taxpayer created"
    assert activity[1]["action"] == "Station changed"
    assert activity[1]["message"] == "Kampala Central → Jinja"
    assert activity[2]["action"] == "Taxpayer details updated"
    assert body["recent_payments"][0]["payment_id"] == "PAY103"
