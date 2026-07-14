"""Edge cases: double-booking, under/over-payment, expiry, idempotent reconcile."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import AppointmentStatus, BookingStatus, PaymentStatus, SlotStatus
from app.services import bookings as bookings_service
from app.services import reconciliation
from app.services import slots as slots_service
from app.services.exceptions import SlotUnavailableError
from tests.conftest import Scenario


def _book(db, sc: Scenario):
    return bookings_service.create_booking(
        db, patient_id=sc.patient.id, slot_id=sc.slot.id, service_id=sc.service.id
    )


def test_double_booking_rejected(db, scenario):
    """A second booking on the same held slot is rejected."""
    booking, _ = _book(db, scenario)
    assert booking.status == BookingStatus.PENDING_PAYMENT

    with pytest.raises(SlotUnavailableError):
        _book(db, scenario)


def test_underpayment_not_confirmed(db, scenario):
    booking, payment = _book(db, scenario)

    result = reconciliation.confirm_payment(
        db,
        payment_id=payment.id,
        amount_paid=booking.amount - 1,  # ₦0.01 short
        charge_status="success",
        gateway_response={"amount": booking.amount - 1},
    )
    assert result.status == "amount_mismatch"
    assert "underpaid" in result.detail

    db.refresh(booking)
    assert booking.status == BookingStatus.PENDING_PAYMENT
    assert booking.appointment is None


def test_overpayment_not_confirmed(db, scenario):
    booking, payment = _book(db, scenario)

    result = reconciliation.confirm_payment(
        db,
        payment_id=payment.id,
        amount_paid=booking.amount + 100_00,  # ₦100 over
        charge_status="success",
        gateway_response={"amount": booking.amount + 100_00},
    )
    assert result.status == "amount_mismatch"
    assert "overpaid" in result.detail

    db.refresh(booking)
    assert booking.status == BookingStatus.PENDING_PAYMENT


def test_exact_payment_confirms_and_is_idempotent(db, scenario):
    booking, payment = _book(db, scenario)

    r1 = reconciliation.confirm_payment(
        db,
        payment_id=payment.id,
        amount_paid=booking.amount,
        charge_status="success",
        gateway_response={"amount": booking.amount},
    )
    assert r1.status == "confirmed"
    assert r1.appointment is not None
    assert r1.appointment.status == AppointmentStatus.SCHEDULED

    db.refresh(booking)
    db.refresh(scenario.slot)
    assert booking.status == BookingStatus.CONFIRMED
    assert payment.status == PaymentStatus.SUCCESS
    assert scenario.slot.status == SlotStatus.BOOKED

    # Replay the same charge — no second appointment, still confirmed.
    r2 = reconciliation.confirm_payment(
        db,
        payment_id=payment.id,
        amount_paid=booking.amount,
        charge_status="success",
        gateway_response={"amount": booking.amount},
    )
    assert r2.status == "already_confirmed"
    assert r2.appointment.id == r1.appointment.id


def test_late_payment_after_expiry_not_double_booked(db, scenario):
    booking, payment = _book(db, scenario)

    # Force the booking past its deadline and expire it.
    booking.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    expired = bookings_service.expire_overdue_bookings(db)
    assert booking.id in expired

    db.refresh(booking)
    db.refresh(scenario.slot)
    assert booking.status == BookingStatus.EXPIRED
    assert scenario.slot.status == SlotStatus.OPEN
    assert payment.status == PaymentStatus.ABANDONED

    # Money lands late — flagged, no appointment created.
    result = reconciliation.confirm_payment(
        db,
        payment_id=payment.id,
        amount_paid=booking.amount,
        charge_status="success",
        gateway_response={"amount": booking.amount},
    )
    assert result.status == "late_payment"
    db.refresh(booking)
    assert booking.appointment is None


def test_expiry_releases_slot(db, scenario):
    booking, _ = _book(db, scenario)
    db.refresh(scenario.slot)
    assert scenario.slot.status == SlotStatus.HELD

    booking.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    bookings_service.expire_overdue_bookings(db)

    db.refresh(scenario.slot)
    assert scenario.slot.status == SlotStatus.OPEN

    # Slot is available to the engine again after release. (Note: a *new* booking on
    # the same slot is blocked by the unique bookings.slot_id constraint — the slot
    # is reusable for holds/availability, but rebooking the identical slot row is not
    # supported by the current schema.)
    held = slots_service.hold_slot(db, slot_id=scenario.slot.id)
    assert held.status == SlotStatus.HELD
