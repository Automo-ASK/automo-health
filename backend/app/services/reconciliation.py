"""Payment reconciliation (Day 4).

Reconciles a successful Paystack charge (from a webhook or a manual verify) against
the owning booking:

  * resolve the payment by our ``reference`` or by the dedicated virtual account the
    transfer landed in;
  * enforce an **exact-amount match** against the snapshotted expected amount;
  * idempotently confirm: booking -> CONFIRMED, slot -> BOOKED, appointment created,
    virtual account closed;
  * guard bookings that already expired/cancelled (late payment — flagged, not
    double-booked);
  * fire notification hooks after the state is committed.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.booking import Booking
from app.models.enums import (
    AppointmentStatus,
    BookingStatus,
    NotificationEvent,
    PaymentStatus,
    SlotStatus,
    VirtualAccountStatus,
)
from app.models.payment import Payment
from app.models.slot import Slot
from app.models.virtual_account import VirtualAccount
from app.services import notifications, paystack
from app.services.exceptions import NotFoundError

logger = logging.getLogger(__name__)


@dataclass
class ReconcileResult:
    status: str  # confirmed | already_confirmed | amount_mismatch | late_payment | ignored
    booking: Booking | None = None
    payment: Payment | None = None
    appointment: Appointment | None = None
    detail: str = ""
    _events: list[tuple[str, dict]] = field(default_factory=list, repr=False)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def resolve_payment(db: Session, data: dict) -> Payment | None:
    """Find the Payment a Paystack event belongs to.

    Tries our own transaction ``reference`` first (hosted checkout), then falls back
    to the dedicated virtual account the money landed in (bank transfer), matching on
    ``customer_code`` or the receiver account number.
    """
    reference = data.get("reference")
    if reference:
        payment = db.execute(
            select(Payment).where(Payment.reference == reference)
        ).scalar_one_or_none()
        if payment is not None:
            return payment

    # Dedicated-account transfer: resolve via the virtual account.
    customer = data.get("customer") or {}
    customer_code = customer.get("customer_code")
    authorization = data.get("authorization") or {}
    account_number = authorization.get("receiver_bank_account_number") or data.get(
        "account_number"
    )

    va = None
    if customer_code:
        va = db.execute(
            select(VirtualAccount).where(VirtualAccount.customer_code == customer_code)
        ).scalar_one_or_none()
    if va is None and account_number:
        va = db.execute(
            select(VirtualAccount).where(VirtualAccount.account_number == account_number)
        ).scalar_one_or_none()
    if va is None:
        return None

    return db.execute(
        select(Payment).where(Payment.booking_id == va.booking_id)
    ).scalar_one_or_none()


def reconcile_from_paystack(db: Session, data: dict) -> ReconcileResult:
    """Reconcile a Paystack charge payload (``event.data`` or verify ``data``)."""
    payment = resolve_payment(db, data)
    if payment is None:
        logger.warning("reconcile: no payment found for event %s", data.get("reference"))
        return ReconcileResult(status="ignored", detail="no matching payment")

    charge_status = (data.get("status") or "").lower()
    amount_paid = data.get("amount")
    # Mock verify carries no amount; treat as exact in dev so the flow is testable.
    if amount_paid is None and paystack.is_mock():
        amount_paid = payment.amount

    return confirm_payment(
        db,
        payment_id=payment.id,
        amount_paid=amount_paid,
        charge_status=charge_status or "success",
        gateway_response=data,
    )


def confirm_payment(
    db: Session,
    *,
    payment_id: uuid.UUID,
    amount_paid: int | None,
    charge_status: str,
    gateway_response: dict | None,
) -> ReconcileResult:
    """Idempotently confirm (or flag) a payment. Locks the booking row."""
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError(f"Payment {payment_id} not found")

    booking = db.execute(
        select(Booking).where(Booking.id == payment.booking_id).with_for_update()
    ).scalar_one()

    # Idempotency: already reconciled.
    if payment.status == PaymentStatus.SUCCESS and booking.status == BookingStatus.CONFIRMED:
        return ReconcileResult(
            status="already_confirmed", booking=booking, payment=payment,
            appointment=booking.appointment, detail="already reconciled",
        )

    if charge_status and charge_status != "success":
        payment.gateway_response = gateway_response
        db.commit()
        return ReconcileResult(
            status="ignored", booking=booking, payment=payment,
            detail=f"charge status is {charge_status}",
        )

    expected = payment.amount
    # Exact-amount match — under- or over-payment is not auto-confirmed.
    if amount_paid is None or amount_paid != expected:
        payment.gateway_response = gateway_response
        db.commit()
        result = ReconcileResult(
            status="amount_mismatch", booking=booking, payment=payment,
            detail=f"expected {expected}, got {amount_paid}",
        )
        result._events.append((
            NotificationEvent.PAYMENT_MISMATCH.value,
            {"booking_id": str(booking.id), "expected": expected, "paid": amount_paid},
        ))
        _flush_events(result)
        return result

    now = _utcnow()

    # Money arrived but the hold already lapsed — flag for refund, don't double-book.
    if booking.status != BookingStatus.PENDING_PAYMENT:
        payment.status = PaymentStatus.SUCCESS
        payment.paid_at = now
        payment.gateway_response = gateway_response
        db.commit()
        result = ReconcileResult(
            status="late_payment", booking=booking, payment=payment,
            detail=f"booking was {booking.status.value} when payment arrived",
        )
        result._events.append((
            NotificationEvent.PAYMENT_SUCCEEDED.value,
            {"booking_id": str(booking.id), "late": True, "amount": amount_paid},
        ))
        _flush_events(result)
        return result

    # --- Happy path: confirm the booking, book the slot, schedule the appointment ---
    payment.status = PaymentStatus.SUCCESS
    payment.paid_at = now
    payment.gateway_response = gateway_response

    booking.status = BookingStatus.CONFIRMED

    slot = db.execute(
        select(Slot).where(Slot.id == booking.slot_id).with_for_update()
    ).scalar_one()
    slot.status = SlotStatus.BOOKED
    slot.hold_expires_at = None

    if booking.virtual_account is not None:
        booking.virtual_account.status = VirtualAccountStatus.CLOSED

    appointment = Appointment(
        booking_id=booking.id,
        patient_id=booking.patient_id,
        provider_id=slot.provider_id,
        slot_id=slot.id,
        scheduled_start=slot.start_time,
        scheduled_end=slot.end_time,
        status=AppointmentStatus.SCHEDULED,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    result = ReconcileResult(
        status="confirmed", booking=booking, payment=payment,
        appointment=appointment, detail="confirmed",
    )
    result._events.extend([
        (NotificationEvent.PAYMENT_SUCCEEDED.value,
         {"booking_id": str(booking.id), "amount": amount_paid}),
        (NotificationEvent.BOOKING_CONFIRMED.value,
         {"booking_id": str(booking.id), "patient_id": str(booking.patient_id)}),
        (NotificationEvent.APPOINTMENT_SCHEDULED.value,
         {"appointment_id": str(appointment.id),
          "provider_id": str(appointment.provider_id),
          "scheduled_start": appointment.scheduled_start.isoformat()}),
    ])
    _flush_events(result)
    return result


def _flush_events(result: ReconcileResult) -> None:
    """Dispatch queued notification hooks after state is committed."""
    while result._events:
        event, payload = result._events.pop(0)
        notifications.dispatch(event, payload)
