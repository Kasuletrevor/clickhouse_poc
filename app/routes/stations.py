from typing import Optional

from fastapi import APIRouter, Query, Request, status

from app.schemas.stations import StationCreate, StationUpdate

router = APIRouter(prefix="/api/stations", tags=["stations"])


def service(request: Request):
    return request.app.state.station_service


@router.get("")
def list_stations(
    request: Request,
    search: Optional[str] = None,
    region: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return service(request).list_stations(
        search=search,
        region=region,
        limit=limit,
        offset=offset,
    )


@router.get("/{station_id}")
def get_station(station_id: str, request: Request):
    return service(request).get_station(station_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_station(payload: StationCreate, request: Request):
    return service(request).create_station(
        payload.station_id,
        payload.station_name,
        payload.region,
        payload.district,
    )


@router.put("/{station_id}")
def update_station(station_id: str, payload: StationUpdate, request: Request):
    return service(request).update_station(
        station_id,
        payload.station_name,
        payload.region,
        payload.district,
    )
