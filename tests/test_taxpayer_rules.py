from app.errors import APIError
from app.services.taxpayers import TaxpayerService


class FakeTaxpayerRepo:
    def __init__(self):
        self.taxpayers = {
            "TIN001": {
                "taxpayer_id": "TIN001",
                "taxpayer_name": "KJT Traders",
                "taxpayer_type": "COMPANY",
                "station_id": "ST001",
                "station_name": "Kampala Central",
                "updated_at": None,
            }
        }
        self.stations = {
            "ST001": "Kampala Central",
            "ST002": "Jinja",
        }

    def list_taxpayers(self, **kwargs):
        items = list(self.taxpayers.values())
        return items, len(items)

    def taxpayer_summary(self):
        return {
            "total_taxpayers": len(self.taxpayers),
            "companies": sum(t["taxpayer_type"] == "COMPANY" for t in self.taxpayers.values()),
            "other_types": sum(t["taxpayer_type"] != "COMPANY" for t in self.taxpayers.values()),
            "stations_represented": len({t["station_id"] for t in self.taxpayers.values()}),
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


def test_duplicate_taxpayer_is_rejected():
    service = TaxpayerService(FakeTaxpayerRepo())

    try:
        service.create_taxpayer("TIN001", "Duplicate", "COMPANY", "ST001")
        assert False, "expected duplicate taxpayer error"
    except APIError as exc:
        assert exc.status_code == 409
        assert exc.code == "duplicate_taxpayer"


def test_taxpayer_requires_existing_station():
    service = TaxpayerService(FakeTaxpayerRepo())

    try:
        service.create_taxpayer("TIN010", "New Trader", "COMPANY", "ST999")
        assert False, "expected station not found error"
    except APIError as exc:
        assert exc.status_code == 404
        assert exc.code == "station_not_found"


def test_update_can_reassign_taxpayer_station():
    repo = FakeTaxpayerRepo()
    service = TaxpayerService(repo)

    updated = service.update_taxpayer("TIN001", "KJT Traders", "COMPANY", "ST002")

    assert updated["station_id"] == "ST002"
    assert updated["station_name"] == "Jinja"
