"""USSD booking engine.

Handles the final step of the USSD flow: turning a confirmed service
selection into a real held booking and queuing the payment SMS.

Design notes
------------
* Paystack DVA (virtual accounts) is Koded's Day 5 work.  Until then we
  issue a booking reference and instruct the patient to watch for a follow-up
  SMS once virtual account details are ready.  The SMS copy here is a
  placeholder that keeps the demo end-to-end without depending on Paystack.
* We create the Booking and Payment rows directly (bypassing the Paystack
  HTTP call) so the USSD session is never blocked by a payment-provider
  timeout.  The booking status is PENDING_PAYMENT; a Celery task will
  expire it if payment doesn't arrive within BOOKING_PAYMENT_TTL_SECONDS.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.enums import BookingStatus, PaymentStatus, SlotStatus
from app.models.payment import Payment
from app.models.service import Service
from app.models.slot import Slot
from app.services import africastalking as at
from app.services.patients import get_or_create_by_phone

logger = logging.getLogger(__name__)

WAT = ZoneInfo("Africa/Lagos")

# Maps USSD service keys (step-3 choice) to a keyword searched in Service.name
_SERVICE_KEYWORDS: dict[str, str] = {
    "1": "consultation",
    "2": "lab",
    "3": "virtual",
}

_PAYMENT_SMS: dict[str, str] = {
    "en": (
        "Your {service} slot is held until {expires}.\n"
        "Ref: {ref}\n"
        "Payment instructions will arrive shortly by SMS.\n"
        "Amount: {amount}"
    ),
    "pidgin": (
        "We don hold your {service} slot until {expires}.\n"
        "Ref: {ref}\n"
        "We go send payment details to you by SMS soon.\n"
        "Amount: {amount}"
    ),
    "yo": (
        "A ti pa akoko {service} rẹ mọ titi {expires}.\n"
        "Ref: {ref}\n"
        "A yoo fi alaye isanwo ranṣẹ si ọ nipasẹ SMS laipẹ.\n"
        "Iye: {amount}"
    ),
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
    """Format a UTC datetime as a human-readable WAT string."""
    wat_dt = dt.astimezone(WAT)
    return wat_dt.strftime("%a %d %b, %I:%M %p WAT")


def _format_kobo(kobo: int) -> str:
    """Convert kobo to a formatted naira string, e.g. 200000 → '₦2,000'."""
    naira = kobo // 100
    return f"₦{naira:,}"


def _find_next_slot(db: Session, service_key: str) -> tuple[Slot, Service] | None:
    """Return the next open (slot, service) pair for the given service key."""
    keyword = _SERVICE_KEYWORDS.get(service_key, "consultation")
    now = datetime.now(timezone.utc)

    # Find active services whose name contains the keyword (case-insensitive)
    services = db.execute(
        select(Service).where(
            Service.is_active.is_(True),
            Service.name.ilike(f"%{keyword}%"),
        )
    ).scalars().all()

    if not services:
        # Fall back to any active service
        services = db.execute(
            select(Service).where(Service.is_active.is_(True)).limit(3)
        ).scalars().all()

    if not services:
        return None

    service_ids = [s.id for s in services]
    service_map = {s.id: s for s in services}

    # Find earliest open slot for any of these services
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
        # Also try slots without a service_id (generic slots)
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

    The payment row holds the reference only; the actual payment mechanism
    (virtual account) is added by Koded's Day 5 payment work.
    """
    from app.core.config import settings

    now = datetime.now(timezone.utc)
    from datetime import timedelta
    expires_at = now + timedelta(seconds=settings.booking_payment_ttl_seconds)

    # Hold the slot
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

    Returns an ``END ``-prefixed string ready to send back to Africa's
    Talking.
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

    # Send payment SMS
    sms_text = _PAYMENT_SMS.get(lang, _PAYMENT_SMS["en"]).format(
        service=service.name,
        expires=_format_wat(booking.expires_at),
        ref=payment.reference,
        amount=_format_kobo(service.price_amount),
    )
    try:
        at.send_sms(sms_text, [phone])
    except Exception as exc:
        logger.error("Payment SMS failed for %s: %s", phone, exc)

    return "END " + _END_CONFIRMED.get(lang, _END_CONFIRMED["en"])
