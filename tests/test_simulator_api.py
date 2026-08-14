from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.errors import APIError
from app.routes.simulator import router


class FakeService:
    def start(self, payload):
        return {"run_id": "EFR-TEST", "status": "starting", "rate": payload.rate}

    def status(self):
        return {"state": "idle", "active": None}

    def history(self, limit):
        return []

    def events(self, run_id, limit):
        return []

    def pause(self, run_id):
        return {"run_id": run_id, "command": "pause"}

    def resume(self, run_id):
        return {"run_id": run_id, "command": "run"}

    def stop(self, run_id):
        return {"run_id": run_id, "command": "stop"}

    def close_gap(self, run_id):
        return {"run_id": run_id, "status": "cdc_gap", "gap_events": 236}


def app_with(service):
    app = FastAPI()
    app.state.simulator_service = service
    app.include_router(router)

    @app.exception_handler(APIError)
    async def handler(_request: Request, exc: APIError):
        payload = {"error": exc.code, "message": exc.message}
        if exc.details:
            payload["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=payload)

    return app


def test_start_simulation_returns_created_run():
    response = TestClient(app_with(FakeService())).post(
        "/api/simulator/runs",
        json={"rate": 14, "duration_seconds": 600, "retry_probability": 0.12},
    )
    assert response.status_code == 201
    assert response.json()["run_id"] == "EFR-TEST"


def test_start_validation_rejects_zero_rate():
    response = TestClient(app_with(FakeService())).post(
        "/api/simulator/runs",
        json={"rate": 0, "duration_seconds": 60, "retry_probability": 0.12},
    )
    assert response.status_code == 422


def test_control_routes():
    client = TestClient(app_with(FakeService()))
    assert client.post("/api/simulator/runs/EFR-1/pause").json()["command"] == "pause"
    assert client.post("/api/simulator/runs/EFR-1/resume").json()["command"] == "run"
    assert client.post("/api/simulator/runs/EFR-1/stop").json()["command"] == "stop"


def test_close_cdc_gap_route():
    response = TestClient(app_with(FakeService())).post("/api/simulator/runs/EFR-1/close-gap")
    assert response.status_code == 200
    assert response.json() == {"run_id": "EFR-1", "status": "cdc_gap", "gap_events": 236}
