from fastapi import APIRouter, Query, Request, status

from app.schemas.efris_errors import EfrisErrorCreate

router = APIRouter(prefix="/api/efris-errors", tags=["efris-errors"])


def analytics_service(request: Request):
    return request.app.state.efris_error_service


def event_service(request: Request):
    return request.app.state.efris_event_service


@router.get("/dashboard")
def efris_error_dashboard(
    request: Request,
    minutes: int = Query(default=60, ge=1, le=10080),
):
    return analytics_service(request).dashboard(minutes)


@router.get("/devices")
def efris_devices(
    request: Request,
    tin: str = Query(min_length=1, max_length=20),
):
    return event_service(request).devices(tin)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_efris_error(payload: EfrisErrorCreate, request: Request):
    return event_service(request).create_event(payload)
