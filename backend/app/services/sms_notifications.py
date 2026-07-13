"""SMS delivery for domain notification events.

Called from notifications._deliver() after the originating transaction commits.
Uses the DB session provided by the caller (which creates its own short-lived
session so this works both inline and in Celery tasks).

Events handled:
  BOOKING_CREATED   — payment instruction SMS (ref, amount, bank/card details)
  BOOKING_CONFIRMED — appointment confirmation (service, time, ref)
  BOOKING_EXPIRED   — expiry notice with retry prompt

Language detection order:
  1. Caller-supplied lang hint (from USSD/SMS booking context)
  2. Most recent Conversation record for the patient's phone
  3. Default: "en"

All send functions are no-raise — failures are logged but never surface to the
caller. A missed SMS is never worth blocking the request or the Celery task.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.booking import Booking
from app.models.conversation import Conversation
from app.models.service import Service
from app.services import africastalking as at

logger = logging.getLogger(__name__)

WAT = ZoneInfo("Africa/Lagos")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _format_wat(dt: datetime) -> str:
    return dt.astimezone(WAT).strftime("%a %d %b, %I:%M %p WAT")


def _format_naira(kobo: int) -> str:
    return f"₦{kobo // 100:,}"


def _detect_lang(db: Session, phone: str | None) -> str:
    """Return the most recently detected language for this phone number."""
    if not phone:
        return "en"
    conv = db.execute(
        select(Conversation)
        .where(Conversation.phone == phone)
        .order_by(Conversation.last_message_at.desc().nulls_last())
        .limit(1)
    ).scalar_one_or_none()
    return conv.language if conv and conv.language else "en"


def _load_booking(db: Session, booking_id_str: str) -> Booking | None:
    try:
        bid = uuid.UUID(booking_id_str)
    except ValueError:
        logger.error("sms_notifications: invalid booking_id %r", booking_id_str)
        return None
    return db.execute(
        select(Booking)
        .options(
            joinedload(Booking.patient),
            joinedload(Booking.slot),
            joinedload(Booking.payment),
            joinedload(Booking.virtual_account),
        )
        .where(Booking.id == bid)
    ).scalar_one_or_none()


def _payment_details_block(va, checkout_url: str | None, lang: str) -> str:
    """Build the bank/card payment details block for the payment instruction SMS."""
    lines: list[str] = []
    if va is not None:
        labels = {
            "en": "Transfer to:",
            "pidgin": "Transfer go this account:",
            "yo": "Fi owó rán sí àkàùntì yìí:",
        }
        lines.append(labels.get(lang, labels["en"]))
        lines.append(f"  Bank: {va.bank_name or 'See bank app'}")
        lines.append(f"  Acct: {va.account_number}")
        lines.append(f"  Name: {va.account_name}")
    if checkout_url:
        label = "Or pay by card:" if lines else "Pay by card:"
        lines += [label, f"  {checkout_url}"]
    if not lines:
        # No VA, no checkout URL — DVA provisioning pending (USSD path)
        fallbacks = {
            "en": "Bank transfer details will follow shortly.",
            "pidgin": "We go send bank details to you soon.",
            "yo": "A yoo fi alaye ìfowópamọ́ ranṣẹ sí ọ laipẹ.",
        }
        lines.append(fallbacks.get(lang, fallbacks["en"]))
    return "\n".join(lines)


# ─── Templates ────────────────────────────────────────────────────────────────

_PAYMENT_INSTRUCTIONS: dict[str, str] = {
    "en": (
        "Hi! Your {service} slot is held.\n"
        "Ref: {ref}\n"
        "Amount: {amount}\n"
        "{payment_details}\n"
        "Expires: {expires}"
    ),
    "pidgin": (
        "Hey! We don hold your {service} slot.\n"
        "Ref: {ref}\n"
        "Amount: {amount}\n"
        "{payment_details}\n"
        "Slot go expire: {expires}"
    ),
    "yo": (
        "Ẹ káàbọ̀! A ti pa àkókò {service} rẹ mọ.\n"
        "Ref: {ref}\n"
        "Iye: {amount}\n"
        "{payment_details}\n"
        "Àkókò parí: {expires}"
    ),
}

_CONFIRMED: dict[str, str] = {
    "en": (
        "✅ Appointment confirmed!\n"
        "Service: {service}\n"
        "When: {slot_time}\n"
        "Ref: {ref}\n"
        "We look forward to seeing you!"
    ),
    "pidgin": (
        "✅ Appointment don confirm!\n"
        "Service: {service}\n"
        "When: {slot_time}\n"
        "Ref: {ref}\n"
        "We go see you there!"
    ),
    "yo": (
        "✅ A ti jẹrisi adehun rẹ!\n"
        "Iṣẹ́: {service}\n"
        "Àkókò: {slot_time}\n"
        "Ref: {ref}\n"
        "A máa ríi rẹ!"
    ),
}

_EXPIRED: dict[str, str] = {
    "en": (
        "Your appointment slot (Ref: {ref}) has expired — payment was not received in time.\n"
        "Reply BOOK to start again, or call the clinic."
    ),
    "pidgin": (
        "Your appointment slot (Ref: {ref}) don expire — payment no reach in time.\n"
        "Reply BOOK to try again, or call the clinic."
    ),
    "yo": (
        "Àkókò adehun rẹ (Ref: {ref}) ti parí — isanwo kò dé lójú àkókò.\n"
        "Fèsì BOOK láti bẹ̀rẹ̀ lẹẹkansii, tàbí pe ile-iwosan."
    ),
}


# ─── Public send functions ────────────────────────────────────────────────────

def send_booking_created(
    db: Session, booking_id_str: str, *, lang: str | None = None
) -> None:
    """Send payment instruction SMS after a booking is created (PENDING_PAYMENT)."""
    booking = _load_booking(db, booking_id_str)
    if not booking:
        return
    patient = booking.patient
    if not patient or not patient.phone:
        logger.debug("send_booking_created: no phone for booking %s — skipping SMS", booking_id_str)
        return

    effective_lang = lang or _detect_lang(db, patient.phone)

    service_name = "Appointment"
    if booking.service_id:
        svc = db.get(Service, booking.service_id)
        if svc:
            service_name = svc.name

    ref = booking.payment.reference if booking.payment else f"AUTOMO-{booking.id.hex[:12].upper()}"
    amount = _format_naira(booking.amount)
    expires = _format_wat(booking.expires_at) if booking.expires_at else "N/A"
    checkout_url = booking.payment.authorization_url if booking.payment else None
    payment_details = _payment_details_block(booking.virtual_account, checkout_url, effective_lang)

    tmpl = _PAYMENT_INSTRUCTIONS.get(effective_lang, _PAYMENT_INSTRUCTIONS["en"])
    sms = tmpl.format(
        service=service_name,
        ref=ref,
        amount=amount,
        payment_details=payment_details,
        expires=expires,
    )
    try:
        at.send_sms(sms, [patient.phone])
        logger.info("payment instruction SMS → %s (booking %s)", patient.phone, booking_id_str)
    except Exception as exc:
        logger.error("payment instruction SMS failed for %s: %s", patient.phone, exc)


def send_booking_confirmed(
    db: Session, booking_id_str: str, *, lang: str | None = None
) -> None:
    """Send appointment confirmation SMS after payment reconciliation."""
    booking = _load_booking(db, booking_id_str)
    if not booking:
        return
    patient = booking.patient
    if not patient or not patient.phone:
        return

    effective_lang = lang or _detect_lang(db, patient.phone)

    service_name = "Appointment"
    if booking.service_id:
        svc = db.get(Service, booking.service_id)
        if svc:
            service_name = svc.name

    slot_time = _format_wat(booking.slot.start_time) if booking.slot else "See clinic"
    ref = booking.payment.reference if booking.payment else f"AUTOMO-{booking.id.hex[:12].upper()}"

    tmpl = _CONFIRMED.get(effective_lang, _CONFIRMED["en"])
    sms = tmpl.format(service=service_name, slot_time=slot_time, ref=ref)
    try:
        at.send_sms(sms, [patient.phone])
        logger.info("confirmation SMS → %s (booking %s)", patient.phone, booking_id_str)
    except Exception as exc:
        logger.error("confirmation SMS failed for %s: %s", patient.phone, exc)


def send_booking_expired(
    db: Session, booking_id_str: str, *, lang: str | None = None
) -> None:
    """Send expiry notice SMS when a PENDING_PAYMENT booking times out."""
    booking = _load_booking(db, booking_id_str)
    if not booking:
        return
    patient = booking.patient
    if not patient or not patient.phone:
        return

    effective_lang = lang or _detect_lang(db, patient.phone)
    ref = booking.payment.reference if booking.payment else f"AUTOMO-{booking.id.hex[:12].upper()}"

    tmpl = _EXPIRED.get(effective_lang, _EXPIRED["en"])
    sms = tmpl.format(ref=ref)
    try:
        at.send_sms(sms, [patient.phone])
        logger.info("expiry SMS → %s (booking %s)", patient.phone, booking_id_str)
    except Exception as exc:
        logger.error("expiry SMS failed for %s: %s", patient.phone, exc)
