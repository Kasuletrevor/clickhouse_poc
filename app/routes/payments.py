from typing import Optional

from fastapi import APIRouter, Query, Request, status

from app.schemas.payments import PaymentCreate, PaymentStatusUpdate

router = APIRouter(prefix="/api/payments", tags=["payments"])


def service(request: Request):
    return request.app.state.payment_service


@router.get("")
def list_payments(
    request: Request,
    search: Optional[str] = None,
    payment_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return service(request).list_payments(
        search=search,
        status=payment_status,
        limit=limit,
        offset=offset,
    )


@router.get("/{payment_id}")
def get_payment(payment_id: str, request: Request):
    return service(request).get_payment(payment_id.strip().upper())


@router.post("", status_code=status.HTTP_201_CREATED)
def create_payment(payload: PaymentCreate, request: Request):
    return service(request).create_payment(
        payload.payment_id,
        payload.taxpayer_id,
        payload.amount,
        payload.status,
    )


@router.post("/{payment_id}/status")
def update_payment_status(payment_id: str, payload: PaymentStatusUpdate, request: Request):
    return service(request).change_status(payment_id.strip().upper(), payload.status)
