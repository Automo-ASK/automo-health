"""USSD booking engine.

Handles the final step of the USSD flow: turning a confirmed service
selection into a real held booking and firing the payment notification.

Design notes
------------
* Paystack DVA (virtual accounts) is Koded's Day 5 payment work. We create
  Booking + Payment rows directly (no Paystack HTTP call) so the USSD session
  is never blocked by a payment-provider timeout.
* After the DB commit, we fire a BOOKING_CREATED notification which calls
  sms_notifications.send_booking_created() — that sends the full payment
  instruction SMS (including bank transfer details if a virtual account exists).
* The booking status is PENDING_PAYMENT; a Celery beat task expires it if
  payment doesn't arrive within BOOKING_PAYMENT_TTL_SECONDS.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.enums import BookingStatus, NotificationEvent, PaymentStatus, SlotStatus
from app.models.payment import Payment
from app.models.service import Service
from app.models.slot import Slot
from app.services import notifications
from app.services.patients import get_or_create_by_phone

logger = logging.getLogger(__name__)

WAT = ZoneInfo("Africa/Lagos")

# Maps USSD service keys (step-3 choice) to a keyword searched in Service.name
_SERVICE_KEYWORDS: dict[str, str] = {
    "1": "consultation",
    "2": "lab",
    "3": "virtual",
}

_END_CONFIRMED: dict[str, str] = {
    "en": "Booking confirmed! Check your SMS for payment details.",
    "pidgin": "Booking don confirm! Check your SMS for payment details.",
    "yo": "A ti jẹrisi adehun rẹ! Wo SMS rẹ fun alaye isanwo.",
}

_END_NO_SLOTS: dict[str, str] = {
    "en": "Sorry, no slots available right now. Please try again later or call the clinic.",
    "pidgin": "Sorry, no slot dey available now. Try again later or call the clinic.",
    "yo": "Pẹ̀lẹ́ ọ, kò sí àkókò tí ó wà báyìí. Jọwọ gbìyànjú lẹhinna tàbí pe ile-iwosan.",
}


def _format_wat(dt: datetime) -> str:
    return dt.astimezone(WAT).strftime("%a %d %b, %I:%M %p WAT")


def _format_kobo(kobo: int) -> str:
    return f"₦{kobo // 100:,}"


def _find_next_slot(db: Session, service_key: str) -> tuple[Slot, Service] | None:
    """Return the next open (slot, service) pair for the given service key."""
    keyword = _SERVICE_KEYWORDS.get(service_key, "consultation")
    now = datetime.now(timezone.utc)

    services = db.execute(
        select(Service).where(
            Service.is_active.is_(True),
            Service.name.ilike(f"%{keyword}%"),
        )
    ).scalars().all()

    if not services:
        services = db.execute(
            select(Service).where(Service.is_active.is_(True)).limit(3)
        ).scalars().all()

    if not services:
        return None

    service_ids = [s.id for s in services]
    service_map = {s.id: s for s in services}

    slot = db.execute(
        select(Slot)
        .where(
            Slot.service_id.in_(service_ids),
            Slot.status == SlotStatus.OPEN,
            Slot.start_time > now,
        )
        .order_by(Slot.start_time)
        .limit(1)
    ).scalar_one_or_none()

    if slot is None:
        slot = db.execute(
            select(Slot)
            .where(
                Slot.service_id.is_(None),
                Slot.status == SlotStatus.OPEN,
                Slot.start_time > now,
            )
            .order_by(Slot.start_time)
            .limit(1)
        ).scalar_one_or_none()
        if slot is None:
            return None
        service = services[0]
    else:
        service = service_map[slot.service_id]

    return slot, service


def _create_booking_direct(
    db: Session,
    *,
    patient_id: uuid.UUID,
    slot: Slot,
    service: Service,
) -> tuple[Booking, Payment]:
    """Create a PENDING_PAYMENT booking without calling Paystack.

    Commits the transaction and returns the refreshed Booking + Payment rows.
    The caller is responsible for firing the BOOKING_CREATED notification after
    this returns (so it fires after the commit, not inside it).
    """
    from app.core.config import settings

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.booking_payment_ttl_seconds)

    slot.status = SlotStatus.HELD
    slot.hold_expires_at = expires_at

    booking = Booking(
        patient_id=patient_id,
        slot_id=slot.id,
        service_id=service.id,
        status=BookingStatus.PENDING_PAYMENT,
        amount=service.price_amount,
        currency=service.currency,
        expires_at=expires_at,
    )
    db.add(booking)
    db.flush()

    reference = f"AUTOMO-{booking.id.hex[:12].upper()}"
    payment = Payment(
        booking_id=booking.id,
        provider="PAYSTACK",
        status=PaymentStatus.PENDING,
        amount=service.price_amount,
        currency=service.currency,
        reference=reference,
    )
    db.add(payment)
    db.commit()
    db.refresh(booking)
    db.refresh(payment)
    return booking, payment


def next_slot_label(db: Session, service_key: str) -> str:
    """Return a human-readable WAT string for the next open slot, or a fallback."""
    result = _find_next_slot(db, service_key)
    if result is None:
        return "No slots available"
    slot, _ = result
    return _format_wat(slot.start_time)


def confirm(
    db: Session,
    *,
    phone: str,
    service_key: str,
    lang: str,
) -> str:
    """Run the full USSD booking confirmation.

    Creates the booking, fires the BOOKING_CREATED notification (which delivers
    the payment instruction SMS), and returns an ``END``-prefixed string.
    """
    result = _find_next_slot(db, service_key)
    if result is None:
        return "END " + _END_NO_SLOTS.get(lang, _END_NO_SLOTS["en"])

    slot, service = result
    patient = get_or_create_by_phone(db, phone)

    try:
        booking, payment = _create_booking_direct(
            db,
            patient_id=patient.id,
            slot=slot,
            service=service,
        )
    except Exception as exc:
        logger.error("USSD booking failed for %s: %s", phone, exc)
        db.rollback()
        return "END Sorry, we couldn't complete your booking. Please try again or call the clinic."

    # Fire BOOKING_CREATED — sms_notifications.send_booking_created() will deliver
    # the payment instruction SMS (with bank transfer details if a virtual account exists).
    notifications.dispatch(
        NotificationEvent.BOOKING_CREATED,
        {
            "booking_id": str(booking.id),
            "patient_id": str(patient.id),
            "amount": booking.amount,
            "currency": booking.currency,
            "expires_at": booking.expires_at.isoformat() if booking.expires_at else None,
            "lang": lang,
        },
    )

    return "END " + _END_CONFIRMED.get(lang, _END_CONFIRMED["en"])
