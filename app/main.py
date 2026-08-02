from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.errors import APIError
from app.oracle import OracleDatabase, SourceOperationError, SourceUnavailableError
from app.repositories.payments import OraclePaymentRepository
from app.repositories.stations import OracleStationRepository
from app.repositories.taxpayers import OracleTaxpayerRepository
from app.routes.payments import router as payments_router
from app.routes.stations import router as stations_router
from app.routes.taxpayers import router as taxpayers_router
from app.services.payments import PaymentService
from app.services.stations import StationService
from app.services.taxpayers import TaxpayerService

BASE_DIR = Path(__file__).resolve().parent


def default_payment_service() -> PaymentService:
    db = OracleDatabase(get_settings())
    return PaymentService(OraclePaymentRepository(db))


def default_taxpayer_service() -> TaxpayerService:
    db = OracleDatabase(get_settings())
    return TaxpayerService(OracleTaxpayerRepository(db))


def default_station_service() -> StationService:
    db = OracleDatabase(get_settings())
    return StationService(OracleStationRepository(db))


def create_app(payment_service=None, taxpayer_service=None, station_service=None) -> FastAPI:
    app = FastAPI(title="Internal Transaction Application", version="0.3.0")
    app.state.payment_service = payment_service or default_payment_service()
    app.state.taxpayer_service = taxpayer_service or default_taxpayer_service()
    app.state.station_service = station_service or default_station_service()
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    app.include_router(payments_router)
    app.include_router(taxpayers_router)
    app.include_router(stations_router)

    @app.exception_handler(APIError)
    async def api_error_handler(_request: Request, exc: APIError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": exc.message})

    @app.exception_handler(SourceUnavailableError)
    async def source_unavailable_handler(_request: Request, _exc: SourceUnavailableError):
        return JSONResponse(status_code=503, content={"error": "source_unavailable", "message": "The Oracle source system is temporarily unavailable."})

    @app.exception_handler(SourceOperationError)
    async def source_operation_handler(_request: Request, _exc: SourceOperationError):
        return JSONResponse(status_code=500, content={"error": "source_operation_failed", "message": "The source transaction could not be completed."})

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse(request=request, name="index.html", context={})

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
