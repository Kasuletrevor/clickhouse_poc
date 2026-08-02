import pytest

from app.errors import APIError
from app.services.stations import StationService


class FakeStationRepo:
    def __init__(self):
        self.stations = {
            "ST001": {
                "station_id": "ST001",
                "station_name": "Kampala Central",
                "region": "CENTRAL",
                "district": "KAMPALA",
                "updated_at": None,
                "taxpayer_count": 1,
            }
        }

    def list_stations(self, **kwargs):
        values = list(self.stations.values())
        return values, len(values)

    def station_summary(self):
        return {
            "total_stations": len(self.stations),
            "regions": len({s["region"] for s in self.stations.values()}),
            "districts": len({s["district"] for s in self.stations.values()}),
            "taxpayers_assigned": sum(s["taxpayer_count"] for s in self.stations.values()),
        }

    def get_station(self, station_id):
        return self.stations.get(station_id)

    def station_exists(self, station_id):
        return station_id in self.stations

    def create_station(self, station_id, station_name, region, district):
        row = {
            "station_id": station_id,
            "station_name": station_name,
            "region": region,
            "district": district,
            "updated_at": None,
            "taxpayer_count": 0,
        }
        self.stations[station_id] = row
        return row

    def update_station(self, station_id, station_name, region, district):
        row = self.stations[station_id]
        row.update(
            station_name=station_name,
            region=region,
            district=district,
        )
        return row


def test_duplicate_station_is_rejected():
    service = StationService(FakeStationRepo())

    with pytest.raises(APIError) as exc_info:
        service.create_station("ST001", "Duplicate", "CENTRAL", "KAMPALA")

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "duplicate_station"


def test_station_can_be_created_with_existing_schema_fields():
    service = StationService(FakeStationRepo())

    created = service.create_station("ST004", "Entebbe", "CENTRAL", "WAKISO")

    assert created["station_id"] == "ST004"
    assert created["station_name"] == "Entebbe"
    assert created["region"] == "CENTRAL"
    assert created["district"] == "WAKISO"
    assert created["taxpayer_count"] == 0


def test_missing_station_cannot_be_updated():
    service = StationService(FakeStationRepo())

    with pytest.raises(APIError) as exc_info:
        service.update_station("ST999", "Missing", "CENTRAL", "KAMPALA")

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "station_not_found"
