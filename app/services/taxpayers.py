from typing import Protocol

from app.errors import APIError


class TaxpayerRepository(Protocol):
    def list_taxpayers(self, **kwargs): ...
    def taxpayer_summary(self): ...
    def get_taxpayer(self, taxpayer_id: str): ...
    def taxpayer_exists(self, taxpayer_id: str) -> bool: ...
    def station_exists(self, station_id: str) -> bool: ...
    def station_options(self): ...
    def create_taxpayer(self, taxpayer_id: str, taxpayer_name: str, taxpayer_type: str, station_id: str): ...
    def update_taxpayer(self, taxpayer_id: str, taxpayer_name: str, taxpayer_type: str, station_id: str) -> bool: ...


class TaxpayerService:
    def __init__(self, repo: TaxpayerRepository):
        self.repo = repo

    def list_taxpayers(self, **filters):
        items, total = self.repo.list_taxpayers(**filters)
        return {
            "items": items,
            "total": total,
            "summary": self.repo.taxpayer_summary(),
        }

    def get_taxpayer(self, taxpayer_id: str):
        taxpayer = self.repo.get_taxpayer(taxpayer_id)
        if taxpayer is None:
            raise APIError(404, "taxpayer_not_found", f"Taxpayer {taxpayer_id} does not exist.")
        return taxpayer

    def station_options(self):
        return self.repo.station_options()

    def create_taxpayer(self, taxpayer_id: str, taxpayer_name: str, taxpayer_type: str, station_id: str):
        if self.repo.taxpayer_exists(taxpayer_id):
            raise APIError(409, "duplicate_taxpayer", f"Taxpayer {taxpayer_id} already exists.")
        if not self.repo.station_exists(station_id):
            raise APIError(404, "station_not_found", f"Station {station_id} does not exist.")
        return self.repo.create_taxpayer(taxpayer_id, taxpayer_name, taxpayer_type, station_id)

    def update_taxpayer(self, taxpayer_id: str, taxpayer_name: str, taxpayer_type: str, station_id: str):
        if not self.repo.taxpayer_exists(taxpayer_id):
            raise APIError(404, "taxpayer_not_found", f"Taxpayer {taxpayer_id} does not exist.")
        if not self.repo.station_exists(station_id):
            raise APIError(404, "station_not_found", f"Station {station_id} does not exist.")
        if not self.repo.update_taxpayer(taxpayer_id, taxpayer_name, taxpayer_type, station_id):
            raise APIError(409, "taxpayer_changed", "Taxpayer changed before the update could be applied. Refresh and retry.")
        return self.get_taxpayer(taxpayer_id)
