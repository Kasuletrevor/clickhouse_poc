from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/efris-errors", tags=["efris-errors"])


def service(request: Request):
    return request.app.state.efris_error_service


@router.get("/dashboard")
def efris_error_dashboard(
    request: Request,
    minutes: int = Query(default=60, ge=1, le=10080),
):
    return service(request).dashboard(minutes)
