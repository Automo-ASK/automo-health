"""Booking service — create a booking as PENDING_PAYMENT.

Creating a booking atomically:
  1. Locks the target slot (``FOR UPDATE``) and verifies it is holdable.
  2. Snapshots the price from the chosen service.
  3. Marks the slot HELD for the payment window.
  4. Creates the Booking (PENDING_PAYMENT) and a Payment row.
  5. Initializes a Paystack transaction and stores the reference / auth URL.

If the Paystack init fails, the whole transaction rolls back, releasing the hold.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.booking import Booking
from app.models.enums import BookingStatus, PaymentProvider, PaymentStatus, SlotStatus
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.service import Service
from app.models.slot import Slot
from app.services import paystack
from app.services.exceptions import (
    NotFoundError,
    PaymentError,
    SlotUnavailableError,
)
from app.services.slots import _is_holdable


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_booking(db: Session, booking_id: uuid.UUID) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise NotFoundError(f"Booking {booking_id} not found")
    return booking


def create_booking(
    db: Session,
    *,
    patient_id: uuid.UUID,
    slot_id: uuid.UUID,
    service_id: uuid.UUID | None = None,
) -> tuple[Booking, Payment]:
    now = _utcnow()

    patient = db.get(Patient, patient_id)
    if patient is None:
        raise NotFoundError(f"Patient {patient_id} not found")

    # Lock the slot for the whole transaction so concurrent bookings can't both win.
    slot = db.execute(
        select(Slot).where(Slot.id == slot_id).with_for_update()
    ).scalar_one_or_none()
    if slot is None:
        raise NotFoundError(f"Slot {slot_id} not found")

    if not _is_holdable(slot, now):
        db.rollback()
        raise SlotUnavailableError(
            f"Slot {slot_id} is not available (status={slot.status.value})"
        )

    # Resolve the service to price the booking. Prefer explicit service_id, then
    # the slot's own service.
    resolved_service_id = service_id or slot.service_id
    amount = 0
    currency = settings.default_currency
    if resolved_service_id is not None:
        service = db.get(Service, resolved_service_id)
        if service is None:
            db.rollback()
            raise NotFoundError(f"Service {resolved_service_id} not found")
        amount = service.price_amount
        currency = service.currency

    expires_at = now + timedelta(seconds=settings.booking_payment_ttl_seconds)

    # Hold the slot for the payment window.
    slot.status = SlotStatus.HELD
    slot.hold_expires_at = expires_at

    booking = Booking(
        patient_id=patient_id,
        slot_id=slot_id,
        service_id=resolved_service_id,
        status=BookingStatus.PENDING_PAYMENT,
        amount=amount,
        currency=currency,
        expires_at=expires_at,
    )
    db.add(booking)
    db.flush()  # assign booking.id

    reference = f"AUTOMO-{booking.id.hex[:16].upper()}"
    payment = Payment(
        booking_id=booking.id,
        provider=PaymentProvider.PAYSTACK,
        status=PaymentStatus.PENDING,
        amount=amount,
        currency=currency,
        reference=reference,
    )
    db.add(payment)
    db.flush()

    # Initialize the Paystack transaction. On failure, roll everything back so the
    # slot hold is released and no orphan booking remains.
    try:
        init = paystack.initialize_transaction(
            email=patient.email,
            amount_kobo=amount,
            reference=reference,
            currency=currency,
        )
    except Exception as exc:  # noqa: BLE001 — surfaced as a 502 to the caller
        db.rollback()
        raise PaymentError(f"Failed to initialize payment: {exc}") from exc

    payment.authorization_url = init.get("authorization_url")
    payment.access_code = init.get("access_code")

    db.commit()
    db.refresh(booking)
    db.refresh(payment)
    return booking, payment


def cancel_booking(db: Session, booking_id: uuid.UUID) -> Booking:
    """Cancel a booking and release its slot (unless already confirmed)."""
    booking = db.execute(
        select(Booking).where(Booking.id == booking_id).with_for_update()
    ).scalar_one_or_none()
    if booking is None:
        raise NotFoundError(f"Booking {booking_id} not found")

    if booking.status in (BookingStatus.CANCELLED, BookingStatus.EXPIRED):
        return booking

    booking.status = BookingStatus.CANCELLED

    slot = db.execute(
        select(Slot).where(Slot.id == booking.slot_id).with_for_update()
    ).scalar_one_or_none()
    if slot is not None and slot.status != SlotStatus.BOOKED:
        slot.status = SlotStatus.OPEN
        slot.hold_expires_at = None

    if booking.payment is not None and booking.payment.status == PaymentStatus.PENDING:
        booking.payment.status = PaymentStatus.ABANDONED

    db.commit()
    db.refresh(booking)
    return booking
