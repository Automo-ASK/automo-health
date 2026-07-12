"""Payment provisioning: per-booking virtual accounts and in-chat links (Day 3)."""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.enums import BookingStatus, PaymentProvider, VirtualAccountStatus
from app.models.virtual_account import VirtualAccount
from app.services import paystack
from app.services.exceptions import ConflictError, NotFoundError, PaymentError


def _get_booking(db: Session, booking_id: uuid.UUID) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise NotFoundError(f"Booking {booking_id} not found")
    return booking


def _format_amount(amount_kobo: int, currency: str) -> str:
    """Render minor units as a human amount, e.g. 500000 NGN -> '₦5,000.00'."""
    symbol = {"NGN": "₦", "USD": "$", "GHS": "₵", "ZAR": "R"}.get(currency, "")
    major = amount_kobo / 100
    return f"{symbol}{major:,.2f}"


def create_virtual_account(db: Session, booking_id: uuid.UUID) -> VirtualAccount:
    """Provision (or return the existing) dedicated virtual account for a booking.

    Idempotent: a booking has at most one virtual account.
    """
    booking = _get_booking(db, booking_id)

    if booking.virtual_account is not None:
        return booking.virtual_account

    if booking.status != BookingStatus.PENDING_PAYMENT:
        raise ConflictError(
            f"Cannot create a virtual account for a {booking.status.value} booking"
        )

    patient = booking.patient
    try:
        customer = paystack.create_customer(
            email=patient.email, full_name=patient.full_name, phone=patient.phone
        )
        dva = paystack.create_dedicated_virtual_account(
            customer_code=customer["customer_code"], email=patient.email
        )
    except Exception as exc:  # noqa: BLE001 — surfaced as 502
        raise PaymentError(f"Failed to provision virtual account: {exc}") from exc

    va = VirtualAccount(
        booking_id=booking.id,
        provider=PaymentProvider.PAYSTACK,
        status=VirtualAccountStatus.ACTIVE,
        account_number=dva["account_number"],
        account_name=dva["account_name"],
        bank_name=dva.get("bank_name"),
        customer_code=dva.get("customer_code"),
        expected_amount=booking.amount,
        currency=booking.currency,
        expires_at=booking.expires_at,
        raw=dva.get("raw"),
    )
    db.add(va)
    db.commit()
    db.refresh(va)
    return va


@dataclass
class PaymentLink:
    booking_id: uuid.UUID
    amount: int
    currency: str
    reference: str | None
    checkout_url: str | None
    virtual_account: VirtualAccount | None
    chat_message: str


def generate_payment_link(
    db: Session, booking_id: uuid.UUID, *, include_virtual_account: bool = True
) -> PaymentLink:
    """Build an in-chat-shareable payment payload for a booking.

    Combines the hosted checkout link (from the booking's Paystack init) with an
    optional dedicated virtual account for bank transfers, plus a ready-to-send
    chat message.
    """
    booking = _get_booking(db, booking_id)
    if booking.status != BookingStatus.PENDING_PAYMENT:
        raise ConflictError(
            f"Booking is {booking.status.value}; no payment link needed"
        )

    payment = booking.payment
    checkout_url = payment.authorization_url if payment else None
    reference = payment.reference if payment else None

    va = booking.virtual_account
    if include_virtual_account and va is None:
        va = create_virtual_account(db, booking_id)

    amount_str = _format_amount(booking.amount, booking.currency)
    lines = [f"💳 Payment for your appointment — {amount_str}"]
    if checkout_url:
        lines.append(f"Pay by card: {checkout_url}")
    if va is not None:
        lines.append(
            "Or transfer to:\n"
            f"  Bank: {va.bank_name or 'N/A'}\n"
            f"  Account: {va.account_number}\n"
            f"  Name: {va.account_name}"
        )
    lines.append("This link expires when your hold does. Thank you! 🙏")
    chat_message = "\n".join(lines)

    return PaymentLink(
        booking_id=booking.id,
        amount=booking.amount,
        currency=booking.currency,
        reference=reference,
        checkout_url=checkout_url,
        virtual_account=va,
        chat_message=chat_message,
    )
