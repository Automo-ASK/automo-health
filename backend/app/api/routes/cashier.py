from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.cashier import (
    CashCollectRequest,
    CashCollectResponse,
    OutstandingBooking,
)
from app.services import cashier as cashier_service

router = APIRouter(prefix="/cashier", tags=["cashier"])


@router.get(
    "/outstanding",
    response_model=list[OutstandingBooking],
    summary="List bookings awaiting payment",
)
def list_outstanding(db: Session = Depends(get_db)) -> list[OutstandingBooking]:
    """The cashier's work queue — bookings still pending payment."""
    return cashier_service.list_outstanding(db)


@router.post(
    "/collect",
    response_model=CashCollectResponse,
    summary="Collect cash for a booking",
)
def collect_cash(
    payload: CashCollectRequest, db: Session = Depends(get_db)
) -> CashCollectResponse:
    """Record a cash/POS payment (exact amount) and confirm the booking."""
    result = cashier_service.collect_cash(
        db, payload.booking_id, amount=payload.amount, reference=payload.reference
    )
    return CashCollectResponse(
        status=result.status,
        detail=result.detail,
        booking_id=result.booking.id if result.booking else None,
        appointment_id=result.appointment.id if result.appointment else None,
    )
