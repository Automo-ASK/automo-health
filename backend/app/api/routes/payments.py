import json
import logging
import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.enums import PaymentStatus
from app.models.payment import Payment
from app.schemas.payment import (
    PaymentLinkRequest,
    PaymentLinkResponse,
    PaymentRead,
    PaymentVerifyResponse,
    VirtualAccountRead,
    VirtualAccountRequest,
)
from app.services import paystack, payments as payments_service, reconciliation
from app.services.exceptions import NotFoundError

_WA_STATUS: dict[PaymentStatus, str] = {
    PaymentStatus.PENDING: "pending",
    PaymentStatus.SUCCESS: "paid",
    PaymentStatus.FAILED: "failed",
    PaymentStatus.ABANDONED: "expired",
    PaymentStatus.REFUNDED: "paid",
}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "/virtual-account",
    response_model=VirtualAccountRead,
    status_code=status.HTTP_201_CREATED,
    summary="Provision a per-booking virtual account",
)
def create_virtual_account(
    payload: VirtualAccountRequest, db: Session = Depends(get_db)
) -> VirtualAccountRead:
    """Create (or return) a dedicated NUBAN for a booking's bank-transfer payment."""
    return payments_service.create_virtual_account(db, payload.booking_id)


@router.post(
    "/link",
    response_model=PaymentLinkResponse,
    summary="Generate an in-chat payment link",
)
def generate_payment_link(
    payload: PaymentLinkRequest, db: Session = Depends(get_db)
) -> PaymentLinkResponse:
    """Build a shareable payment payload (checkout link + bank transfer details +
    a ready-to-send chat message) for a booking.

    Accepts either ``booking_id`` or ``appointment_id`` (WhatsApp alias).
    The response includes WhatsApp-compatible ``payment_id``, ``method``, ``url``,
    and ``expires_at`` fields alongside the original shape.
    """
    link = payments_service.generate_payment_link(
        db, payload.booking_id, include_virtual_account=payload.include_virtual_account
    )
    # Fetch payment record for WhatsApp-specific fields.
    from app.models.booking import Booking
    booking = db.get(Booking, link.booking_id)
    payment = booking.payment if booking else None
    return PaymentLinkResponse(
        booking_id=link.booking_id,
        amount=link.amount,
        currency=link.currency,
        reference=link.reference,
        checkout_url=link.checkout_url,
        virtual_account=(
            VirtualAccountRead.model_validate(link.virtual_account)
            if link.virtual_account is not None
            else None
        ),
        chat_message=link.chat_message,
        # WhatsApp shape
        payment_id=payment.id if payment else None,
        method="link",
        url=link.checkout_url,
        expires_at=booking.expires_at if booking else None,
    )


@router.get("/verify/{reference}", response_model=PaymentVerifyResponse, summary="Verify a transaction")
def verify_payment(reference: str, db: Session = Depends(get_db)) -> PaymentVerifyResponse:
    """Server-side verify a Paystack transaction by reference and reconcile the
    booking/appointment state."""
    data = paystack.verify_transaction(reference)
    data.setdefault("reference", reference)
    result = reconciliation.reconcile_from_paystack(db, data)
    return PaymentVerifyResponse(
        reference=reference,
        status=result.status,
        detail=result.detail,
        booking_id=result.booking.id if result.booking else None,
        appointment_id=result.appointment.id if result.appointment else None,
    )


@router.get("/{payment_id}", summary="Get a payment")
def get_payment(payment_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Return payment data.

    Includes WhatsApp-compatible aliases (``payment_id``, ``appointment_id``,
    ``method``) and normalizes ``status`` to the values WhatsApp polls on:
    ``pending`` / ``paid`` / ``failed`` / ``expired``.
    """
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError(f"Payment {payment_id} not found")
    return {
        "id": str(payment.id),
        "payment_id": str(payment.id),
        "booking_id": str(payment.booking_id),
        "appointment_id": str(payment.booking_id),
        "provider": payment.provider.value,
        "status": _WA_STATUS.get(payment.status, payment.status.value),
        "amount": payment.amount,
        "currency": payment.currency,
        "method": "link",
        "reference": payment.reference,
        "authorization_url": payment.authorization_url,
        "access_code": payment.access_code,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "created_at": payment.created_at.isoformat(),
    }


@router.post("/webhook", summary="Paystack webhook receiver")
async def paystack_webhook(request: Request, db: Session = Depends(get_db)) -> Response:
    """Receive Paystack events. Verifies the ``x-paystack-signature`` HMAC, then
    reconciles successful charges (exact-amount match → confirm appointment).

    Always returns 200 for accepted-but-unactionable events so Paystack does not
    retry indefinitely; returns 401 only on a bad signature.
    """
    raw = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not paystack.verify_signature(raw, signature):
        logger.warning("Rejected webhook with invalid signature")
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    event = body.get("event", "")
    data = body.get("data") or {}

    # Successful card charge or dedicated-account transfer credit.
    if event == "charge.success":
        result = reconciliation.reconcile_from_paystack(db, data)
        logger.info("webhook charge.success -> %s (%s)", result.status, result.detail)
    else:
        logger.info("webhook event ignored: %s", event)

    return Response(status_code=status.HTTP_200_OK)
