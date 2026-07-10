import uuid

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.payment import (
    PaymentInitializeRequest,
    PaymentRead,
    PaymentVerifyResponse,
)

router = APIRouter(prefix="/payments", tags=["payments"])

_NOT_IMPLEMENTED = "Stub endpoint — Paystack integration lands on Day 2+."


@router.post("/initialize", response_model=PaymentRead, summary="Initialize a Paystack transaction")
def initialize_payment(payload: PaymentInitializeRequest) -> PaymentRead:
    """Create/refresh a Paystack transaction for a booking and return its
    reference + authorization_url."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.get("/verify/{reference}", response_model=PaymentVerifyResponse, summary="Verify a transaction")
def verify_payment(reference: str) -> PaymentVerifyResponse:
    """Server-side verify a Paystack transaction by reference and reconcile the
    booking/appointment state."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.get("/{payment_id}", response_model=PaymentRead, summary="Get a payment")
def get_payment(payment_id: uuid.UUID) -> PaymentRead:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)


@router.post("/webhook", summary="Paystack webhook receiver")
async def paystack_webhook(request: Request) -> dict:
    """Receive Paystack events (charge.success, etc.). Signature verification and
    idempotent reconciliation land on Day 2+."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, _NOT_IMPLEMENTED)
