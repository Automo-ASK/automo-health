"""Cashier / front-desk cash collection (Day 6).

Lets a desk operator settle a booking that's still awaiting payment by taking cash
(or POS) at the clinic, without going through Paystack. It reuses the exact-amount
reconciliation path so a cash-settled booking is confirmed identically to an online
one: booking CONFIRMED, slot BOOKED, appointment created.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.enums import BookingStatus, PaymentProvider, PaymentStatus
from app.models.payment import Payment
from app.services import reconciliation
from app.services.exceptions import ConflictError, NotFoundError
from app.services.reconciliation import ReconcileResult


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def list_outstanding(db: Session) -> list[Booking]:
    """Bookings still awaiting payment — the cashier's work queue."""
    stmt = (
        select(Booking)
        .where(Booking.status == BookingStatus.PENDING_PAYMENT)
        .order_by(Booking.created_at)
    )
    return list(db.execute(stmt).scalars().all())


def collect_cash(
    db: Session, booking_id: uuid.UUID, *, amount: int, reference: str | None = None
) -> ReconcileResult:
    """Record a cash/POS payment against a booking and confirm it.

    Enforces the same exact-amount match as online reconciliation. ``amount`` is in
    minor units (kobo). ``reference`` is an optional desk receipt number.
    """
    booking = db.execute(
        select(Booking).where(Booking.id == booking_id).with_for_update()
    ).scalar_one_or_none()
    if booking is None:
        raise NotFoundError(f"Booking {booking_id} not found")

    if booking.status == BookingStatus.CONFIRMED:
        raise ConflictError("Booking is already confirmed")
    if booking.status != BookingStatus.PENDING_PAYMENT:
        raise ConflictError(f"Cannot collect on a {booking.status.value} booking")

    if amount != booking.amount:
        raise ConflictError(
            f"Amount mismatch: expected {booking.amount}, got {amount}"
        )

    now = _utcnow()
    payment = db.execute(
        select(Payment).where(Payment.booking_id == booking.id).with_for_update()
    ).scalar_one_or_none()
    if payment is None:
        # Follow-ups and manually-created bookings may not have a Payment yet.
        payment = Payment(
            booking_id=booking.id,
            provider=PaymentProvider.CASH,
            status=PaymentStatus.PENDING,
            amount=booking.amount,
            currency=booking.currency,
            reference=reference or f"CASH-{booking.id.hex[:16].upper()}",
        )
        db.add(payment)
        db.flush()
    else:
        payment.provider = PaymentProvider.CASH
        if reference:
            payment.gateway_response = {"cash_reference": reference}

    payment.paid_at = now
    return reconciliation.finalize_confirmation(db, booking, payment, amount, now)
