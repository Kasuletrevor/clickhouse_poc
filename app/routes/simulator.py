from fastapi import APIRouter, Query, Request, status

from app.schemas.simulator import SimulatorStartRequest

router = APIRouter(prefix="/api/simulator", tags=["simulator"])


def service(request: Request):
    return request.app.state.simulator_service


@router.post("/runs", status_code=status.HTTP_201_CREATED)
def start_run(payload: SimulatorStartRequest, request: Request):
    return service(request).start(payload)


@router.get("/status")
def status_view(request: Request):
    return service(request).status()


@router.get("/runs")
def run_history(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    return service(request).history(limit)


@router.get("/runs/{run_id}/events")
def run_events(run_id: str, request: Request, limit: int = Query(default=40, ge=1, le=100)):
    return service(request).events(run_id, limit)


@router.post("/runs/{run_id}/pause")
def pause_run(run_id: str, request: Request):
    return service(request).pause(run_id)


@router.post("/runs/{run_id}/resume")
def resume_run(run_id: str, request: Request):
    return service(request).resume(run_id)


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: str, request: Request):
    return service(request).stop(run_id)


@router.post("/runs/{run_id}/close-gap")
def close_cdc_gap(run_id: str, request: Request):
    return service(request).close_gap(run_id)
