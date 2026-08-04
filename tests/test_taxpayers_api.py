from fastapi.testclient import TestClient

from app.main import create_app
from app.services.taxpayers import TaxpayerService


class FakeTaxpayerRepo:
    def __init__(self):
        self.taxpayers = {}
        self.stations = {
            "ST001": "Kampala Central",
            "ST002": "Jinja",
        }

    def list_taxpayers(self, **kwargs):
        items = list(self.taxpayers.values())
        return items, len(items)

    def taxpayer_summary(self):
        values = list(self.taxpayers.values())
        return {
            "total_taxpayers": len(values),
            "companies": sum(t["taxpayer_type"] == "COMPANY" for t in values),
            "other_types": sum(t["taxpayer_type"] != "COMPANY" for t in values),
            "stations_represented": len({t["station_id"] for t in values}),
        }

    def get_taxpayer(self, taxpayer_id):
        return self.taxpayers.get(taxpayer_id)

    def taxpayer_exists(self, taxpayer_id):
        return taxpayer_id in self.taxpayers

    def station_exists(self, station_id):
        return station_id in self.stations

    def station_options(self):
        return [{"station_id": key, "station_name": value} for key, value in self.stations.items()]

    def create_taxpayer(self, taxpayer_id, taxpayer_name, taxpayer_type, station_id):
        self.taxpayers[taxpayer_id] = {
            "taxpayer_id": taxpayer_id,
            "taxpayer_name": taxpayer_name,
            "taxpayer_type": taxpayer_type,
            "station_id": station_id,
            "station_name": self.stations[station_id],
            "updated_at": None,
        }
        return self.taxpayers[taxpayer_id]

    def update_taxpayer(self, taxpayer_id, taxpayer_name, taxpayer_type, station_id):
        if taxpayer_id not in self.taxpayers:
            return False
        self.taxpayers[taxpayer_id].update(
            taxpayer_name=taxpayer_name,
            taxpayer_type=taxpayer_type,
            station_id=station_id,
            station_name=self.stations[station_id],
        )
        return True


def client():
    app = create_app(taxpayer_service=TaxpayerService(FakeTaxpayerRepo()))
    return TestClient(app)


def test_create_and_get_taxpayer():
    c = client()

    response = c.post(
        "/api/taxpayers",
        json={
            "taxpayer_id": "tin010",
            "taxpayer_name": "New Trader Ltd",
            "taxpayer_type": "company",
            "station_id": "st002",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["taxpayer_id"] == "TIN010"
    assert created["taxpayer_type"] == "COMPANY"
    assert created["station_name"] == "Jinja"

    detail = c.get("/api/taxpayers/TIN010")
    assert detail.status_code == 200
    assert detail.json()["taxpayer_name"] == "New Trader Ltd"


def test_update_taxpayer_reassigns_station():
    c = client()
    c.post(
        "/api/taxpayers",
        json={
            "taxpayer_id": "TIN011",
            "taxpayer_name": "Example Services",
            "taxpayer_type": "COMPANY",
            "station_id": "ST001",
        },
    )

    response = c.put(
        "/api/taxpayers/TIN011",
        json={
            "taxpayer_name": "Example Services Uganda",
            "taxpayer_type": "COMPANY",
            "station_id": "ST002",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["station_id"] == "ST002"
    assert body["station_name"] == "Jinja"


def test_taxpayer_list_and_station_options():
    c = client()
    c.post(
        "/api/taxpayers",
        json={
            "taxpayer_id": "TIN012",
            "taxpayer_name": "List Test",
            "taxpayer_type": "INDIVIDUAL",
            "station_id": "ST001",
        },
    )

    listing = c.get("/api/taxpayers")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["summary"]["total_taxpayers"] == 1

    options = c.get("/api/taxpayers/station-options")
    assert options.status_code == 200
    assert {item["station_id"] for item in options.json()} == {"ST001", "ST002"}
