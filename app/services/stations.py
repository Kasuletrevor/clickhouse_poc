from typing import Protocol

from app.errors import APIError


class StationRepository(Protocol):
    def list_stations(self, **kwargs): ...
    def station_summary(self): ...
    def get_station(self, station_id: str): ...
    def station_exists(self, station_id: str) -> bool: ...
    def create_station(self, station_id: str, station_name: str, region: str, district: str): ...
    def update_station(self, station_id: str, station_name: str, region: str, district: str): ...


class StationService:
    def __init__(self, repo: StationRepository):
        self.repo = repo

    def list_stations(self, **filters):
        items, total = self.repo.list_stations(**filters)
        return {
            "items": items,
            "total": total,
            "summary": self.repo.station_summary(),
        }

    def get_station(self, station_id: str):
        station_id = station_id.strip().upper()
        station = self.repo.get_station(station_id)
        if station is None:
            raise APIError(404, "station_not_found", f"Station {station_id} does not exist.")
        return station

    def create_station(self, station_id: str, station_name: str, region: str, district: str):
        station_id = station_id.strip().upper()
        if self.repo.station_exists(station_id):
            raise APIError(409, "duplicate_station", f"Station {station_id} already exists.")
        return self.repo.create_station(station_id, station_name, region, district)

    def update_station(self, station_id: str, station_name: str, region: str, district: str):
        station_id = station_id.strip().upper()
        if not self.repo.station_exists(station_id):
            raise APIError(404, "station_not_found", f"Station {station_id} does not exist.")
        return self.repo.update_station(station_id, station_name, region, district)
