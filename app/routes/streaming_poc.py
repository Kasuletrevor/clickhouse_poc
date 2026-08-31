from fastapi import APIRouter, Request, status

from app.schemas.streaming_poc import StreamingPocStartRequest

router = APIRouter(prefix="/api/streaming-poc", tags=["streaming-poc"])


def service(request: Request):
    return request.app.state.streaming_poc_service


@router.get("/status")
def status_view(request: Request):
    return service(request).status()


@router.post("/start", status_code=status.HTTP_201_CREATED)
def start(payload: StreamingPocStartRequest, request: Request):
    return service(request).start(payload)


@router.post("/stop")
def stop(request: Request):
    return service(request).stop()
