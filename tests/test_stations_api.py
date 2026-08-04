from fastapi.testclient import TestClient

from app.main import create_app
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
            },
            "ST002": {
                "station_id": "ST002",
                "station_name": "Jinja",
                "region": "EASTERN",
                "district": "JINJA",
                "updated_at": None,
                "taxpayer_count": 2,
            },
        }

    def list_stations(self, **kwargs):
        values = list(self.stations.values())
        search = (kwargs.get("search") or "").upper()
        region = (kwargs.get("region") or "").upper()
        if search:
            values = [
                s for s in values
                if search in s["station_id"].upper()
                or search in s["station_name"].upper()
                or search in s["district"].upper()
            ]
        if region:
            values = [s for s in values if s["region"] == region]
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


def client():
    app = create_app(station_service=StationService(FakeStationRepo()))
    return TestClient(app)


def test_create_and_get_station():
    c = client()

    response = c.post(
        "/api/stations",
        json={
            "station_id": "ST004",
            "station_name": "Entebbe",
            "region": "CENTRAL",
            "district": "WAKISO",
        },
    )

    assert response.status_code == 201
    assert response.json()["station_id"] == "ST004"

    detail = c.get("/api/stations/ST004")
    assert detail.status_code == 200
    assert detail.json()["station_name"] == "Entebbe"


def test_update_station_changes_existing_fields():
    c = client()

    response = c.put(
        "/api/stations/ST001",
        json={
            "station_name": "Kampala Central Office",
            "region": "CENTRAL",
            "district": "KAMPALA",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["station_name"] == "Kampala Central Office"
    assert body["region"] == "CENTRAL"


def test_station_list_returns_summary_and_filters():
    c = client()

    response = c.get("/api/stations?region=EASTERN")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["station_id"] == "ST002"
    assert body["summary"]["total_stations"] == 2
    assert body["summary"]["taxpayers_assigned"] == 3
