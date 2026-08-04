from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def service(request: Request):
    return request.app.state.dashboard_service


@router.get("/summary")
def dashboard_summary(request: Request):
    return service(request).summary()


@router.get("/payments-by-station")
def payments_by_station(request: Request):
    return service(request).payments_by_station()


@router.get("/status-summary")
def status_summary(request: Request):
    return service(request).status_summary()


@router.get("/recent-activity")
def recent_activity(request: Request):
    return service(request).recent_activity()
