import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.booking import (
    BookingCreate,
    BookingCreateResponse,
    BookingRead,
    PaymentInit,
)
from app.services import bookings as bookings_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post(
    "",
    response_model=BookingCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a booking (pending payment)",
)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db)) -> BookingCreateResponse:
    """Hold the slot, snapshot the price, create a PENDING_PAYMENT booking and
    initialize a Paystack transaction. Returns the booking + payment init data."""
    booking, payment = bookings_service.create_booking(
        db,
        patient_id=payload.patient_id,
        slot_id=payload.slot_id,
        service_id=payload.service_id,
    )
    return BookingCreateResponse(
        booking=BookingRead.model_validate(booking),
        payment=PaymentInit(
            reference=payment.reference,
            authorization_url=payment.authorization_url,
            access_code=payment.access_code,
        ),
    )


@router.get("/{booking_id}", response_model=BookingRead, summary="Get a booking")
def get_booking(booking_id: uuid.UUID, db: Session = Depends(get_db)) -> BookingRead:
    return bookings_service.get_booking(db, booking_id)


@router.post("/{booking_id}/cancel", response_model=BookingRead, summary="Cancel a booking")
def cancel_booking(booking_id: uuid.UUID, db: Session = Depends(get_db)) -> BookingRead:
    return bookings_service.cancel_booking(db, booking_id)
