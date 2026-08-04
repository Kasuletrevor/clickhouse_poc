from typing import Optional

from fastapi import APIRouter, Query, Request, status

from app.schemas.taxpayers import TaxpayerCreate, TaxpayerUpdate

router = APIRouter(prefix="/api/taxpayers", tags=["taxpayers"])


def service(request: Request):
    return request.app.state.taxpayer_service


@router.get("")
def list_taxpayers(
    request: Request,
    search: Optional[str] = None,
    taxpayer_type: Optional[str] = Query(default=None, alias="type"),
    station_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return service(request).list_taxpayers(
        search=search,
        taxpayer_type=taxpayer_type,
        station_id=station_id,
        limit=limit,
        offset=offset,
    )


@router.get("/station-options")
def station_options(request: Request):
    return service(request).station_options()


@router.get("/{taxpayer_id}")
def get_taxpayer(taxpayer_id: str, request: Request):
    return service(request).get_taxpayer(taxpayer_id.strip().upper())


@router.post("", status_code=status.HTTP_201_CREATED)
def create_taxpayer(payload: TaxpayerCreate, request: Request):
    return service(request).create_taxpayer(
        payload.taxpayer_id,
        payload.taxpayer_name,
        payload.taxpayer_type,
        payload.station_id,
    )


@router.put("/{taxpayer_id}")
def update_taxpayer(taxpayer_id: str, payload: TaxpayerUpdate, request: Request):
    return service(request).update_taxpayer(
        taxpayer_id.strip().upper(),
        payload.taxpayer_name,
        payload.taxpayer_type,
        payload.station_id,
    )
